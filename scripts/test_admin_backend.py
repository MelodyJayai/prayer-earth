#!/usr/bin/env python3
"""Focused regression tests for admin persistence and upload safety.

Run with ``python -m unittest scripts.test_admin_backend``.
"""
from __future__ import annotations

import http.client
import io
import json
import os
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
        self.key_patch = patch.object(admin_backend, "DEFAULT_INGEST_KEY_FILE", self.missing_key)
        self.key_patch.start()
        self.env_patch = without_ingest_config()
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
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


if __name__ == "__main__":
    unittest.main()
