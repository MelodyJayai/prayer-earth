#!/usr/bin/env python3
"""Persistent, same-origin administration for the prayer trial site.

Integration: set ``server.admin_store = AdminStore(data_dir, seed_file)`` and
inherit ``AdminRequestMixin`` before SimpleHTTPRequestHandler. At the start of
do_GET/POST/PUT/PATCH call ``if self.handle_admin_request(): return``. Serve
``store.media_dir`` at /media/ with normal path traversal protection. The data
directory MUST be outside the static document root. Seed JSON is an array or
{items: [...]} whose segments already contain public ``uri`` values.

``store.bootstrap(username, password)`` creates the first administrator only;
it returns False once any account exists. It never stores cleartext passwords.
All Store validation failures raise ApiError(status, code, message). HTTP errors
have {error, message}. A publish-count mismatch also includes ``actual``.
``/api/content`` and ``/api/prayer-requests`` may be cached for 30 seconds.
Their ETag is the shared content version plus a short hash of the returned
item ids. Authenticated responses are not cached. The failover signature
does not read that ETag; it still uses snapshot file hashes and
``contentVersion``.
"""
from __future__ import annotations

import base64
import argparse
import collections
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import warnings
from contextlib import contextmanager
from email import policy
from email.parser import BytesParser
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from PIL import Image, ImageOps, UnidentifiedImageError


COOKIE_NAME = "prayer_admin_session"
MAX_BODY = 60 * 1024 * 1024
MAX_FILE = 20 * 1024 * 1024
MAX_IMAGES = 20
PASSWORD_ITERATIONS = 600_000
SESSION_SECONDS = 8 * 60 * 60
CHANNELS = {"morning": "晨修", "mission": "宣教动态与见证", "晨修": "晨修", "宣教动态与见证": "宣教动态与见证"}
MAX_INGEST_BODY = 64 * 1024
MAX_NEWS_BATCH = 30
MAX_NEWS_TITLE = 120
MAX_NEWS_SUMMARY = 400
MAX_NEWS_SOURCE_NAME = 60
MAX_NEWS_REGION = 40
MAX_NEWS_URL = 500
MAX_INGEST_KEY = 256
MIN_INGEST_KEY = 16
INGEST_LIMIT = 8
INGEST_WINDOW_SECONDS = 600
INGEST_KEY_ENV = "PRAYER_NEWS_INGEST_KEY"
INGEST_KEY_FILE_ENV = "PRAYER_NEWS_INGEST_KEY_FILE"
DEFAULT_INGEST_KEY_FILE = Path("/etc/prayer-earth-news/ingest.key")
NEWS_CHANNEL = "宗教动态"
NEWS_CATEGORIES = {"基督教", "宗教宣教", "教会", "教会相关"}
NEWS_FIELDS = {"title", "summary", "source_url", "source_name", "published_at", "region", "verified", "category"}
# Substring match on title + summary only. Keep phrases specific; region,
# source name and URL must not pull an unrelated item onto the prayer page.
PRAYER_CANDIDATE_KEYWORDS = (
    "迫害",
    "逾捕",
    "监禁",
    "袭击教会",
    "杀害",
    "绑架",
    "禁教",
    "拘留",
    "关闭教会",
    "拘押",
    "persecution",
)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None):
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}
        super().__init__(message)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _password(password: object) -> str:
    if not isinstance(password, str) or not 12 <= len(password) <= 128 or not password.strip():
        raise ApiError(400, "invalid_password", "密码须为 12–128 个字符，且不能全为空格。")
    return password


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _check_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class IngestLimiter:
    """Short in-process cap for the unattended news ingest endpoint."""

    def __init__(self, limit: int = INGEST_LIMIT, window_seconds: int = INGEST_WINDOW_SECONDS):
        self.limit = limit
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._events: dict[str, collections.deque] = {}

    def allow(self, identity: str) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events.setdefault(identity, collections.deque())
            cutoff = now - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            if len(self._events) > 2048:
                stale = [key for key, value in self._events.items() if not value or value[-1] <= cutoff]
                for key in stale[:1024]:
                    self._events.pop(key, None)
            return True


def _keys_equal(provided: str, expected: str) -> bool:
    # Compare fixed-length digests so a different length cannot skip the check.
    actual = hashlib.sha256(provided.encode("utf-8")).digest()
    stored = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(actual, stored)


def _usable_secret(value: str) -> bool:
    return MIN_INGEST_KEY <= len(value) <= MAX_INGEST_KEY and not any(ord(ch) < 32 or ord(ch) == 127 for ch in value)


def _read_secret_file(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        raise ApiError(503, "ingest_unavailable", "动态提交入口未就绪。") from None
    if not data or len(data) > MAX_INGEST_KEY + 2:
        raise ApiError(503, "ingest_unavailable", "动态提交入口未就绪。")
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        raise ApiError(503, "ingest_unavailable", "动态提交入口未就绪。") from None
    if text.endswith("\n"):
        text = text[:-1]
    if text.endswith("\r"):
        text = text[:-1]
    if not _usable_secret(text):
        raise ApiError(503, "ingest_unavailable", "动态提交入口未就绪。")
    return text


def resolve_ingest_key() -> str | None:
    """Return the ingest key, or None when the endpoint is closed.

    A present but unusable configuration raises ApiError 503. The key is
    never included in the exception or returned to logs by this function's
    callers.
    """
    env = os.environ.get(INGEST_KEY_ENV)
    if env:
        if not _usable_secret(env):
            raise ApiError(503, "ingest_unavailable", "动态提交入口未就绪。")
        return env
    configured = os.environ.get(INGEST_KEY_FILE_ENV)
    if configured:
        return _read_secret_file(Path(configured))
    if DEFAULT_INGEST_KEY_FILE.is_file():
        return _read_secret_file(DEFAULT_INGEST_KEY_FILE)
    return None


def _plain(value: object, *, minimum: int, maximum: int, code: str, message: str) -> str:
    if not isinstance(value, str) or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ApiError(400, code, message)
    text = value.strip()
    if not minimum <= len(text) <= maximum:
        raise ApiError(400, code, message)
    return text


def _canonical_source_url(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_NEWS_URL:
        raise ApiError(400, "invalid_source_url", "来源链接须为 http 或 https。")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value) or "\\" in value:
        raise ApiError(400, "invalid_source_url", "来源链接须为 http 或 https。")
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or parts.username or parts.password:
        raise ApiError(400, "invalid_source_url", "来源链接须为 http 或 https。")
    host = parts.hostname
    if not host:
        raise ApiError(400, "invalid_source_url", "来源链接须为 http 或 https。")
    try:
        port = parts.port
    except ValueError:
        raise ApiError(400, "invalid_source_url", "来源链接须为 http 或 https。") from None
    netloc = "[" + host.lower() + "]" if ":" in host else host.lower()
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc += f":{port}"
    path = parts.path or "/"
    if not path.startswith("/"):
        raise ApiError(400, "invalid_source_url", "来源链接须为 http 或 https。")
    query = f"?{parts.query}" if parts.query else ""
    return f"{scheme}://{netloc}{path}{query}"


def _published_stamp(value: object) -> dt.datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2}))?", value
    ):
        raise ApiError(400, "invalid_published_at", "发布时间须为 UTC 的 ISO-8601。")
    try:
        if "T" not in value:
            day = dt.date.fromisoformat(value)
            stamp = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc)
        else:
            stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        raise ApiError(400, "invalid_published_at", "发布时间须为 UTC 的 ISO-8601。") from None
    now = dt.datetime.now(dt.timezone.utc)
    if stamp < dt.datetime(1990, 1, 1, tzinfo=dt.timezone.utc) or stamp > now + dt.timedelta(hours=36):
        raise ApiError(400, "invalid_published_at", "发布时间超出允许范围。")
    return stamp


def _news_id(stamp: dt.datetime, canonical_url: str) -> str:
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:12]
    return f"news-{stamp.astimezone(dt.timezone.utc).strftime('%Y%m%d')}-{digest}"


def _prayer_haystack(data: dict) -> str:
    parts = []
    for key in ("title", "summary"):
        value = data.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def is_prayer_candidate(data: object) -> bool:
    """True when title or summary contains a persecution keyword."""
    if not isinstance(data, dict):
        return False
    text = _prayer_haystack(data).casefold()
    if not text:
        return False
    return any(keyword.casefold() in text for keyword in PRAYER_CANDIDATE_KEYWORDS)


def _flag_on(value: object) -> bool:
    return value == 1 or value is True


PUBLIC_FEED_CACHE_CONTROL = "public, max-age=30, s-maxage=30, stale-while-revalidate=60"
_FEED_ETAG_HASH_HEX = 16


def feed_etag(prefix: str, version: int, items: list[dict]) -> str:
    """Quoted strong validator: content version plus the returned id set.

    Ids are deduped, sorted, and joined with newlines before SHA-256. The
    first 16 hex characters are the suffix. The same ids in any order share
    one hash, so a routing change that does not bump ``version`` still
    changes the validator. This hash is not an input to the failover
    signature, and computing it does not write the version counter.
    """
    ids = sorted({str(item["id"]) for item in items})
    digest = hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()[:_FEED_ETAG_HASH_HEX]
    return f'"{prefix}-{int(version)}-{digest}"'


def on_prayer_page(data: object, *, status: str, needs_prayer: object, prayer_excluded: object) -> bool:
    """Whether a row is shown on the prayer page instead of the news list.

    Exclusion wins over both the keyword rule and a manual mark. Unverified
    rows are routed only when an administrator marks them. Verified rows whose
    title or summary hits a keyword are routed unless excluded. Pending and
    rejected rows stay off both public surfaces.
    """
    if status != "published" or not isinstance(data, dict):
        return False
    if _flag_on(prayer_excluded):
        return False
    if _flag_on(needs_prayer):
        return True
    return data.get("verified") is True and is_prayer_candidate(data)


def _user(row) -> dict:
    return {"id": row["id"], "username": row["username"], "role": row["role"],
            "active": bool(row["active"]), "mustChangePassword": bool(row["must_change_password"])}


class AdminStore:
    def __init__(self, data_dir, seed_file=None, *, secure_cookies=True):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.media_dir = self.data_dir / "media"
        self.media_dir.mkdir(exist_ok=True, mode=0o700)
        self.db_path = self.data_dir / "admin.sqlite3"
        self.secure_cookies = secure_cookies
        self.lock = threading.RLock()
        self._dummy_password = _hash_password(secrets.token_urlsafe(24))
        with self._db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
              password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','editor')),
              active INTEGER NOT NULL DEFAULT 1, must_change_password INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
              token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
              csrf TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS login_attempts (identity TEXT NOT NULL, at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS login_attempts_identity ON login_attempts(identity, at);
            CREATE TABLE IF NOT EXISTS content (
              id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL
              CHECK(status IN ('draft','published','archived')), seeded INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT,
              action TEXT NOT NULL, target TEXT, detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
            INSERT OR IGNORE INTO meta(key,value) VALUES ('version',1);
            CREATE TABLE IF NOT EXISTS news (
              id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL
              CHECK(status IN ('pending','published','rejected')),
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              needs_prayer INTEGER NOT NULL DEFAULT 0,
              prayer_excluded INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS news_status ON news(status, id);
            """)
            self._migrate_news_prayer_columns(db)
            if seed_file:
                seed = json.loads(Path(seed_file).read_text(encoding="utf-8-sig"))
                items = seed.get("items", []) if isinstance(seed, dict) else seed
                if not isinstance(items, list):
                    raise ValueError("Seed must be an array or {items: [...]}.")
                inserted = 0
                for item in items:
                    if not isinstance(item, dict) or not item.get("id"):
                        raise ValueError("Every seed item needs an id.")
                    item = dict(item)
                    item.setdefault("title", f'{item.get("channel", "内容")} · {item.get("date", "")}')
                    item.setdefault("excerpt", "点击查看完整图片内容")
                    if item.get("segments"):
                        if not all(isinstance(s, dict) and s.get("uri") for s in item["segments"]):
                            raise ValueError("Seed segments need public uri values.")
                        item.setdefault("image", {"uri": item["segments"][0]["uri"]})
                    cursor = db.execute("INSERT OR IGNORE INTO content VALUES (?,?,?,1,?,?)",
                                        (item["id"], json.dumps(item, ensure_ascii=False), "published", _now(), _now()))
                    inserted += cursor.rowcount
                if inserted:
                    self._bump(db)
        if os.name != "nt":
            os.chmod(self.data_dir, 0o700)
            os.chmod(self.db_path, 0o600)

    @contextmanager
    def _db(self):
        with self.lock:
            db = sqlite3.connect(self.db_path, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            try:
                with db:
                    yield db
            finally:
                db.close()

    @staticmethod
    def _audit(db, actor, action, target=None, detail=None):
        db.execute("INSERT INTO audit(at,actor,action,target,detail) VALUES (?,?,?,?,?)",
                   (_now(), actor, action, target, json.dumps(detail or {}, ensure_ascii=False)))

    @staticmethod
    def _bump(db):
        db.execute("UPDATE meta SET value=value+1 WHERE key='version'")

    @staticmethod
    def _migrate_news_prayer_columns(db) -> None:
        """Add prayer flags to databases created before this column existed.

        ``CREATE TABLE IF NOT EXISTS`` does not alter an older ``news`` table.
        New columns default to 0, so existing rows stay unmarked and unexcluded.
        """
        columns = {row["name"] for row in db.execute("PRAGMA table_info(news)")}
        if "needs_prayer" not in columns:
            db.execute("ALTER TABLE news ADD COLUMN needs_prayer INTEGER NOT NULL DEFAULT 0")
        if "prayer_excluded" not in columns:
            db.execute("ALTER TABLE news ADD COLUMN prayer_excluded INTEGER NOT NULL DEFAULT 0")

    def _news_public_sets(self, db) -> tuple[frozenset[str], frozenset[str]]:
        """Published ids on the news list, then ids routed to the prayer page."""
        content_ids: set[str] = set()
        prayer_ids: set[str] = set()
        rows = db.execute(
            "SELECT id, data, needs_prayer, prayer_excluded FROM news WHERE status='published'"
        ).fetchall()
        for row in rows:
            try:
                data = json.loads(row["data"])
            except (TypeError, json.JSONDecodeError):
                continue
            if on_prayer_page(
                data,
                status="published",
                needs_prayer=row["needs_prayer"],
                prayer_excluded=row["prayer_excluded"],
            ):
                prayer_ids.add(row["id"])
            else:
                content_ids.add(row["id"])
        return frozenset(content_ids), frozenset(prayer_ids)

    def _bump_if_news_public_changed(self, db, before: tuple[frozenset[str], frozenset[str]]) -> None:
        """Bump once when either public surface gains or loses a news id.

        ``/api/content`` version and the failover snapshot share this counter.
        Moving a row between the news list and the prayer page changes both
        what the content feed returns and the reader HTML, so the version and
        the snapshot signature move together. A no-op leaves the version alone.

        Public ETags also hash the returned ids. That hash does not replace
        this bump and is not part of ``signature()``: a code deploy can
        reclassify rows without a write, and only the hash changes then.
        """
        if self._news_public_sets(db) != before:
            self._bump(db)

    @staticmethod
    def _username(username):
        if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username):
            raise ApiError(400, "invalid_username", "帐号须为 3–40 位英文字母、数字或 ._-。")
        return username

    def bootstrap(self, username, password) -> bool:
        username = self._username(username)
        password = _password(password)
        with self._db() as db:
            if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return False
            uid = secrets.token_hex(12)
            db.execute("INSERT INTO users VALUES (?,?,?,'admin',1,1,?)",
                       (uid, username, _hash_password(password), _now()))
            self._audit(db, None, "bootstrap_admin", uid)
            return True

    def login(self, username, password, client_ip):
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 100 or len(password) > 128:
            raise ApiError(401, "invalid_credentials", "帐号或密码不正确。")
        now = time.time()
        identities = ("ip:" + str(client_ip), "account:" + username.lower())
        failure = False
        with self._db() as db:
            db.execute("DELETE FROM login_attempts WHERE at < ?", (now - 86400,))
            if any(db.execute("SELECT COUNT(*) FROM login_attempts WHERE identity=? AND at>?", (identity, now-900)).fetchone()[0] >= 8 for identity in identities):
                raise ApiError(429, "login_rate_limited", "尝试次数过多，请 15 分钟后再试。")
            row = db.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
            valid = _check_password(password, row["password_hash"] if row else self._dummy_password)
            if not row or not valid or not row["active"]:
                db.executemany("INSERT INTO login_attempts VALUES (?,?)", [(identity, now) for identity in identities])
                failure = True
            else:
                db.execute("DELETE FROM login_attempts WHERE identity=?", (identities[1],))
                db.execute("DELETE FROM sessions WHERE expires<?", (now,))
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (_digest(token), row["id"], csrf, now+SESSION_SECONDS))
                self._audit(db, row["id"], "login", row["id"])
                result = {"user": _user(row), "csrfToken": csrf}
        if failure:
            raise ApiError(401, "invalid_credentials", "帐号或密码不正确。")
        return token, result

    def session(self, token):
        with self._db() as db:
            row = db.execute("SELECT u.*,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND u.active=1",
                             (_digest(token or ""), time.time())).fetchone()
            if not row:
                raise ApiError(401, "authentication_required", "请先登录。")
            return {"user": _user(row), "csrfToken": row["csrf"]}

    def logout(self, token):
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (_digest(token or ""),))

    def change_password(self, uid, current_password, new_password, token):
        new_password = _password(new_password)
        if not isinstance(current_password, str) or len(current_password) > 128:
            raise ApiError(400, "invalid_password", "当前密码不正确。")
        with self._db() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            if not row or not _check_password(current_password, row["password_hash"]):
                raise ApiError(400, "invalid_password", "当前密码不正确。")
            if hmac.compare_digest(current_password.encode(), new_password.encode()):
                raise ApiError(400, "password_unchanged", "请设置一个不同于临时密码的新密码。")
            db.execute("UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?", (_hash_password(new_password), uid))
            db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (uid, _digest(token)))
            # Rotate CSRF after password changes while keeping this browser signed in.
            db.execute("UPDATE sessions SET csrf=? WHERE token_hash=?", (secrets.token_urlsafe(32), _digest(token)))
            self._audit(db, uid, "change_password", uid)
        return self.session(token)

    def users(self):
        with self._db() as db:
            return [_user(row) for row in db.execute("SELECT * FROM users ORDER BY created_at,username")]

    def create_user(self, actor, data):
        username, password = self._username(data.get("username")), _password(data.get("password"))
        role = data.get("role", "editor")
        if role not in ("admin", "editor"):
            raise ApiError(400, "invalid_role", "角色须为 admin 或 editor。")
        with self._db() as db:
            uid = secrets.token_hex(12)
            try:
                db.execute("INSERT INTO users VALUES (?,?,?,?,1,1,?)", (uid, username, _hash_password(password), role, _now()))
            except sqlite3.IntegrityError:
                raise ApiError(409, "username_exists", "此帐号已存在。") from None
            self._audit(db, actor, "create_user", uid, {"username": username, "role": role})
            return _user(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())

    def update_user(self, actor, uid, data):
        if not data or any(k not in ("active", "password") for k in data):
            raise ApiError(400, "invalid_user_update", "仅支持启用、停用帐号或重置密码。")
        if "active" in data and not isinstance(data["active"], bool):
            raise ApiError(400, "invalid_active", "active 必须是布尔值。")
        password = _password(data["password"]) if "password" in data else None
        with self._db() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            if not row:
                raise ApiError(404, "user_not_found", "帐号不存在。")
            if data.get("active") is False:
                if uid == actor:
                    raise ApiError(400, "cannot_disable_self", "不能停用自己的帐号。")
                if row["role"] == "admin" and row["active"] and db.execute("SELECT COUNT(*) FROM users WHERE active=1 AND role='admin'").fetchone()[0] <= 1:
                    raise ApiError(400, "last_admin", "必须保留至少一个启用的管理员帐号。")
            if "active" in data:
                db.execute("UPDATE users SET active=? WHERE id=?", (int(data["active"]), uid))
            if password:
                db.execute("UPDATE users SET password_hash=?,must_change_password=1 WHERE id=?", (_hash_password(password), uid))
            if password or data.get("active") is False:
                db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            self._audit(db, actor, "update_user", uid, {"active": data.get("active"), "passwordReset": bool(password)})
            return _user(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())

    def content(self, *, public=False):
        with self._db() as db:
            # Keep content and its version in the same SQLite read snapshot,
            # including readers in the separate snapshot publishing process.
            db.execute("BEGIN")
            rows = db.execute("SELECT * FROM content" + (" WHERE status='published'" if public else "")).fetchall()
            items = []
            for row in rows:
                item = json.loads(row["data"])
                if public:
                    # Original upload filenames can contain private group,
                    # person or location identifiers. Keep them in the
                    # authenticated management response only.
                    item.pop("sourceFile", None)
                    item["searchText"] = " ".join((str(item.get("channel", "")), str(item.get("date", "")), str(item.get("title", "")), str(item.get("excerpt", ""))))
                else:
                    item.update(status=row["status"], seeded=bool(row["seeded"]), updatedAt=row["updated_at"])
                items.append(item)
            if public:
                # Pending and rejected news stay out of the public feed, the
                # reader, and failover snapshots. Ingest does not bump version.
                # Rows routed to the prayer page are omitted here so the news
                # list, /reader/news.html and failover snapshots do not repeat them.
                for news_row in db.execute(
                    "SELECT data, needs_prayer, prayer_excluded FROM news WHERE status='published'"
                ):
                    data = json.loads(news_row["data"])
                    if on_prayer_page(
                        data,
                        status="published",
                        needs_prayer=news_row["needs_prayer"],
                        prayer_excluded=news_row["prayer_excluded"],
                    ):
                        continue
                    items.append(self._public_news(data))
            items.sort(key=lambda item: (item.get("date", ""), item["id"]), reverse=True)
            version = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0]
            return {"version": version, "items": items}

    def public_items(self):
        """Published seed and uploaded content, including durable admin overrides."""
        return self.content(public=True)["items"]

    @staticmethod
    def _metadata(data, existing=None):
        item = dict(existing or {})
        allowed = {"date", "channel", "title", "excerpt", "status"}
        if any(key not in allowed for key in data):
            raise ApiError(400, "unknown_field", "包含不支持的内容字段。")
        date = data.get("date", item.get("date"))
        try:
            if not isinstance(date, str) or dt.date.fromisoformat(date).isoformat() != date:
                raise ValueError()
        except ValueError:
            raise ApiError(400, "invalid_date", "日期须为 YYYY-MM-DD。") from None
        raw_channel = data.get("channel", item.get("channel"))
        channel = CHANNELS.get(raw_channel) if isinstance(raw_channel, str) else None
        if not channel:
            raise ApiError(400, "invalid_channel", "请选择晨修或宣教动态与见证。")
        title = data.get("title", item.get("title", ""))
        excerpt = data.get("excerpt", item.get("excerpt", ""))
        if not isinstance(title, str) or len(title) > 150 or not isinstance(excerpt, str) or len(excerpt) > 2000:
            raise ApiError(400, "invalid_text", "标题最多 150 字，摘要最多 2000 字。")
        status = data.get("status", item.pop("status", "draft"))
        if status not in ("draft", "published", "archived"):
            raise ApiError(400, "invalid_status", "状态须为 draft、published 或 archived。")
        item.update(date=date, channel=channel, label=channel, title=title.strip() or f"{channel} · {date}", excerpt=excerpt.strip())
        item["searchText"] = " ".join((channel, date, item["title"], item["excerpt"]))
        return item, status

    def _images(self, images):
        if not images or len(images) > MAX_IMAGES:
            raise ApiError(400, "invalid_images", "每条内容请上传 1–20 张清晰图片。")
        upload_id = secrets.token_hex(16)
        temporary = Path(tempfile.mkdtemp(prefix="upload-", dir=self.data_dir))
        segments, filenames, total_height, max_width, total_pixels = [], [], 0, 0, 0
        try:
            for original_name, raw in images:
                if not raw or len(raw) > MAX_FILE:
                    raise ApiError(413, "image_too_large", "单张图片不能超过 20 MiB。")
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", Image.DecompressionBombWarning)
                        with Image.open(io.BytesIO(raw)) as probe:
                            if probe.format not in ("JPEG", "PNG", "WEBP") or getattr(probe, "n_frames", 1) != 1:
                                raise ValueError("unsupported format")
                            width, height = probe.size
                            total_pixels += width * height
                            if width < 1 or height < 1 or width > 12000 or height > 100000 or width*height > 60_000_000 or total_pixels > 150_000_000:
                                raise ValueError("image dimensions too large")
                            probe.verify()
                        with Image.open(io.BytesIO(raw)) as source:
                            oriented = ImageOps.exif_transpose(source)
                            oriented.load()
                            # New RGB pixels prevent EXIF/ICC/text metadata from being copied.
                            rgb = Image.new("RGB", oriented.size, "white")
                            if "A" in oriented.getbands():
                                rgb.paste(oriented.convert("RGB"), mask=oriented.getchannel("A"))
                            else:
                                rgb.paste(oriented.convert("RGB"))
                            if rgb.width > 2400:
                                rgb = rgb.resize((2400, max(1, round(rgb.height * 2400/rgb.width))), Image.Resampling.LANCZOS)
                            max_width = max(max_width, rgb.width)
                            total_height += rgb.height
                            for top in range(0, rgb.height, 4096):
                                bottom = min(top+4096, rgb.height)
                                filename = f"{len(segments)+1:03d}.jpg"
                                piece = rgb.crop((0, top, rgb.width, bottom))
                                piece.save(temporary / filename, "JPEG", quality=90, optimize=True)
                                segments.append({"uri": f"/media/{upload_id}/{filename}", "width": rgb.width, "height": bottom-top})
                    filenames.append(str(original_name).replace("\\", "/").rsplit("/", 1)[-1][:150])
                except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError):
                    raise ApiError(400, "invalid_image", "图片无法读取或尺寸过大；请上传完整的 JPG、PNG 或 WebP 图片。") from None
            destination = self.media_dir / upload_id
            temporary.replace(destination)
            return {"segments": segments, "width": max_width, "height": total_height,
                    "image": {"uri": segments[0]["uri"]}, "sourceFile": ", ".join(filenames)[:1000]}, destination
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def save_content(self, actor, data, images=None, content_id=None):
        destination = None
        try:
            with self._db() as db:
                row = db.execute("SELECT * FROM content WHERE id=?", (content_id,)).fetchone() if content_id else None
                if content_id and not row:
                    raise ApiError(404, "content_not_found", "内容不存在。")
                existing = json.loads(row["data"]) if row else {}
                existing["status"] = row["status"] if row else "draft"
                item, status = self._metadata(data, existing)
                if images is not None:
                    image_data, destination = self._images(images)
                    item.update(image_data)
                elif not row:
                    raise ApiError(400, "images_required", "请上传内容图片。")
                content_id = content_id or ("morning-" if item["channel"] == "晨修" else "mission-") + item["date"].replace("-", "") + "-" + secrets.token_hex(6)
                item["id"] = content_id
                stamp = _now()
                db.execute("INSERT INTO content(id,data,status,seeded,created_at,updated_at) VALUES (?,?,?,0,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,status=excluded.status,updated_at=excluded.updated_at",
                           (content_id, json.dumps(item, ensure_ascii=False), status, stamp, stamp))
                self._bump(db)
                self._audit(db, actor, "update_content" if row else "create_content", content_id, {"status": status, "title": item["title"], "replacedImages": images is not None})
                return {**item, "status": status, "seeded": bool(row["seeded"]) if row else False, "updatedAt": stamp}
        except BaseException:
            if destination:
                shutil.rmtree(destination, ignore_errors=True)
            raise

    @staticmethod
    def _public_news(
        data: dict,
        *,
        status: str | None = None,
        updated_at: str | None = None,
        needs_prayer: object = 0,
        prayer_excluded: object = 0,
    ) -> dict:
        item = {
            "id": data["id"],
            "kind": "news",
            "date": data["date"],
            "channel": NEWS_CHANNEL,
            "label": NEWS_CHANNEL,
            "title": data["title"],
            "excerpt": data["summary"],
            "summary": data["summary"],
            "sourceName": data["source_name"],
            "sourceUrl": data["source_url"],
            "publishedAt": data["published_at"],
            "region": data["region"],
            # Only a real JSON boolean true counts as verified. The string
            # "false", a missing field, or a numeric 1 must not look verified.
            "verified": data.get("verified") is True,
            "category": data["category"],
        }
        item["searchText"] = " ".join((
            NEWS_CHANNEL, item["date"], item["title"], item["summary"],
            item["sourceName"], item["region"], item["category"],
        ))
        if status is not None:
            item["status"] = status
            item["updatedAt"] = updated_at
            marked = _flag_on(needs_prayer)
            excluded = _flag_on(prayer_excluded)
            item["needsPrayer"] = marked
            item["prayerExcluded"] = excluded
            item["prayerCandidate"] = is_prayer_candidate(data)
            item["onPrayerPage"] = on_prayer_page(
                data, status=status, needs_prayer=needs_prayer, prayer_excluded=prayer_excluded,
            )
        return item

    def _normalize_news_item(self, raw: object, index: int) -> dict:
        label = f"第 {index + 1} 条"
        if not isinstance(raw, dict):
            raise ApiError(400, "invalid_news_item", f"{label}不是对象。")
        if any(key not in NEWS_FIELDS for key in raw):
            raise ApiError(400, "unknown_field", f"{label}包含不支持的字段。")
        if NEWS_FIELDS - raw.keys():
            raise ApiError(400, "invalid_news_item", f"{label}缺少必要字段。")
        title = _plain(raw.get("title"), minimum=1, maximum=MAX_NEWS_TITLE, code="invalid_text",
                       message=f"{label}标题须为 1–{MAX_NEWS_TITLE} 个字符。")
        summary = _plain(raw.get("summary"), minimum=1, maximum=MAX_NEWS_SUMMARY, code="invalid_text",
                         message=f"{label}摘要须为 1–{MAX_NEWS_SUMMARY} 个字符。")
        source_name = _plain(raw.get("source_name"), minimum=1, maximum=MAX_NEWS_SOURCE_NAME, code="invalid_text",
                             message=f"{label}来源名须为 1–{MAX_NEWS_SOURCE_NAME} 个字符。")
        region = _plain(raw.get("region"), minimum=1, maximum=MAX_NEWS_REGION, code="invalid_text",
                        message=f"{label}地区须为 1–{MAX_NEWS_REGION} 个字符。")
        category = raw.get("category")
        if not isinstance(category, str) or category.strip() not in NEWS_CATEGORIES:
            raise ApiError(400, "invalid_category", f"{label}不属于基督教、宗教宣教或教会相关。")
        if not isinstance(raw.get("verified"), bool):
            raise ApiError(400, "invalid_verified", f"{label}的 verified 须为布尔值。")
        source_url = _canonical_source_url(raw.get("source_url"))
        stamp = _published_stamp(raw.get("published_at"))
        return {
            "id": _news_id(stamp, source_url),
            "kind": "news",
            "title": title,
            "summary": summary,
            "source_url": source_url,
            "source_name": source_name,
            "published_at": stamp.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date": stamp.astimezone(dt.timezone.utc).date().isoformat(),
            "region": region,
            "verified": raw["verified"],
            "category": category.strip(),
            "channel": NEWS_CHANNEL,
        }

    def ingest_news(self, items: object) -> dict:
        """Insert a religious news batch as pending. Duplicates are ignored.

        Pending rows are not public and do not change the content version.
        """
        if not isinstance(items, list) or not items:
            raise ApiError(400, "invalid_batch", f"请一次提交 1–{MAX_NEWS_BATCH} 条宗教动态。")
        if len(items) > MAX_NEWS_BATCH:
            raise ApiError(400, "batch_too_large", f"单次最多提交 {MAX_NEWS_BATCH} 条宗教动态。")
        records = [self._normalize_news_item(item, index) for index, item in enumerate(items)]
        inserted: list[str] = []
        ignored: list[str] = []
        with self._db() as db:
            for record in records:
                db.execute(
                    "INSERT OR IGNORE INTO news(id,data,status,created_at,updated_at,needs_prayer,prayer_excluded) "
                    "VALUES (?,?,'pending',?,?,0,0)",
                    (record["id"], json.dumps(record, ensure_ascii=False), _now(), _now()),
                )
                if db.execute("SELECT changes()").fetchone()[0]:
                    inserted.append(record["id"])
                else:
                    ignored.append(record["id"])
            # Ids only: titles and URLs can carry untrusted text or query tokens.
            self._audit(db, "news-ingest", "ingest_news", None, {"inserted": inserted, "ignored": ignored})
        return {"inserted": inserted, "ignored": ignored}

    def review_news(self, actor: str, news_id: str, action: str) -> dict:
        if action not in ("publish", "reject"):
            raise ApiError(400, "invalid_action", "审核动作须为公开或驳回。")
        if not isinstance(news_id, str) or not re.fullmatch(r"news-[0-9]{8}-[a-f0-9]{12}", news_id):
            raise ApiError(404, "news_not_found", "动态不存在。")
        target = "published" if action == "publish" else "rejected"
        with self._db() as db:
            before = self._news_public_sets(db)
            row = db.execute("SELECT * FROM news WHERE id=?", (news_id,)).fetchone()
            if not row:
                raise ApiError(404, "news_not_found", "动态不存在。")
            previous = row["status"]
            stamp = row["updated_at"]
            if previous != target:
                stamp = _now()
                db.execute("UPDATE news SET status=?, updated_at=? WHERE id=?", (target, stamp, news_id))
            self._bump_if_news_public_changed(db, before)
            self._audit(db, actor, f"{action}_news", news_id, {"from": previous, "to": target})
            return self._public_news(
                json.loads(row["data"]),
                status=target,
                updated_at=stamp,
                needs_prayer=row["needs_prayer"],
                prayer_excluded=row["prayer_excluded"],
            )

    @staticmethod
    def _publishable_ids(db) -> list[str]:
        """Pending rows whose stored verified value is JSON true and nothing else."""
        rows = db.execute("SELECT id, data FROM news WHERE status='pending' ORDER BY id").fetchall()
        ids: list[str] = []
        for row in rows:
            try:
                data = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict) and data.get("verified") is True:
                ids.append(row["id"])
        return ids

    def news_listing(self, status: str | None = None) -> dict:
        if status is not None and status not in ("pending", "published", "rejected"):
            raise ApiError(400, "invalid_status", "状态须为 pending、published 或 rejected。")
        with self._db() as db:
            if status:
                rows = db.execute("SELECT * FROM news WHERE status=? ORDER BY created_at DESC, id DESC", (status,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM news ORDER BY created_at DESC, id DESC").fetchall()
            items = [
                self._public_news(
                    json.loads(row["data"]),
                    status=row["status"],
                    updated_at=row["updated_at"],
                    needs_prayer=row["needs_prayer"],
                    prayer_excluded=row["prayer_excluded"],
                )
                for row in rows
            ]
            return {"items": items, "publishable": len(self._publishable_ids(db))}

    def list_news(self, status: str | None = None) -> list[dict]:
        return self.news_listing(status)["items"]

    def publish_verified_news(self, actor: str, expected_count: int | None = None) -> dict:
        """Publish every pending item whose verified flag is JSON true.

        The select, status updates, single version bump, and audit insert share
        one database transaction. A mismatch or a later failure rolls all of
        them back. An empty set writes the audit row and leaves version as-is.
        """
        if expected_count is not None and (type(expected_count) is not int or expected_count < 0):
            raise ApiError(400, "invalid_expected_count", "期望条数须为非负整数。")
        with self._db() as db:
            before = self._news_public_sets(db)
            ids = self._publishable_ids(db)
            count = len(ids)
            if expected_count is not None and expected_count != count:
                raise ApiError(
                    409,
                    "count_mismatch",
                    f"待公开条数已变为 {count}，请重新确认。",
                    {"actual": count},
                )
            if count:
                stamp = _now()
                for news_id in ids:
                    db.execute(
                        "UPDATE news SET status='published', updated_at=? WHERE id=? AND status='pending'",
                        (stamp, news_id),
                    )
                    if db.execute("SELECT changes()").fetchone()[0] != 1:
                        raise ApiError(409, "count_mismatch", "待公开条目在写入时发生变化，请重新确认。")
            self._bump_if_news_public_changed(db, before)
            version = int(db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])
            self._audit(db, actor, "publish_verified_news", None, {"published": count, "ids": ids})
            return {"published": count, "version": version}

    def _require_news_row(self, db, news_id: str):
        if not isinstance(news_id, str) or not re.fullmatch(r"news-[0-9]{8}-[a-f0-9]{12}", news_id):
            raise ApiError(404, "news_not_found", "动态不存在。")
        row = db.execute("SELECT * FROM news WHERE id=?", (news_id,)).fetchone()
        if not row:
            raise ApiError(404, "news_not_found", "动态不存在。")
        return row

    def set_news_prayer(self, actor: str, news_id: str, needs_prayer: bool) -> dict:
        """Mark or clear the manual prayer flag.

        Setting the flag publishes a pending or rejected row in the same
        transaction and clears an exclusion, so the explicit action is visible.
        Clearing the flag does not unpublish and does not by itself block the
        keyword rule. Rows are never deleted.
        """
        if type(needs_prayer) is not bool:
            raise ApiError(400, "invalid_needs_prayer", "needs_prayer 须为布尔值。")
        with self._db() as db:
            before = self._news_public_sets(db)
            row = self._require_news_row(db, news_id)
            previous = row["status"]
            target = "published" if needs_prayer else previous
            excluded = 0 if needs_prayer else int(row["prayer_excluded"] or 0)
            flag = 1 if needs_prayer else 0
            stamp = row["updated_at"]
            changed = previous != target or int(row["needs_prayer"] or 0) != flag or int(row["prayer_excluded"] or 0) != excluded
            if changed:
                stamp = _now()
                db.execute(
                    "UPDATE news SET status=?, needs_prayer=?, prayer_excluded=?, updated_at=? WHERE id=?",
                    (target, flag, excluded, stamp, news_id),
                )
            self._bump_if_news_public_changed(db, before)
            if changed:
                self._audit(db, actor, "set_news_prayer", news_id, {
                    "needs_prayer": needs_prayer, "from": previous, "to": target,
                })
            version = int(db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])
            item = self._public_news(
                json.loads(row["data"]), status=target, updated_at=stamp,
                needs_prayer=flag, prayer_excluded=excluded,
            )
            return {"item": item, "version": version}

    def set_news_prayer_exclusion(self, actor: str, news_id: str, excluded: bool) -> dict:
        """Exclude or restore one row from automatic and manual prayer routing.

        Exclusion wins over the keyword rule and a manual mark, and puts a
        published row back on the news list. The news row is kept.
        """
        if type(excluded) is not bool:
            raise ApiError(400, "invalid_excluded", "excluded 须为布尔值。")
        with self._db() as db:
            before = self._news_public_sets(db)
            row = self._require_news_row(db, news_id)
            flag = 1 if excluded else 0
            stamp = row["updated_at"]
            changed = int(row["prayer_excluded"] or 0) != flag
            if changed:
                stamp = _now()
                db.execute(
                    "UPDATE news SET prayer_excluded=?, updated_at=? WHERE id=?",
                    (flag, stamp, news_id),
                )
            self._bump_if_news_public_changed(db, before)
            if changed:
                self._audit(db, actor, "set_news_prayer_exclusion", news_id, {"excluded": excluded})
            version = int(db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])
            item = self._public_news(
                json.loads(row["data"]),
                status=row["status"],
                updated_at=stamp,
                needs_prayer=row["needs_prayer"],
                prayer_excluded=flag,
            )
            return {"item": item, "version": version}

    def prayer_requests(self) -> dict:
        """Published rows routed to the prayer page. No admin fields."""
        with self._db() as db:
            db.execute("BEGIN")
            items = []
            rows = db.execute(
                "SELECT data, needs_prayer, prayer_excluded FROM news WHERE status='published'"
            ).fetchall()
            for row in rows:
                data = json.loads(row["data"])
                if not on_prayer_page(
                    data,
                    status="published",
                    needs_prayer=row["needs_prayer"],
                    prayer_excluded=row["prayer_excluded"],
                ):
                    continue
                items.append({
                    "id": data["id"],
                    "title": data["title"],
                    "summary": data["summary"],
                    "sourceName": data["source_name"],
                    "sourceUrl": data["source_url"],
                    "date": data["date"],
                    "region": data["region"],
                    "verified": data.get("verified") is True,
                })
            items.sort(key=lambda item: (item["date"], item["id"]), reverse=True)
            version = int(db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])
            return {"version": version, "items": items}

    def reader_prayer_items(self) -> list[dict]:
        """Reader-shaped copies of the public prayer feed. Not an admin payload."""
        items = []
        for item in self.prayer_requests()["items"]:
            items.append({
                "id": item["id"],
                "kind": "news",
                "date": item["date"],
                "channel": NEWS_CHANNEL,
                "label": "需要祷告",
                "title": item["title"],
                "excerpt": item["summary"],
                "summary": item["summary"],
                "sourceName": item["sourceName"],
                "sourceUrl": item["sourceUrl"],
                "region": item["region"],
                "verified": item["verified"],
                "category": "需要祷告",
            })
        return items


def create_admin_store(data_dir, seed_file=None, **kwargs):
    return AdminStore(data_dir, seed_file, **kwargs)


class AdminRequestMixin:
    """Call handle_admin_request first in GET/POST/PUT/PATCH handler methods."""
    def _api_json(self, status, payload, *, cookie=None, cache_control=None, etag=None, retry_after=None):
        if etag and self.headers.get("If-None-Match", "") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache_control or "no-store, private")
            self.end_headers()
            return
        # Escape HTML-sensitive characters in the JSON text so a response
        # cannot break out of a surrounding page. Parsers restore the original
        # characters; readers still escape again when rendering HTML.
        raw = (json.dumps(payload, ensure_ascii=False)
               .replace("&", "\\u0026")
               .replace("<", "\\u003c")
               .replace(">", "\\u003e")
               .encode("utf-8"))
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", cache_control or "no-store, private")
        if etag:
            self.send_header("ETag", etag)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if status == 429:
            self.send_header("Retry-After", retry_after or "900")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _session_cookie(self, token, *, clear=False):
        store = self.server.admin_store
        value = f"{COOKIE_NAME}={token}; Path=/api/admin; HttpOnly; SameSite=Strict; Max-Age={0 if clear else SESSION_SECONDS}"
        if store.secure_cookies:
            value += "; Secure"
        return value

    def _token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            return cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ""
        except Exception:
            return ""

    def _same_origin(self, *, required=False):
        origin = self.headers.get("Origin")
        if not origin:
            if required:
                raise ApiError(403, "invalid_origin", "请从本站管理员入口登录。")
            return
        parsed = urlsplit(origin)
        if parsed.scheme not in ("https", "http") or parsed.netloc.lower() != self.headers.get("Host", "").lower() or parsed.path or parsed.query or parsed.fragment:
            raise ApiError(403, "invalid_origin", "请求来源不受允许。")

    def _body(self, *, max_bytes: int | None = None):
        if self.headers.get("Transfer-Encoding"):
            raise ApiError(400, "unsupported_transfer", "不支持此上传方式。")
        try:
            size = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            size = -1
        if size < 0:
            raise ApiError(411, "length_required", "请求缺少长度。")
        if size > MAX_BODY or (max_bytes is not None and size > max_bytes):
            self.close_connection = True
            if max_bytes is not None and size <= MAX_BODY:
                raise ApiError(413, "request_too_large", "请求体超过允许大小。")
            raise ApiError(413, "request_too_large", "每次上传总计不能超过 60 MiB。")
        self.connection.settimeout(30)
        try:
            raw = self.rfile.read(size)
        except (TimeoutError, OSError):
            self.close_connection = True
            raise ApiError(408, "request_timeout", "上传超时，请重试。") from None
        if len(raw) != size:
            raise ApiError(400, "incomplete_request", "上传未完成，请重试。")
        return raw

    def _json_body(self, *, max_bytes: int = 64 * 1024):
        if self.headers.get_content_type() != "application/json":
            raise ApiError(415, "json_required", "请求须为 JSON。")
        raw = self._body(max_bytes=max_bytes)
        if len(raw) > max_bytes:
            raise ApiError(413, "request_too_large", "内容字段过长。")
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, UnicodeError):
            raise ApiError(400, "invalid_json", "JSON 格式不正确。") from None

    def _multipart(self):
        if self.headers.get_content_type() != "multipart/form-data":
            raise ApiError(415, "multipart_required", "图片须以 multipart/form-data 上传。")
        content_type = self.headers.get("Content-Type", "")
        if "\r" in content_type or "\n" in content_type or len(content_type) > 500:
            raise ApiError(400, "invalid_multipart", "上传格式不正确。")
        raw = self._body()
        message = BytesParser(policy=policy.default).parsebytes(("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + raw)
        if not message.is_multipart() or message.defects:
            raise ApiError(400, "invalid_multipart", "上传格式不正确。")
        fields, images = {}, []
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            filename = part.get_filename()
            value = part.get_payload(decode=True)
            if part.defects or not isinstance(value, bytes):
                raise ApiError(400, "invalid_multipart", "上传格式不正确。")
            if filename is not None:
                if name not in ("images", "images[]"):
                    raise ApiError(400, "invalid_image_field", "图片字段须为 images。")
                images.append((filename, value))
                if len(images) > MAX_IMAGES:
                    raise ApiError(400, "invalid_images", "每条内容最多上传 20 张图片。")
            else:
                if name in fields or name not in {"date", "channel", "title", "excerpt", "status"} or len(value) > 10000:
                    raise ApiError(400, "invalid_field", "内容字段不正确或过长。")
                try:
                    fields[name] = value.decode("utf-8")
                except UnicodeError:
                    raise ApiError(400, "invalid_text", "文字须为 UTF-8。") from None
        return fields, images

    def _bearer_token(self) -> str | None:
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not isinstance(header, str) or len(header) > MAX_INGEST_KEY + len(prefix) or not header.startswith(prefix):
            return None
        token = header[len(prefix):]
        if not token or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in token):
            return None
        return token

    def _ingest_news(self, store: AdminStore) -> None:
        if self.command != "POST":
            raise ApiError(405, "method_not_allowed", "此接口仅接受提交。")
        limiter = getattr(self.server, "ingest_limiter", None)
        if limiter is None:
            limiter = IngestLimiter()
            self.server.ingest_limiter = limiter
        identity = str(self.headers.get("CF-Connecting-IP") or self.client_address[0])[:100]
        if not limiter.allow(identity):
            raise ApiError(429, "ingest_rate_limited", "提交过于频繁，请稍后再试。")
        expected = resolve_ingest_key()
        if not expected:
            raise ApiError(404, "not_found", "接口不存在。")
        provided = self._bearer_token()
        # Compare before reading the body so a wrong key does not need the payload,
        # but still after the rate limit so guesses are capped. The key is not logged.
        if provided is None or not _keys_equal(provided, expected):
            self.close_connection = True
            raise ApiError(401, "invalid_ingest_key", "提交密钥无效。")
        data = self._json_body(max_bytes=MAX_INGEST_BODY)
        if any(key != "items" for key in data):
            raise ApiError(400, "unknown_field", "请求只接受 items 数组。")
        self._api_json(200, store.ingest_news(data.get("items")))

    def handle_admin_request(self):
        path = urlsplit(self.path).path
        if path == "/api/ingest/news":
            try:
                opened = resolve_ingest_key() is not None
            except ApiError:
                opened = True
            if not opened:
                return False
        if not (path == "/api/content" or path == "/api/prayer-requests" or path.startswith("/api/admin/") or path == "/api/admin" or path == "/api/ingest/news"):
            return False
        try:
            # Ingest uses its own limiter so a submitting bot cannot consume
            # the administrator write budget, and the reverse is also true.
            if self.command not in ("GET", "HEAD") and path != "/api/ingest/news":
                limiter = getattr(self.server, "request_limiter", None)
                if limiter is not None:
                    identity = self.headers.get("CF-Connecting-IP") or self.client_address[0]
                    if not limiter.allow(str(identity)[:100]):
                        raise ApiError(429, "write_rate_limited", "操作过于频繁，请稍后再试。")
            self._handle_admin_api(path)
        except ApiError as error:
            # Close rejected uploads so unread request bodies cannot become a new request.
            if self.command not in ("GET", "HEAD"):
                self.close_connection = True
            retry_after = "600" if error.code == "ingest_rate_limited" else None
            payload = {"error": error.code, "message": error.message}
            for key, value in error.extra.items():
                if key not in payload:
                    payload[key] = value
            self._api_json(error.status, payload, retry_after=retry_after)
        except Exception:
            self.close_connection = True
            self.log_error("Administration request failed (%s)", path)
            self._api_json(500, {"error": "internal_error", "message": "服务暂时无法完成操作，请重试。"})
        return True

    def _handle_admin_api(self, path):
        store = self.server.admin_store
        method, token = self.command, self._token()
        if path == "/api/ingest/news":
            self._ingest_news(store)
            return
        if path == "/api/content":
            if method not in ("GET", "HEAD"):
                raise ApiError(405, "method_not_allowed", "此接口仅支持读取。")
            payload = store.content(public=True)
            self._api_json(
                200, payload,
                cache_control=PUBLIC_FEED_CACHE_CONTROL,
                etag=feed_etag("content", payload["version"], payload["items"]),
            )
            return
        if path == "/api/prayer-requests":
            if method not in ("GET", "HEAD"):
                raise ApiError(405, "method_not_allowed", "此接口仅支持读取。")
            payload = store.prayer_requests()
            self._api_json(
                200, payload,
                cache_control=PUBLIC_FEED_CACHE_CONTROL,
                etag=feed_etag("prayer-requests", payload["version"], payload["items"]),
            )
            return
        if path == "/api/admin/login" and method == "POST":
            self._same_origin(required=True)
            data = self._json_body()
            ip = self.client_address[0]
            if ip in ("127.0.0.1", "::1"):
                ip = self.headers.get("CF-Connecting-IP", ip)[:100]
            new_token, result = store.login(data.get("username"), data.get("password"), ip)
            self._api_json(200, result, cookie=self._session_cookie(new_token))
            return
        session = store.session(token)
        user = session["user"]
        if method not in ("GET", "HEAD"):
            self._same_origin()
            csrf = self.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(csrf.encode(), session["csrfToken"].encode()):
                raise ApiError(403, "invalid_csrf", "登录状态已更新，请刷新管理员页面。")
        if path == "/api/admin/session" and method in ("GET", "HEAD"):
            self._api_json(200, session)
            return
        if path == "/api/admin/logout" and method == "POST":
            store.logout(token)
            self._api_json(200, {"ok": True}, cookie=self._session_cookie("", clear=True))
            return
        if path == "/api/admin/password" and method == "POST":
            data = self._json_body()
            result = store.change_password(user["id"], data.get("currentPassword"), data.get("newPassword"), token)
            self._api_json(200, result)
            return
        if user["mustChangePassword"]:
            raise ApiError(403, "password_change_required", "首次登录或密码重置后，请先修改临时密码。")
        if path == "/api/admin/content" and method in ("GET", "HEAD"):
            self._api_json(200, store.content())
            return
        content_match = re.fullmatch(r"/api/admin/content/([A-Za-z0-9_-]{1,150})", path)
        if path == "/api/admin/content" and method == "POST":
            fields, images = self._multipart()
            if fields.get("status") == "archived":
                raise ApiError(400, "invalid_status", "新建内容请选择草稿或发布。")
            self._api_json(201, {"item": store.save_content(user["id"], fields, images)})
            return
        if content_match and method in ("PUT", "POST"):
            if method == "PUT":
                fields, images = self._json_body(), None
            else:
                fields, images = self._multipart()
            self._api_json(200, {"item": store.save_content(user["id"], fields, images, content_match.group(1))})
            return
        if path == "/api/admin/news" and method in ("GET", "HEAD"):
            pairs = parse_qsl(urlsplit(self.path).query, keep_blank_values=True)
            if len(pairs) > 1 or any(key != "status" for key, _ in pairs):
                raise ApiError(400, "invalid_query", "查询参数不正确。")
            status = pairs[0][1] if pairs else None
            if status == "":
                status = None
            self._api_json(200, store.news_listing(status))
            return
        if path == "/api/admin/news/publish-verified" and method == "POST":
            data = self._json_body()
            if any(key != "expected_count" for key in data):
                raise ApiError(400, "unknown_field", "批量公开只接受期望条数。")
            expected = None
            if "expected_count" in data:
                expected = data["expected_count"]
                if type(expected) is not int or expected < 0:
                    raise ApiError(400, "invalid_expected_count", "期望条数须为非负整数。")
            self._api_json(200, store.publish_verified_news(user["id"], expected))
            return
        prayer_match = re.fullmatch(r"/api/admin/news/(news-[0-9]{8}-[a-f0-9]{12})/prayer", path)
        if prayer_match and method == "POST":
            data = self._json_body()
            if set(data) != {"needs_prayer"}:
                raise ApiError(400, "unknown_field", "祷告标记只接受 needs_prayer。")
            self._api_json(200, store.set_news_prayer(user["id"], prayer_match.group(1), data.get("needs_prayer")))
            return
        exclusion_match = re.fullmatch(r"/api/admin/news/(news-[0-9]{8}-[a-f0-9]{12})/prayer-exclusion", path)
        if exclusion_match and method == "POST":
            data = self._json_body()
            if set(data) != {"excluded"}:
                raise ApiError(400, "unknown_field", "排除标记只接受 excluded。")
            self._api_json(200, store.set_news_prayer_exclusion(user["id"], exclusion_match.group(1), data.get("excluded")))
            return
        news_match = re.fullmatch(r"/api/admin/news/(news-[0-9]{8}-[a-f0-9]{12})/(publish|reject)", path)
        if news_match and method == "POST":
            if self._json_body():
                raise ApiError(400, "unknown_field", "审核请求不接受额外字段。")
            action = "publish" if news_match.group(2) == "publish" else "reject"
            self._api_json(200, {"item": store.review_news(user["id"], news_match.group(1), action)})
            return
        if path == "/api/admin/users" or path.startswith("/api/admin/users/"):
            if user["role"] != "admin":
                raise ApiError(403, "admin_required", "仅管理员可以管理同工帐号。")
            if path == "/api/admin/users" and method in ("GET", "HEAD"):
                self._api_json(200, {"users": store.users()})
                return
            if path == "/api/admin/users" and method == "POST":
                self._api_json(201, {"user": store.create_user(user["id"], self._json_body())})
                return
            match = re.fullmatch(r"/api/admin/users/([a-f0-9]{24})", path)
            if match and method == "PATCH":
                self._api_json(200, {"user": store.update_user(user["id"], match.group(1), self._json_body())})
                return
        raise ApiError(404, "not_found", "接口不存在。")


def main():
    parser = argparse.ArgumentParser(description="Create the first prayer-site administrator; never reset an existing account.")
    parser.add_argument("command", choices=("bootstrap",))
    parser.add_argument("--data-directory", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-file", help="UTF-8 secret file; omit or use - to read stdin")
    args = parser.parse_args()
    secret = Path(args.password_file).read_text(encoding="utf-8-sig") if args.password_file and args.password_file != "-" else sys.stdin.read()
    # A single trailing line ending is convenient for a secret file without
    # silently removing intentional spaces from a password.
    secret = secret.removesuffix("\n").removesuffix("\r")
    try:
        created = AdminStore(args.data_directory).bootstrap(args.username, secret)
    except ApiError as error:
        print(error.message, file=sys.stderr)
        return 1
    print("Initial administrator created; password change required." if created else "Accounts already exist; nothing changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
