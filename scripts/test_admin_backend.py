#!/usr/bin/env python3
"""Focused regression tests for admin persistence and upload safety.

Run with ``python -m unittest scripts.test_admin_backend``.
"""
from __future__ import annotations

import hashlib
import http.client
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts import admin_backend
from scripts.admin_backend import AdminRequestMixin, AdminStore, ApiError, IngestLimiter


def jpeg(width=20, height=9000):
    output = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(output, "JPEG")
    return output.getvalue()


class AdminStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.seed = root / "seed.json"
        self.seed.write_text(json.dumps({"items": [{
            "id": "morning-2026-01-01", "date": "2026-01-01", "channel": "晨修",
            "title": "原始标题", "segments": [{"uri": "/assets/a.jpg", "width": 1, "height": 1}],
        }]}, ensure_ascii=False), encoding="utf-8")
        self.data = root / "private"
        self.store = AdminStore(self.data, self.seed, secure_cookies=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_survives_restart_and_live_override(self):
        self.assertTrue(self.store.bootstrap("admin", "temporary-pass-1"))
        token, login = self.store.login("admin", "temporary-pass-1", "127.0.0.1")
        changed = self.store.change_password(login["user"]["id"], "temporary-pass-1", "permanent-pass-1", token)
        self.assertFalse(changed["user"]["mustChangePassword"])
        item = self.store.save_content(login["user"]["id"], {"title": "已审核标题", "status": "published"}, None, "morning-2026-01-01")
        self.assertEqual(item["title"], "已审核标题")
        restarted = AdminStore(self.data, self.seed, secure_cookies=False)
        self.assertEqual(restarted.public_items()[0]["title"], "已审核标题")

    def test_upload_is_reencoded_and_segmented(self):
        self.store.bootstrap("admin", "temporary-pass-1")
        token, login = self.store.login("admin", "temporary-pass-1", "10.0.0.2")
        item = self.store.save_content(login["user"]["id"], {
            "date": "2026-02-02", "channel": "morning", "status": "draft",
        }, [("nested/evil.jpg", jpeg())])
        self.assertEqual(item["channel"], "晨修")
        self.assertGreater(len(item["segments"]), 1)
        self.assertTrue(all(segment["height"] <= 4096 for segment in item["segments"]))
        self.assertTrue(all((self.store.media_dir / Path(segment["uri"]).relative_to("/media")).is_file() for segment in item["segments"]))

    def test_bad_image_and_last_admin_protection(self):
        self.store.bootstrap("admin", "temporary-pass-1")
        with self.assertRaises(ApiError) as error:
            self.store.save_content("x", {"date": "2026-02-02", "channel": "mission"}, [("x.jpg", b"not-an-image")])
        self.assertEqual(error.exception.code, "invalid_image")
        _, login = self.store.login("admin", "temporary-pass-1", "127.0.0.1")
        with self.assertRaises(ApiError) as error:
            self.store.update_user(login["user"]["id"], login["user"]["id"], {"active": False})
        self.assertEqual(error.exception.code, "cannot_disable_self")


SECRET = "ingest-test-key-0001"
OTHER_SECRET = "ingest-test-key-0002"


def news_payload(**overrides):
    item = {
        "title": "教会周报",
        "summary": "短摘要，不含全文。",
        "source_url": "https://example.com/church/weekly",
        "source_name": "教会通讯",
        "published_at": "2026-10-27T08:00:00Z",
        "region": "全球",
        "verified": False,
        "category": "基督教",
    }
    item.update(overrides)
    return item


class Handler(AdminRequestMixin, BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if not self.handle_admin_request():
            self.send_error(404)

    def do_HEAD(self):  # noqa: N802
        if not self.handle_admin_request():
            self.send_error(404)

    def do_POST(self):  # noqa: N802
        if not self.handle_admin_request():
            self.send_error(404)

    def log_message(self, fmt, *args):
        rendered = fmt % args if args else fmt
        if SECRET in str(rendered) or OTHER_SECRET in str(rendered):
            raise AssertionError("ingest key was written to the HTTP log")


def start_server(store, *, limit=100):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.admin_store = store
    httpd.ingest_limiter = IngestLimiter(limit=limit, window_seconds=600)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def request(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    raw = None if body is None else body if isinstance(body, bytes) else json.dumps(body).encode()
    header_map = dict(headers or {})
    if raw is not None and "Content-Type" not in header_map:
        header_map["Content-Type"] = "application/json"
    connection.request(method, path, body=raw, headers=header_map)
    response = connection.getresponse()
    payload = response.read()
    status = response.status
    connection.close()
    return status, payload


def without_ingest_config():
    return patch.dict(os.environ, {admin_backend.INGEST_KEY_ENV: "", admin_backend.INGEST_KEY_FILE_ENV: ""}, clear=False)


class NewsIngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "private"
        self.store = AdminStore(self.data, secure_cookies=False)
        self.missing_key = Path(self.tmp.name) / "missing.key"
        self.switch_file = Path(self.tmp.name) / "switches.env"
        self.key_patch = patch.object(admin_backend, "DEFAULT_INGEST_KEY_FILE", self.missing_key)
        self.key_patch.start()
        self.switch_patch = patch.object(admin_backend, "NEWS_SWITCH_FILE", self.switch_file)
        self.switch_patch.start()
        self.env_patch = without_ingest_config()
        self.env_patch.start()
        self.flag_patch = patch.dict(os.environ, {
            admin_backend.AUTO_PUBLISH_VERIFIED_ENV: "",
            admin_backend.SHOW_PUBLISH_VERIFIED_BUTTON_ENV: "",
        }, clear=False)
        self.flag_patch.start()

    def tearDown(self):
        self.flag_patch.stop()
        self.env_patch.stop()
        self.switch_patch.stop()
        self.key_patch.stop()
        self.tmp.cleanup()

    def test_pending_news_is_hidden_until_publish_and_deduplicated(self):
        self.store.bootstrap("admin", "temporary-pass-1")
        _, login = self.store.login("admin", "temporary-pass-1", "127.0.0.1")
        with self.store._db() as db:
            db.execute(
                "INSERT INTO content VALUES (?,?,?,0,'now','now')",
                ("morning-fixed", json.dumps({"id": "morning-fixed", "date": "2026-01-01", "channel": "晨修", "title": "原图片"}), "published"),
            )
            before = db.execute("SELECT id, data, status FROM content").fetchall()
            version = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0]
        created = self.store.ingest_news([news_payload(title="教会周报 <script>")])
        self.assertEqual(len(created["inserted"]), 1)
        self.assertEqual(created["ignored"], [])
        self.assertTrue(created["inserted"][0].startswith("news-20261027-"))
        self.assertEqual(len(created["inserted"][0].rsplit("-", 1)[-1]), 12)
        again = self.store.ingest_news([news_payload(source_url="https://example.com/church/weekly#section")])
        self.assertEqual(again["inserted"], [])
        self.assertEqual(again["ignored"], created["inserted"])
        other_day = self.store.ingest_news([news_payload(published_at="2026-10-28")])
        self.assertEqual(len(other_day["inserted"]), 1)
        self.assertNotEqual(other_day["inserted"][0], created["inserted"][0])
        public = self.store.content(public=True)
        self.assertEqual(public["version"], version)
        self.assertEqual([item["id"] for item in public["items"]], ["morning-fixed"])
        self.assertTrue(all(item.get("kind") != "news" for item in self.store.content()["items"]))
        rejected = self.store.review_news(login["user"]["id"], other_day["inserted"][0], "reject")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(self.store.content(public=True)["version"], version)
        self.assertNotIn(other_day["inserted"][0], {item["id"] for item in self.store.public_items()})
        published = self.store.review_news(login["user"]["id"], created["inserted"][0], "publish")
        self.assertEqual(published["status"], "published")
        self.assertFalse(published["verified"])
        self.assertEqual(published["sourceUrl"], "https://example.com/church/weekly")
        after_publish = self.store.content(public=True)
        self.assertEqual(after_publish["version"], version + 1)
        news = next(item for item in after_publish["items"] if item["id"] == created["inserted"][0])
        self.assertEqual(news["channel"], "宗教动态")
        self.assertNotIn("status", news)
        self.assertEqual(self.store.review_news(login["user"]["id"], created["inserted"][0], "publish")["status"], "published")
        self.assertEqual(self.store.content(public=True)["version"], version + 1)
        self.store.review_news(login["user"]["id"], created["inserted"][0], "reject")
        self.assertEqual(self.store.content(public=True)["version"], version + 2)
        self.assertNotIn(created["inserted"][0], {item["id"] for item in self.store.public_items()})
        with self.store._db() as db:
            self.assertEqual([tuple(row) for row in db.execute("SELECT id, data, status FROM content")], [tuple(row) for row in before])
            details = [row[0] for row in db.execute("SELECT detail FROM audit")]
            actions = [row[0] for row in db.execute("SELECT action FROM audit")]
        self.assertNotIn(SECRET, " ".join(details))
        self.assertIn("ingest_news", actions)

    def test_invalid_nonreligious_and_oversized_batches_are_rejected_whole(self):
        cases = [
            news_payload(category="财经"),
            news_payload(category="AI"),
            news_payload(category="安全"),
            news_payload(summary="摘" * 401),
            news_payload(title="题" * 121),
            news_payload(source_url="javascript:alert(1)"),
            news_payload(source_url="file:///etc/passwd"),
            news_payload(source_url="http://user:pass@example.com/a"),
            news_payload(verified="false"),
            {**news_payload(), "body": "转载全文"},
        ]
        for item in cases:
            with self.subTest(item=item.get("category", item.get("source_url", "field"))), self.assertRaises(ApiError):
                self.store.ingest_news([news_payload(), item] if item.get("category") in {"财经", "AI", "安全"} else [item])
        with self.assertRaises(ApiError) as too_many:
            self.store.ingest_news([news_payload(source_url=f"https://example.com/{index}") for index in range(31)])
        self.assertEqual(too_many.exception.code, "batch_too_large")
        self.assertEqual(self.store.list_news(), [])

    def test_http_ingest_requires_dedicated_key_and_hides_pending_text(self):
        os.environ.pop(admin_backend.INGEST_KEY_ENV, None)
        os.environ.pop(admin_backend.INGEST_KEY_FILE_ENV, None)
        httpd = start_server(self.store)
        try:
            status, _ = request(httpd.server_address[1], "POST", "/api/ingest/news", {"items": [news_payload()]})
            self.assertEqual(status, 404)
            os.environ[admin_backend.INGEST_KEY_FILE_ENV] = str(self.missing_key)
            status, payload = request(httpd.server_address[1], "POST", "/api/ingest/news", {"items": [news_payload()]},
                                      {"Authorization": "Bearer " + SECRET})
            self.assertEqual(status, 503)
            self.assertNotIn(SECRET, payload.decode())
            os.environ.pop(admin_backend.INGEST_KEY_FILE_ENV, None)
            key_file = Path(self.tmp.name) / "ingest.key"
            key_file.write_text(OTHER_SECRET + "\n", encoding="utf-8")
            with patch.object(admin_backend, "DEFAULT_INGEST_KEY_FILE", key_file):
                status, _ = request(httpd.server_address[1], "POST", "/api/ingest/news", {"items": [news_payload()]},
                                    {"Authorization": "Bearer " + SECRET})
                self.assertEqual(status, 401)
                os.environ[admin_backend.INGEST_KEY_ENV] = SECRET
                status, payload = request(httpd.server_address[1], "POST", "/api/ingest/news", {"items": [news_payload(title="<script>alert(1)</script>")]},
                                          {"Authorization": "Bearer " + SECRET, "Cookie": "prayer_admin_session=not-a-session"})
            self.assertEqual(status, 200)
            body = json.loads(payload)
            self.assertEqual(len(body["inserted"]), 1)
            self.assertNotIn(SECRET, payload.decode())
            status, public = request(httpd.server_address[1], "GET", "/api/content")
            self.assertEqual(status, 200)
            self.assertNotIn(body["inserted"][0], public.decode())
            self.store.bootstrap("admin", "temporary-pass-1")
            token, login = self.store.login("admin", "temporary-pass-1", "127.0.0.1")
            session = self.store.change_password(login["user"]["id"], "temporary-pass-1", "permanent-pass-1", token)
            port = httpd.server_address[1]
            headers = {
                "Origin": f"http://127.0.0.1:{port}",
                "Cookie": "prayer_admin_session=" + token,
                "X-CSRF-Token": session["csrfToken"],
            }
            bad_origin = dict(headers, Origin="https://evil.example")
            status, _ = request(port, "POST", f"/api/admin/news/{body['inserted'][0]}/publish", {}, bad_origin)
            self.assertEqual(status, 403)
            missing_csrf = dict(headers)
            missing_csrf.pop("X-CSRF-Token")
            status, _ = request(port, "POST", f"/api/admin/news/{body['inserted'][0]}/publish", {}, missing_csrf)
            self.assertEqual(status, 403)
            status, published = request(port, "POST", f"/api/admin/news/{body['inserted'][0]}/publish", {}, headers)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(published)["item"]["status"], "published")
            status, public = request(port, "GET", "/api/content")
            text = public.decode()
            self.assertIn(body["inserted"][0], text)
            self.assertNotIn("<script>", text)
            self.assertIn("\\u003c", text)
            editor = self.store.create_user(login["user"]["id"], {"username": "editor1", "password": "temporary-pass-2", "role": "editor"})
            editor_token, editor_login = self.store.login("editor1", "temporary-pass-2", "10.0.0.8")
            self.assertNotEqual(editor["role"], "admin")
            status, denied = request(port, "POST", f"/api/admin/news/{body['inserted'][0]}/reject", {}, {
                "Origin": headers["Origin"], "Cookie": "prayer_admin_session=" + editor_token,
                "X-CSRF-Token": editor_login["csrfToken"],
            })
            self.assertEqual(status, 403)
            self.assertEqual(json.loads(denied)["error"], "password_change_required")
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_http_limits_body_batch_and_rate(self):
        os.environ[admin_backend.INGEST_KEY_ENV] = SECRET
        httpd = start_server(self.store, limit=4)
        port = httpd.server_address[1]
        headers = {"Authorization": "Bearer " + SECRET}
        try:
            status, payload = request(port, "POST", "/api/ingest/news", {"items": [news_payload(category="财经")]}, headers)
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(payload)["error"], "invalid_category")
            oversized = b'{"items":[]}' + b" " * 70000
            status, _ = request(port, "POST", "/api/ingest/news", oversized, headers)
            self.assertEqual(status, 413)
            self.assertEqual(self.store.list_news(), [])
            status, _ = request(port, "POST", "/api/ingest/news", {"items": [news_payload()]}, headers)
            self.assertEqual(status, 200)
            status, second = request(port, "POST", "/api/ingest/news", {"items": [news_payload()]}, headers)
            self.assertEqual(status, 200)
            self.assertEqual(len(json.loads(second)["ignored"]), 1)
            status, limited = request(port, "POST", "/api/ingest/news", {"items": [news_payload()]}, headers)
            self.assertEqual(status, 429)
            self.assertEqual(json.loads(limited)["error"], "ingest_rate_limited")
            self.assertNotIn(SECRET, limited.decode())
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_verified_batch_auto_publishes_once_and_routes_persecution(self):
        before = self._version()
        created = self.store.ingest_news([
            news_payload(verified=True, title="已核实周报", source_url="https://example.com/auto-home", published_at="2026-10-27T08:00:00Z"),
            news_payload(verified=True, title="另一条已核实", source_url="https://example.com/auto-home-2", published_at="2026-10-26T08:00:00Z"),
            news_payload(verified=False, title="未核实周报", source_url="https://example.com/auto-pending"),
            news_payload(verified=True, title="信徒遭监禁", summary="需要代祷", source_url="https://example.com/auto-prayer", published_at="2026-10-28T08:00:00Z"),
        ])
        home_a, home_b, pending_id, prayer_id = created["inserted"]
        self.assertEqual(created["ignored"], [])
        self.assertEqual(created["published"], [home_a, home_b, prayer_id])
        self.assertEqual(self._version(), before + 1)
        self.assertEqual(self._statuses()[pending_id], "pending")
        public_ids = {item["id"] for item in self.store.content(public=True)["items"]}
        self.assertIn(home_a, public_ids)
        self.assertIn(home_b, public_ids)
        self.assertNotIn(pending_id, public_ids)
        self.assertNotIn(prayer_id, public_ids)
        prayers = self.store.prayer_requests()
        self.assertEqual([item["id"] for item in prayers["items"]], [prayer_id])
        self.assertTrue(prayers["items"][0]["verified"] is True)
        self.assertEqual(prayers["version"], before + 1)
        with self.store._db() as db:
            detail = db.execute("SELECT detail FROM audit WHERE action='ingest_news'").fetchone()[0]
        self.assertIn("auto-publish by ingest", detail)
        self.assertNotIn("未核实周报", detail)
        self.assertNotIn("https://example.com/auto-home", detail)

    def test_auto_publish_etag_follows_version_and_returned_ids(self):
        httpd = start_server(self.store)
        port = httpd.server_address[1]
        try:
            status, headers, body = request_response(port, "GET", "/api/content")
            self.assertEqual(status, 200)
            before_etag = headers["etag"]
            before_version = json.loads(body)["version"]
            created = self.store.ingest_news([
                news_payload(verified=True, title="首页动态", source_url="https://example.com/etag-home"),
            ])
            news_id = created["published"][0]
            self.assertEqual(created["inserted"], [news_id])
            status, headers, body = request_response(port, "GET", "/api/content")
            payload = json.loads(body)
            self.assertEqual(payload["version"], before_version + 1)
            self.assertIn(news_id, {item["id"] for item in payload["items"]})
            self.assertNotEqual(headers["etag"], before_etag)
            self.assertEqual(headers["etag"], admin_backend.feed_etag("content", payload["version"], payload["items"]))
            legacy = f'"content-{payload["version"]}"'
            self.assertNotEqual(headers["etag"], legacy)
            status, hit_headers, hit_body = request_response(
                port, "GET", "/api/content", headers={"If-None-Match": headers["etag"]},
            )
            self.assertEqual(status, 304)
            self.assertEqual(hit_body, b"")
            self.assertEqual(hit_headers["etag"], headers["etag"])
            self.assertEqual(hit_headers["cache-control"], admin_backend.PUBLIC_FEED_CACHE_CONTROL)
            status, missed_headers, missed_body = request_response(
                port, "GET", "/api/content", headers={"If-None-Match": legacy},
            )
            self.assertEqual(status, 200)
            self.assertEqual(missed_headers["etag"], headers["etag"])
            self.assertIn(news_id, missed_body.decode())
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_switch_off_keeps_verified_pending_until_the_next_request_enables_it(self):
        for token in ("0", "false", "off", "OFF", " false ", '"0"'):
            os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = token
            self.assertFalse(admin_backend.auto_publish_verified_enabled(), token)
        os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = "0"
        before = self._version()
        created = self.store.ingest_news([
            news_payload(verified=True, source_url="https://example.com/switch-off"),
            news_payload(verified=False, source_url="https://example.com/switch-off-plain"),
        ])
        pending_id = created["inserted"][0]
        self.assertEqual(created["published"], [])
        self.assertEqual(self._statuses()[pending_id], "pending")
        self.assertEqual(self._version(), before)
        os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = "1"
        repeated = self.store.ingest_news([news_payload(verified=True, title="改写标题", source_url="https://example.com/switch-off")])
        self.assertEqual(repeated["inserted"], [])
        self.assertEqual(repeated["ignored"], [pending_id])
        self.assertEqual(repeated["published"], [])
        self.assertEqual(self._statuses()[pending_id], "pending")
        self.assertEqual(self._version(), before)
        with self.store._db() as db:
            stored = json.loads(db.execute("SELECT data FROM news WHERE id=?", (pending_id,)).fetchone()[0])
        self.assertEqual(stored["title"], "教会周报")
        opened = self.store.ingest_news([news_payload(verified=True, source_url="https://example.com/switch-on")])
        self.assertEqual(opened["published"], opened["inserted"])
        self.assertEqual(self._statuses()[pending_id], "pending")
        self.assertEqual(self._version(), before + 1)
        os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = "maybe"
        self.assertTrue(admin_backend.auto_publish_verified_enabled())

    def test_switch_file_overrides_environment_without_restart(self):
        os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = "1"
        os.environ[admin_backend.SHOW_PUBLISH_VERIFIED_BUTTON_ENV] = "1"
        self.switch_file.write_text(
            "# live override\nexport NEWS_AUTO_PUBLISH_VERIFIED=0\nNEWS_SHOW_PUBLISH_VERIFIED_BUTTON=off\n",
            encoding="utf-8",
        )
        self.assertFalse(admin_backend.auto_publish_verified_enabled())
        created = self.store.ingest_news([news_payload(verified=True, source_url="https://example.com/file-off")])
        self.assertEqual(created["published"], [])
        self.assertEqual(self._statuses()[created["inserted"][0]], "pending")
        self.assertIs(self.store.news_listing()["showPublishVerified"], False)
        self.switch_file.write_text(
            "NEWS_AUTO_PUBLISH_VERIFIED='on'\nNEWS_SHOW_PUBLISH_VERIFIED_BUTTON=\"true\"\n",
            encoding="utf-8",
        )
        self.assertTrue(admin_backend.auto_publish_verified_enabled())
        self.assertIs(self.store.news_listing()["showPublishVerified"], True)
        self.switch_file.unlink()
        os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = "off"
        os.environ[admin_backend.SHOW_PUBLISH_VERIFIED_BUTTON_ENV] = "0"
        self.assertFalse(admin_backend.auto_publish_verified_enabled())
        self.assertIs(self.store.news_listing()["showPublishVerified"], False)

    def test_publish_button_flag_defaults_off_until_explicitly_enabled(self):
        self.assertIs(admin_backend.show_publish_verified_button(), False)
        self.assertIs(self.store.news_listing()["showPublishVerified"], False)
        for token in ("1", "true", "on", " ON ", '"true"'):
            os.environ[admin_backend.SHOW_PUBLISH_VERIFIED_BUTTON_ENV] = token
            self.assertIs(self.store.news_listing()["showPublishVerified"], True, token)
        for token in ("", "0", "false", "off", "yes", "maybe"):
            os.environ[admin_backend.SHOW_PUBLISH_VERIFIED_BUTTON_ENV] = token
            self.assertIs(self.store.news_listing()["showPublishVerified"], False, token)

    def test_duplicate_and_rejected_rows_are_not_published_again(self):
        created = self.store.ingest_news([
            news_payload(verified=True, title="将要撤下", source_url="https://example.com/take-down"),
            news_payload(verified=True, title="信徒遭监禁", summary="代祷", source_url="https://example.com/take-down-prayer"),
        ])
        home_id, prayer_id = created["inserted"]
        version = self._version()
        _token, session = self._actor()
        actor = session["user"]["id"]
        removed = self.store.review_news(actor, home_id, "reject")
        self.assertEqual(removed["status"], "rejected")
        self.assertEqual(self._version(), version + 1)
        self.assertNotIn(home_id, {item["id"] for item in self.store.content(public=True)["items"]})
        self.store.review_news(actor, prayer_id, "reject")
        self.assertEqual(self._version(), version + 2)
        self.assertEqual(self.store.prayer_requests()["items"], [])
        self.assertNotIn(prayer_id, {item["id"] for item in self.store.content(public=True)["items"]})
        again = self.store.ingest_news([
            news_payload(verified=True, title="标题被换成别的", source_url="https://example.com/take-down"),
            news_payload(verified=True, title="信徒遭监禁", summary="代祷", source_url="https://example.com/take-down-prayer"),
        ])
        self.assertEqual(again["inserted"], [])
        self.assertCountEqual(again["ignored"], [home_id, prayer_id])
        self.assertEqual(again["published"], [])
        self.assertEqual(self._statuses()[home_id], "rejected")
        self.assertEqual(self._statuses()[prayer_id], "rejected")
        self.assertEqual(self._version(), version + 2)
        with self.store._db() as db:
            stored = json.loads(db.execute("SELECT data FROM news WHERE id=?", (home_id,)).fetchone()[0])
            note = db.execute(
                "SELECT detail FROM audit WHERE action='ingest_news' ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        self.assertEqual(stored["title"], "将要撤下")
        self.assertNotIn("auto-publish by ingest", note)

    def test_auto_publish_batch_rolls_back_when_the_version_bump_fails(self):
        before = self._version()
        with patch.object(AdminStore, "_bump_if_news_public_changed", side_effect=sqlite3.OperationalError("simulated")):
            with self.assertRaises(sqlite3.OperationalError):
                self.store.ingest_news([
                    news_payload(verified=True, source_url="https://example.com/rollback-1"),
                    news_payload(verified=False, source_url="https://example.com/rollback-2"),
                ])
        self.assertEqual(self.store.list_news(), [])
        self.assertEqual(self._version(), before)
        with self.store._db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM audit WHERE action='ingest_news'").fetchone())

    def test_hidden_publish_button_does_not_remove_the_authenticated_route(self):
        os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = "0"
        os.environ[admin_backend.SHOW_PUBLISH_VERIFIED_BUTTON_ENV] = "0"
        created = self.store.ingest_news([
            news_payload(verified=True, source_url="https://example.com/manual-batch"),
            news_payload(verified=False, source_url="https://example.com/manual-batch-no"),
        ])
        verified_id, unverified_id = created["inserted"]
        httpd = start_server(self.store)
        port = httpd.server_address[1]
        origin = f"http://127.0.0.1:{port}"
        try:
            status, denied = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": 1})
            self.assertEqual(status, 401)
            self.assertEqual(json.loads(denied)["error"], "authentication_required")
            token, session = self._actor()
            headers = {
                "Origin": origin,
                "Cookie": "prayer_admin_session=" + token,
                "X-CSRF-Token": session["csrfToken"],
            }
            status, listed = request(port, "GET", "/api/admin/news", None, headers)
            self.assertEqual(status, 200)
            listing = json.loads(listed)
            self.assertIs(listing["showPublishVerified"], False)
            self.assertEqual(listing["publishable"], 1)
            version = self._version()
            status, published = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": 1}, headers)
            self.assertEqual(status, 200)
            body = json.loads(published)
            self.assertEqual(body["published"], 1)
            self.assertEqual(body["version"], version + 1)
            self.assertEqual(self._statuses()[verified_id], "published")
            self.assertEqual(self._statuses()[unverified_id], "pending")
            os.environ[admin_backend.SHOW_PUBLISH_VERIFIED_BUTTON_ENV] = "on"
            status, shown = request(port, "GET", "/api/admin/news", None, headers)
            self.assertIs(json.loads(shown)["showPublishVerified"], True)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_deploy_script_does_not_write_news_switch_settings(self):
        source = Path(__file__).with_name("deploy-trial.py").read_text(encoding="utf-8")
        self.assertIn("EnvironmentFile=-/etc/prayer-earth-news/ingest.env", source)
        self.assertNotIn("NEWS_AUTO_PUBLISH_VERIFIED=", source)
        self.assertNotIn("NEWS_SHOW_PUBLISH_VERIFIED_BUTTON=", source)
        for line in source.splitlines():
            if "ingest.env" in line or "switches.env" in line:
                self.assertNotIn("tee ", line)
                self.assertNotIn("cat >", line)
                self.assertNotRegex(line, r">>")

    def _actor(self):
        self.store.bootstrap("admin", "temporary-pass-1")
        token, login = self.store.login("admin", "temporary-pass-1", "127.0.0.1")
        session = self.store.change_password(login["user"]["id"], "temporary-pass-1", "permanent-pass-1", token)
        return token, session

    def _version(self):
        return self.store.content()["version"]

    def _statuses(self):
        with self.store._db() as db:
            return {row["id"]: row["status"] for row in db.execute("SELECT id, status FROM news")}

    def _insert_news(self, news_id, verified, status="pending"):
        data = {
            "id": news_id,
            "title": "原始动态",
            "summary": "短摘要",
            "source_url": "https://example.com/" + news_id,
            "source_name": "来源",
            "published_at": "2026-10-27T08:00:00Z",
            "date": "2026-10-27",
            "region": "全球",
            "category": "基督教",
            "channel": "宗教动态",
        }
        if verified is not _OMITTED:
            data["verified"] = verified
        raw = verified if isinstance(verified, str) and verified.startswith("{") else json.dumps(data, ensure_ascii=False)
        with self.store._db() as db:
            db.execute(
                "INSERT INTO news(id,data,status,created_at,updated_at) VALUES (?,?,?,?,?)",
                (news_id, raw, status, "t0", "t0"),
            )

    def test_publish_verified_publishes_only_pending_json_true_and_bumps_once(self):
        os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = "0"
        _token, session = self._actor()
        actor = session["user"]["id"]
        created = self.store.ingest_news([
            news_payload(verified=True, source_url="https://example.com/verified-1", title="已核实一"),
            news_payload(verified=True, source_url="https://example.com/verified-2", title="已核实二"),
            news_payload(verified=True, source_url="https://example.com/verified-3", title="已核实三"),
            news_payload(verified=False, source_url="https://example.com/unverified"),
            news_payload(verified=True, source_url="https://example.com/reject-me"),
            news_payload(verified=False, source_url="https://example.com/already-public"),
            news_payload(verified=True, source_url="https://example.com/already-verified-public"),
        ])
        inserted = created["inserted"]
        verified_ids = inserted[:3]
        unverified_id, rejected_id, public_false_id, public_true_id = inserted[3:]
        self.store.review_news(actor, rejected_id, "reject")
        self.store.review_news(actor, public_false_id, "publish")
        self.store.review_news(actor, public_true_id, "publish")
        version_before = self._version()
        strict_rows = {
            "news-20261027-aaaaaaaaaaa1": "false",
            "news-20261027-aaaaaaaaaaa2": "true",
            "news-20261027-aaaaaaaaaaa3": 1,
            "news-20261027-aaaaaaaaaaa4": _OMITTED,
            "news-20261027-aaaaaaaaaaa5": False,
        }
        for news_id, verified in strict_rows.items():
            self._insert_news(news_id, verified)
        self._insert_news("news-20261027-aaaaaaaaaaa6", True, status="rejected")
        listing = self.store.news_listing("pending")
        self.assertEqual(listing["publishable"], 3)
        verified_flags = {item["id"]: item["verified"] for item in listing["items"]}
        self.assertIs(verified_flags["news-20261027-aaaaaaaaaaa1"], False)
        self.assertIs(verified_flags["news-20261027-aaaaaaaaaaa2"], False)
        self.assertIs(verified_flags["news-20261027-aaaaaaaaaaa4"], False)
        self.assertIs(verified_flags[verified_ids[0]], True)
        self._insert_news("news-20261027-aaaaaaaaaaa7", "{not-json")
        with self.assertRaises(ApiError) as mismatch:
            self.store.publish_verified_news(actor, expected_count=2)
        self.assertEqual(mismatch.exception.status, 409)
        self.assertEqual(mismatch.exception.extra["actual"], 3)
        self.assertEqual(self._version(), version_before)
        self.assertEqual(self._statuses()[unverified_id], "pending")
        with self.store._db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM audit WHERE action='publish_verified_news'").fetchone())

        result = self.store.publish_verified_news(actor, expected_count=3)
        self.assertEqual(result, {"published": 3, "version": version_before + 1})
        statuses = self._statuses()
        for news_id in verified_ids:
            self.assertEqual(statuses[news_id], "published")
        for news_id in (unverified_id, *strict_rows, "news-20261027-aaaaaaaaaaa7"):
            self.assertEqual(statuses[news_id], "pending", news_id)
        self.assertEqual(statuses[rejected_id], "rejected")
        self.assertEqual(statuses["news-20261027-aaaaaaaaaaa6"], "rejected")
        self.assertEqual(statuses[public_false_id], "published")
        self.assertEqual(statuses[public_true_id], "published")
        public_ids = {item["id"] for item in self.store.content(public=True)["items"]}
        self.assertTrue(set(verified_ids) <= public_ids)
        self.assertIn(public_false_id, public_ids)
        self.assertNotIn(unverified_id, public_ids)
        self.assertNotIn(rejected_id, public_ids)
        self.assertNotIn("news-20261027-aaaaaaaaaaa1", public_ids)
        again = self.store.publish_verified_news(actor, expected_count=0)
        self.assertEqual(again, {"published": 0, "version": result["version"]})
        with self.store._db() as db:
            rows = db.execute(
                "SELECT actor, detail FROM audit WHERE action='publish_verified_news' ORDER BY id"
            ).fetchall()
        self.assertEqual(len(rows), 2)
        first = json.loads(rows[0]["detail"])
        self.assertEqual(rows[0]["actor"], actor)
        self.assertEqual(first["published"], 3)
        self.assertEqual(first["ids"], sorted(verified_ids))
        self.assertEqual(json.loads(rows[1]["detail"])["published"], 0)
        self.store.review_news(actor, verified_ids[0], "reject")
        after_reject = self.store.content(public=True)
        self.assertEqual(after_reject["version"], result["version"] + 1)
        self.assertNotIn(verified_ids[0], {item["id"] for item in after_reject["items"]})

    def test_publish_verified_empty_set_does_not_bump_version(self):
        _token, session = self._actor()
        self.store.ingest_news([news_payload(verified=False, source_url="https://example.com/only-unverified")])
        self._insert_news("news-20261027-bbbbbbbbbbb1", "false", status="rejected")
        before = self._version()
        result = self.store.publish_verified_news(session["user"]["id"])
        self.assertEqual(result, {"published": 0, "version": before})
        self.assertEqual(self._version(), before)
        self.assertTrue(all(status != "published" for status in self._statuses().values()))

    def test_publish_verified_rolls_back_when_a_later_row_fails(self):
        os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = "0"
        _token, session = self._actor()
        created = self.store.ingest_news([
            news_payload(verified=True, source_url="https://example.com/atomic-1"),
            news_payload(verified=True, source_url="https://example.com/atomic-2"),
            news_payload(verified=False, source_url="https://example.com/atomic-untouched"),
        ])
        before = self._version()
        with self.store._db() as db:
            db.execute("""
                CREATE TRIGGER news_publish_fail_second
                BEFORE UPDATE ON news
                WHEN NEW.status = 'published' AND (SELECT COUNT(*) FROM news WHERE status = 'published') >= 1
                BEGIN
                  SELECT RAISE(ABORT, 'simulated failure');
                END
            """)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.publish_verified_news(session["user"]["id"], expected_count=2)
        self.assertEqual(self._statuses()[created["inserted"][0]], "pending")
        self.assertEqual(self._statuses()[created["inserted"][1]], "pending")
        self.assertEqual(self._statuses()[created["inserted"][2]], "pending")
        self.assertEqual(self._version(), before)
        with self.store._db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM audit WHERE action='publish_verified_news'").fetchone())
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0], before)

    def test_http_publish_verified_requires_session_csrf_and_uses_expected_count(self):
        os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = "0"
        created = self.store.ingest_news([
            news_payload(verified=True, source_url="https://example.com/http-1"),
            news_payload(verified=True, source_url="https://example.com/http-2"),
            news_payload(verified=False, source_url="https://example.com/http-unverified"),
        ])
        verified_ids = created["inserted"][:2]
        unverified_id = created["inserted"][2]
        httpd = start_server(self.store)
        port = httpd.server_address[1]
        origin = f"http://127.0.0.1:{port}"
        try:
            status, denied = request(port, "POST", "/api/admin/news/publish-verified", {})
            self.assertEqual(status, 401)
            self.assertEqual(json.loads(denied)["error"], "authentication_required")
            self.store.bootstrap("admin", "temporary-pass-1")
            token, login = self.store.login("admin", "temporary-pass-1", "127.0.0.1")
            temporary = {
                "Origin": origin,
                "Cookie": "prayer_admin_session=" + token,
                "X-CSRF-Token": login["csrfToken"],
            }
            status, blocked = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": 2}, temporary)
            self.assertEqual(status, 403)
            self.assertEqual(json.loads(blocked)["error"], "password_change_required")
            self.assertTrue(all(item["status"] == "pending" for item in self.store.list_news()))
            session = self.store.change_password(login["user"]["id"], "temporary-pass-1", "permanent-pass-1", token)
            headers = {
                "Origin": origin,
                "Cookie": "prayer_admin_session=" + token,
                "X-CSRF-Token": session["csrfToken"],
            }
            status, _ = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": 2}, dict(headers, Origin="https://evil.example"))
            self.assertEqual(status, 403)
            missing_csrf = dict(headers)
            missing_csrf.pop("X-CSRF-Token")
            status, missing = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": 2}, missing_csrf)
            self.assertEqual(status, 403)
            self.assertEqual(json.loads(missing)["error"], "invalid_csrf")
            status, wrong = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": 2}, dict(headers, **{"X-CSRF-Token": "not-the-token"}))
            self.assertEqual(status, 403)
            self.assertEqual(json.loads(wrong)["error"], "invalid_csrf")
            status, extra = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": 2, "force": True}, headers)
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(extra)["error"], "unknown_field")
            status, boolean = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": True}, headers)
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(boolean)["error"], "invalid_expected_count")
            status, listed = request(port, "GET", "/api/admin/news?status=pending", None, headers)
            self.assertEqual(status, 200)
            listing = json.loads(listed)
            self.assertEqual(listing["publishable"], 2)
            self.assertIs(listing["showPublishVerified"], False)
            self.assertEqual(sum(1 for item in listing["items"] if item["verified"] is True), 2)
            version_before = self._version()
            status, mismatched = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": 1}, headers)
            self.assertEqual(status, 409)
            mismatch_body = json.loads(mismatched)
            self.assertEqual(mismatch_body["error"], "count_mismatch")
            self.assertEqual(mismatch_body["actual"], 2)
            self.assertEqual(self._version(), version_before)
            self.assertEqual(self._statuses()[verified_ids[0]], "pending")
            status, published = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": 2}, headers)
            self.assertEqual(status, 200)
            body = json.loads(published)
            self.assertEqual(body["published"], 2)
            self.assertEqual(body["version"], version_before + 1)
            self.assertEqual(self._statuses()[verified_ids[0]], "published")
            self.assertEqual(self._statuses()[verified_ids[1]], "published")
            self.assertEqual(self._statuses()[unverified_id], "pending")
            editor = self.store.create_user(login["user"]["id"], {"username": "editor1", "password": "temporary-pass-2", "role": "editor"})
            editor_token, editor_login = self.store.login("editor1", "temporary-pass-2", "10.0.0.8")
            self.assertEqual(editor["role"], "editor")
            status, editor_denied = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": 0}, {
                "Origin": origin, "Cookie": "prayer_admin_session=" + editor_token, "X-CSRF-Token": editor_login["csrfToken"],
            })
            self.assertEqual(status, 403)
            self.assertEqual(json.loads(editor_denied)["error"], "password_change_required")
            editor_session = self.store.change_password(editor["id"], "temporary-pass-2", "permanent-pass-2", editor_token)
            status, editor_published = request(port, "POST", "/api/admin/news/publish-verified", {"expected_count": 0}, {
                "Origin": origin,
                "Cookie": "prayer_admin_session=" + editor_token,
                "X-CSRF-Token": editor_session["csrfToken"],
            })
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(editor_published)["published"], 0)
            self.assertEqual(json.loads(editor_published)["version"], body["version"])
        finally:
            httpd.shutdown()
            httpd.server_close()


_OMITTED = object()


PRAYER_FIELDS = {"id", "title", "summary", "sourceName", "sourceUrl", "date", "region", "verified"}


class PrayerRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "private"
        self.store = AdminStore(self.data, secure_cookies=False)
        self.store.bootstrap("admin", "temporary-pass-1")
        _, login = self.store.login("admin", "temporary-pass-1", "127.0.0.1")
        self.actor = login["user"]["id"]
        self.switch_file = Path(self.tmp.name) / "switches.env"
        self.switch_patch = patch.object(admin_backend, "NEWS_SWITCH_FILE", self.switch_file)
        self.switch_patch.start()
        self.flag_patch = patch.dict(os.environ, {
            admin_backend.AUTO_PUBLISH_VERIFIED_ENV: "",
            admin_backend.SHOW_PUBLISH_VERIFIED_BUTTON_ENV: "",
        }, clear=False)
        self.flag_patch.start()

    def tearDown(self):
        self.flag_patch.stop()
        self.switch_patch.stop()
        self.tmp.cleanup()

    def _version(self):
        with self.store._db() as db:
            return db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0]

    def _row_count(self):
        with self.store._db() as db:
            return db.execute("SELECT COUNT(*) FROM news").fetchone()[0]

    def _ids(self, public=True):
        return {item["id"] for item in self.store.content(public=public)["items"] if item.get("kind") == "news" or item.get("channel") == "宗教动态"}

    def test_verified_keyword_is_auto_routed_by_date_and_not_duplicated(self):
        before = self._version()
        created = self.store.ingest_news([
            news_payload(verified=True, title="教会周报", summary="本周聚会安排", source_url="https://example.com/plain", published_at="2026-10-28T08:00:00Z"),
            news_payload(verified=True, title="信徒遭监禁", summary="短摘要", source_url="https://example.com/old", published_at="2026-10-01T08:00:00Z"),
            news_payload(verified=True, title="教会周报", summary="多地发生迫害", source_url="https://example.com/new", published_at="2026-10-20T08:00:00Z"),
            news_payload(verified=True, title="Persecution report", summary="short", source_url="https://example.com/en", published_at="2026-10-21T08:00:00Z"),
            news_payload(verified=True, title="地区新闻", summary="没有关键词", region="迫害", source_url="https://example.com/region", published_at="2026-10-22T08:00:00Z"),
        ])
        ids = created["inserted"]
        for news_id in ids:
            self.store.review_news(self.actor, news_id, "publish")
        plain, old, new, english, region_only = ids
        prayers = self.store.prayer_requests()
        prayer_ids = [item["id"] for item in prayers["items"]]
        self.assertEqual(prayer_ids, [english, new, old])
        self.assertTrue(all(set(item) == PRAYER_FIELDS for item in prayers["items"]))
        self.assertTrue(all(item["verified"] is True for item in prayers["items"]))
        self.assertNotIn("needsPrayer", prayers["items"][0])
        self.assertNotIn("status", prayers["items"][0])
        content_ids = self._ids()
        self.assertIn(plain, content_ids)
        self.assertIn(region_only, content_ids)
        self.assertTrue(set(prayer_ids).isdisjoint(content_ids))
        self.assertEqual(self._row_count(), 5)
        self.assertGreater(self._version(), before)
        again = self.store.review_news(self.actor, english, "publish")
        self.assertEqual(again["status"], "published")
        self.assertEqual(self._version(), prayers["version"])

    def test_unverified_keyword_stays_on_news_until_marked_and_returns(self):
        created = self.store.ingest_news([
            news_payload(verified=False, title="有人被拘留", summary="待核对", source_url="https://example.com/unverified"),
        ])
        news_id = created["inserted"][0]
        self.store.review_news(self.actor, news_id, "publish")
        version = self._version()
        self.assertEqual(self.store.prayer_requests()["items"], [])
        self.assertIn(news_id, self._ids())
        marked = self.store.set_news_prayer(self.actor, news_id, True)
        self.assertEqual(marked["version"], version + 1)
        self.assertTrue(marked["item"]["onPrayerPage"])
        self.assertTrue(marked["item"]["needsPrayer"])
        self.assertNotIn(news_id, self._ids())
        prayer = self.store.prayer_requests()["items"]
        self.assertEqual(prayer[0]["id"], news_id)
        self.assertFalse(prayer[0]["verified"])
        cleared = self.store.set_news_prayer(self.actor, news_id, False)
        self.assertEqual(cleared["version"], version + 2)
        self.assertFalse(cleared["item"]["onPrayerPage"])
        self.assertEqual(self.store.prayer_requests()["items"], [])
        self.assertIn(news_id, self._ids())
        self.assertEqual(self._row_count(), 1)
        self.store.set_news_prayer(self.actor, news_id, False)
        self.assertEqual(self._version(), version + 2)

    def test_exclusion_overrides_auto_and_manual_without_deleting(self):
        created = self.store.ingest_news([
            news_payload(verified=True, title="教堂遭袭击教会", summary="短摘要", source_url="https://example.com/auto"),
            news_payload(verified=False, title="家人被绑架", summary="尚未核实", source_url="https://example.com/manual"),
        ])
        auto_id, manual_id = created["inserted"]
        self.store.review_news(self.actor, auto_id, "publish")
        self.store.review_news(self.actor, manual_id, "publish")
        self.store.set_news_prayer(self.actor, manual_id, True)
        self.assertEqual({item["id"] for item in self.store.prayer_requests()["items"]}, {auto_id, manual_id})
        self.assertTrue(self._ids().isdisjoint({auto_id, manual_id}))
        version = self._version()
        excluded = self.store.set_news_prayer_exclusion(self.actor, auto_id, True)
        self.assertTrue(excluded["item"]["prayerExcluded"])
        self.assertFalse(excluded["item"]["onPrayerPage"])
        self.assertEqual(excluded["version"], version + 1)
        self.assertNotIn(auto_id, {item["id"] for item in self.store.prayer_requests()["items"]})
        self.assertIn(auto_id, self._ids())
        self.store.set_news_prayer_exclusion(self.actor, manual_id, True)
        self.assertEqual(self.store.prayer_requests()["items"], [])
        self.assertIn(manual_id, self._ids())
        self.assertEqual(self._row_count(), 2)
        restored = self.store.set_news_prayer_exclusion(self.actor, auto_id, False)
        self.assertTrue(restored["item"]["onPrayerPage"])
        self.assertNotIn(auto_id, self._ids())
        self.assertIn(auto_id, {item["id"] for item in self.store.prayer_requests()["items"]})
        with self.store._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM news").fetchone()[0], 2)
            stored = json.loads(db.execute("SELECT data FROM news WHERE id=?", (auto_id,)).fetchone()[0])
        self.assertEqual(stored["title"], "教堂遭袭击教会")

    def test_string_verified_does_not_auto_route(self):
        news_id = "news-20261027-abcdefabcdef"
        payload = {
            "id": news_id, "title": "信徒遭监禁", "summary": "短摘要",
            "source_url": "https://example.com/string-verified", "source_name": "教会通讯",
            "published_at": "2026-10-27T08:00:00Z", "date": "2026-10-27", "region": "全球",
            "verified": "true", "category": "基督教",
        }
        with self.store._db() as db:
            db.execute(
                "INSERT INTO news(id,data,status,created_at,updated_at,needs_prayer,prayer_excluded) VALUES (?,?,'published',?,?,0,0)",
                (news_id, json.dumps(payload), "t", "t"),
            )
        self.assertEqual(self.store.prayer_requests()["items"], [])
        self.assertIn(news_id, self._ids())

    def test_pending_keyword_is_not_public_until_publish(self):
        os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = "off"
        created = self.store.ingest_news([
            news_payload(verified=True, title="禁教之后", summary="短摘要", source_url="https://example.com/pending-prayer"),
        ])
        news_id = created["inserted"][0]
        version = self._version()
        self.assertEqual(self.store.prayer_requests()["items"], [])
        self.assertNotIn(news_id, self._ids())
        self.assertEqual(self._version(), version)
        listing = self.store.news_listing()
        item = next(entry for entry in listing["items"] if entry["id"] == news_id)
        self.assertTrue(item["prayerCandidate"])
        self.assertFalse(item["onPrayerPage"])
        self.assertFalse(item["needsPrayer"])

    def test_marking_pending_publishes_and_routes_once(self):
        created = self.store.ingest_news([
            news_payload(verified=False, title="普通周报", summary="没有关键词", source_url="https://example.com/mark-publish"),
        ])
        news_id = created["inserted"][0]
        version = self._version()
        result = self.store.set_news_prayer(self.actor, news_id, True)
        self.assertEqual(result["item"]["status"], "published")
        self.assertEqual(result["version"], version + 1)
        self.assertEqual(self.store.prayer_requests()["items"][0]["id"], news_id)
        self.assertNotIn(news_id, self._ids())
        self.assertEqual(self._row_count(), 1)

    def test_http_prayer_routes_require_session_csrf_and_hide_admin_fields(self):
        created = self.store.ingest_news([
            news_payload(verified=False, title="有人被拘押", summary="待核实摘要", source_url="https://example.com/http-prayer"),
            news_payload(verified=True, title="关闭教会", summary="已核实", source_url="https://example.com/http-auto"),
        ])
        manual_id, auto_id = created["inserted"]
        httpd = start_server(self.store)
        port = httpd.server_address[1]
        origin = f"http://127.0.0.1:{port}"
        try:
            status, denied = request(port, "POST", f"/api/admin/news/{manual_id}/prayer", {"needs_prayer": True})
            self.assertEqual(status, 401)
            self.assertEqual(json.loads(denied)["error"], "authentication_required")
            token, login = self.store.login("admin", "temporary-pass-1", "127.0.0.1")
            temporary = {"Origin": origin, "Cookie": "prayer_admin_session=" + token, "X-CSRF-Token": login["csrfToken"]}
            status, blocked = request(port, "POST", f"/api/admin/news/{manual_id}/prayer", {"needs_prayer": True}, temporary)
            self.assertEqual(status, 403)
            self.assertEqual(json.loads(blocked)["error"], "password_change_required")
            session = self.store.change_password(self.actor, "temporary-pass-1", "permanent-pass-1", token)
            headers = {"Origin": origin, "Cookie": "prayer_admin_session=" + token, "X-CSRF-Token": session["csrfToken"]}
            status, _ = request(port, "POST", f"/api/admin/news/{manual_id}/prayer", {"needs_prayer": True}, dict(headers, Origin="https://evil.example"))
            self.assertEqual(status, 403)
            missing = dict(headers)
            missing.pop("X-CSRF-Token")
            status, missing_body = request(port, "POST", f"/api/admin/news/{manual_id}/prayer", {"needs_prayer": True}, missing)
            self.assertEqual(status, 403)
            self.assertEqual(json.loads(missing_body)["error"], "invalid_csrf")
            status, extra = request(port, "POST", f"/api/admin/news/{manual_id}/prayer", {"needs_prayer": True, "force": True}, headers)
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(extra)["error"], "unknown_field")
            status, boolean = request(port, "POST", f"/api/admin/news/{manual_id}/prayer", {"needs_prayer": "true"}, headers)
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(boolean)["error"], "invalid_needs_prayer")
            version = self._version()
            status, marked = request(port, "POST", f"/api/admin/news/{manual_id}/prayer", {"needs_prayer": True}, headers)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(marked)["version"], version + 1)
            status, published = request(port, "POST", f"/api/admin/news/{auto_id}/publish", {}, headers)
            self.assertEqual(status, 200)
            status, public_headers, public_body = request_response(port, "GET", "/api/prayer-requests")
            self.assertEqual(status, 200)
            self.assertIn("nosniff", public_headers.get("x-content-type-options", ""))
            self.assertIn("max-age=30", public_headers.get("cache-control", ""))
            self.assertIn("prayer-requests-", public_headers.get("etag", ""))
            payload = json.loads(public_body)
            by_id = {item["id"]: item for item in payload["items"]}
            self.assertEqual(set(by_id), {auto_id, manual_id})
            self.assertFalse(by_id[manual_id]["verified"])
            self.assertTrue(by_id[auto_id]["verified"])
            self.assertNotIn("needsPrayer", public_body.decode())
            self.assertNotIn("prayerExcluded", public_body.decode())
            status, content_body = request(port, "GET", "/api/content")
            content = json.loads(content_body)
            self.assertTrue({auto_id, manual_id}.isdisjoint({item["id"] for item in content["items"]}))
            self.assertEqual(content["version"], payload["version"])
            status, method = request(port, "POST", "/api/prayer-requests", {})
            self.assertEqual(status, 405)
            status, excluded = request(port, "POST", f"/api/admin/news/{auto_id}/prayer-exclusion", {"excluded": True}, headers)
            self.assertEqual(status, 200)
            self.assertFalse(json.loads(excluded)["item"]["onPrayerPage"])
            status, after = request(port, "GET", "/api/content")
            self.assertIn(auto_id, {item["id"] for item in json.loads(after)["items"]})
            status, prayers_after = request(port, "GET", "/api/prayer-requests")
            self.assertNotIn(auto_id, {item["id"] for item in json.loads(prayers_after)["items"]})
            editor = self.store.create_user(self.actor, {"username": "editor1", "password": "temporary-pass-2", "role": "editor"})
            editor_token, editor_login = self.store.login("editor1", "temporary-pass-2", "10.0.0.8")
            status, editor_denied = request(port, "POST", f"/api/admin/news/{auto_id}/prayer-exclusion", {"excluded": False}, {
                "Origin": origin, "Cookie": "prayer_admin_session=" + editor_token, "X-CSRF-Token": editor_login["csrfToken"],
            })
            self.assertEqual(status, 403)
            self.assertEqual(json.loads(editor_denied)["error"], "password_change_required")
            editor_session = self.store.change_password(editor["id"], "temporary-pass-2", "permanent-pass-2", editor_token)
            status, editor_ok = request(port, "POST", f"/api/admin/news/{auto_id}/prayer-exclusion", {"excluded": False}, {
                "Origin": origin, "Cookie": "prayer_admin_session=" + editor_token, "X-CSRF-Token": editor_session["csrfToken"],
            })
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(editor_ok)["item"]["onPrayerPage"])
        finally:
            httpd.shutdown()
            httpd.server_close()


class PrayerColumnMigrationTests(unittest.TestCase):
    def test_old_news_table_gains_flags_without_losing_rows(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name) / "private"
        data.mkdir()
        connection = sqlite3.connect(data / "admin.sqlite3")
        payload = {"id": "news-20261027-0123456789ab", "title": "旧行", "summary": "保留"}
        connection.executescript("""
            CREATE TABLE news (
              id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
            INSERT INTO meta(key, value) VALUES ('version', 7);
        """)
        connection.execute(
            "INSERT INTO news(id, data, status, created_at, updated_at) VALUES (?,?, 'published', 't0', 't1')",
            ("news-20261027-0123456789ab", json.dumps(payload, ensure_ascii=False)),
        )
        connection.commit()
        connection.close()
        store = AdminStore(data, secure_cookies=False)
        with store._db() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(news)")}
            row = db.execute("SELECT data, status, needs_prayer, prayer_excluded, created_at FROM news").fetchone()
            version = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0]
        self.assertIn("needs_prayer", columns)
        self.assertIn("prayer_excluded", columns)
        self.assertEqual(json.loads(row["data"])["title"], "旧行")
        self.assertEqual(row["status"], "published")
        self.assertEqual(row["needs_prayer"], 0)
        self.assertEqual(row["prayer_excluded"], 0)
        self.assertEqual(row["created_at"], "t0")
        self.assertEqual(version, 7)
        self.assertEqual(store.prayer_requests()["items"], [])
        restarted = AdminStore(data, secure_cookies=False)
        with restarted._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM news").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0], 7)


class PublicFeedEtagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "private"
        self.store = AdminStore(self.data, secure_cookies=False)
        self.httpd = start_server(self.store)
        self.port = self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def test_feed_etag_is_version_plus_id_set_hash(self):
        digest = hashlib.sha256("a\nb".encode()).hexdigest()[:16]
        expected = f'"content-4-{digest}"'
        self.assertEqual(admin_backend.feed_etag("content", 4, [{"id": "b"}, {"id": "a"}, {"id": "a"}]), expected)
        self.assertEqual(admin_backend.feed_etag("content", 4, [{"id": "a"}, {"id": "b"}]), expected)
        self.assertNotEqual(admin_backend.feed_etag("content", 4, [{"id": "a"}]), expected)
        self.assertNotEqual(admin_backend.feed_etag("content", 5, [{"id": "a"}, {"id": "b"}]), expected)
        self.assertNotEqual(admin_backend.feed_etag("prayer-requests", 4, [{"id": "a"}, {"id": "b"}]), expected)
        self.assertNotEqual(expected, '"content-4"')
        empty = hashlib.sha256(b"").hexdigest()[:16]
        self.assertEqual(admin_backend.feed_etag("prayer-requests", 4, []), f'"prayer-requests-4-{empty}"')

    def test_same_version_membership_change_changes_etag(self):
        version = self._version()
        first_content = self._get("/api/content")
        first_prayer = self._get("/api/prayer-requests")
        again_content = self._get("/api/content")
        again_prayer = self._get("/api/prayer-requests")
        self.assertEqual(again_content["etag"], first_content["etag"])
        self.assertEqual(again_prayer["etag"], first_prayer["etag"])
        self.assertEqual(first_content["version"], version)
        self.assertEqual(first_prayer["version"], version)
        self.assertEqual(self._version(), version)
        self._assert_public_headers(first_content)
        self._assert_public_headers(first_prayer)
        self.assertEqual(first_content["etag"], admin_backend.feed_etag("content", version, first_content["items"]))
        self.assertEqual(first_prayer["etag"], admin_backend.feed_etag("prayer-requests", version, first_prayer["items"]))

        news_id = self._insert_published(title="教会周报", summary="短摘要", verified=False)
        listed = self._get("/api/content")
        prayers = self._get("/api/prayer-requests")
        self.assertEqual(self._version(), version)
        self.assertEqual(listed["version"], version)
        self.assertIn(news_id, {item["id"] for item in listed["items"]})
        self.assertEqual(prayers["items"], [])
        self.assertNotEqual(listed["etag"], first_content["etag"])
        self.assertEqual(prayers["etag"], first_prayer["etag"])
        self.assertEqual(self._get("/api/content")["etag"], listed["etag"])

        self._rewrite(news_id, summary="仍是同一条，没有关键词")
        rewritten = self._get("/api/content")
        self.assertEqual(self._version(), version)
        self.assertEqual(rewritten["etag"], listed["etag"])
        self.assertEqual(self._get("/api/prayer-requests")["etag"], prayers["etag"])

        self._rewrite(news_id, title="信徒遭监禁", verified=True)
        routed_content = self._get("/api/content")
        routed_prayer = self._get("/api/prayer-requests")
        self.assertEqual(self._version(), version)
        self.assertEqual(routed_content["version"], version)
        self.assertEqual(routed_prayer["version"], version)
        self.assertNotIn(news_id, {item["id"] for item in routed_content["items"]})
        self.assertEqual([item["id"] for item in routed_prayer["items"]], [news_id])
        self.assertNotEqual(routed_content["etag"], listed["etag"])
        self.assertNotEqual(routed_prayer["etag"], prayers["etag"])
        self.assertEqual(routed_content["etag"], admin_backend.feed_etag("content", version, routed_content["items"]))
        self.assertEqual(routed_prayer["etag"], admin_backend.feed_etag("prayer-requests", version, routed_prayer["items"]))
        self.assertEqual(self._get("/api/content")["etag"], routed_content["etag"])
        self.assertEqual(self._get("/api/prayer-requests")["etag"], routed_prayer["etag"])

        for path, current, previous, legacy in (
            ("/api/content", routed_content["etag"], listed["etag"], f'"content-{version}"'),
            ("/api/prayer-requests", routed_prayer["etag"], prayers["etag"], f'"prayer-requests-{version}"'),
        ):
            hit = self._get(path, {"If-None-Match": current})
            self.assertEqual(hit["status"], 304)
            self.assertEqual(hit["body"], b"")
            self.assertEqual(hit["etag"], current)
            self.assertEqual(hit["headers"]["cache-control"], admin_backend.PUBLIC_FEED_CACHE_CONTROL)
            head = self._get(path, {"If-None-Match": current}, method="HEAD")
            self.assertEqual(head["status"], 304)
            self.assertEqual(head["body"], b"")
            self.assertEqual(head["etag"], current)
            for stale in (previous, legacy, '"content-4"', '"prayer-requests-4"'):
                missed = self._get(path, {"If-None-Match": stale})
                self.assertEqual(missed["status"], 200, stale)
                self.assertEqual(missed["etag"], current)
                self._assert_public_headers(missed)
                self.assertGreater(len(missed["body"]), 0)

    def _version(self):
        with self.store._db() as db:
            return int(db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])

    def _insert_published(self, **overrides):
        record = self.store._normalize_news_item(news_payload(**overrides), 0)
        with self.store._db() as db:
            db.execute(
                "INSERT INTO news(id,data,status,created_at,updated_at,needs_prayer,prayer_excluded) "
                "VALUES (?,?,'published',?,?,0,0)",
                (record["id"], json.dumps(record, ensure_ascii=False), "t0", "t1"),
            )
        return record["id"]

    def _rewrite(self, news_id, **overrides):
        with self.store._db() as db:
            data = json.loads(db.execute("SELECT data FROM news WHERE id=?", (news_id,)).fetchone()["data"])
            data.update(overrides)
            db.execute("UPDATE news SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), news_id))

    def _get(self, path, headers=None, method="GET"):
        status, response_headers, body = request_response(self.port, method, path, headers=headers)
        payload = json.loads(body) if body else {}
        return {
            "status": status,
            "headers": response_headers,
            "body": body,
            "etag": response_headers.get("etag", ""),
            "version": payload.get("version"),
            "items": payload.get("items", []),
        }

    def _assert_public_headers(self, response):
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["headers"]["cache-control"], admin_backend.PUBLIC_FEED_CACHE_CONTROL)
        self.assertEqual(response["headers"]["x-content-type-options"], "nosniff")
        self.assertEqual(response["headers"]["referrer-policy"], "same-origin")
        self.assertIn("application/json", response["headers"]["content-type"])


def request_response(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    raw = None if body is None else body if isinstance(body, bytes) else json.dumps(body).encode()
    header_map = dict(headers or {})
    if raw is not None and "Content-Type" not in header_map:
        header_map["Content-Type"] = "application/json"
    connection.request(method, path, body=raw, headers=header_map)
    response = connection.getresponse()
    payload = response.read()
    status = response.status
    header_map = {key.lower(): value for key, value in response.getheaders()}
    connection.close()
    return status, header_map, payload


if __name__ == "__main__":
    unittest.main()
