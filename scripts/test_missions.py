#!/usr/bin/env python3
"""Regression tests for the mission board (conferences, progress, reports).

Run with ``python -m unittest scripts.test_missions``.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import admin_backend
from scripts.admin_backend import AdminStore, ApiError
from scripts.test_admin_backend import SECRET, request, start_server, without_ingest_config


def mission_payload(**overrides):
    item = {
        "title": "洛桑运动区域会议",
        "summary": "短摘要，不含全文。",
        "source_url": "https://example.com/missions/conference",
        "source_name": "洛桑运动",
        "published_at": "2026-11-20T08:00:00Z",
        "region": "非洲",
        "verified": False,
        "kind": "会议",
    }
    item.update(overrides)
    return item


class MissionBoardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AdminStore(Path(self.tmp.name) / "private", secure_cookies=False)
        self.patches = [
            patch.object(admin_backend, "DEFAULT_INGEST_KEY_FILE", Path(self.tmp.name) / "missing.key"),
            patch.object(admin_backend, "NEWS_SWITCH_FILE", Path(self.tmp.name) / "switches.env"),
            without_ingest_config(),
            patch.dict(os.environ, {
                admin_backend.AUTO_PUBLISH_VERIFIED_ENV: "",
                admin_backend.SHOW_PUBLISH_VERIFIED_BUTTON_ENV: "",
            }, clear=False),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def version(self):
        with sqlite3.connect(self.store.db_path) as db:
            return db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0]

    def test_unverified_goes_pending_and_stays_off_public_feed(self):
        result = self.store.ingest_missions([mission_payload()])
        self.assertEqual(len(result["inserted"]), 1)
        self.assertTrue(result["inserted"][0].startswith("mission-20261120-"))
        self.assertEqual(result["published"], [])
        self.assertEqual(self.store.missions_public()["items"], [])
        pending = self.store.missions_listing("pending")["items"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["status"], "pending")

    def test_verified_publishes_once_and_bumps_version_once(self):
        before = self.version()
        result = self.store.ingest_missions([
            mission_payload(verified=True, event_date="2026-12-01"),
            mission_payload(verified=True, source_url="https://example.com/missions/report", kind="报告"),
        ])
        self.assertEqual(len(result["published"]), 2)
        self.assertEqual(self.version(), before + 1)
        feed = self.store.missions_public()
        self.assertEqual(len(feed["items"]), 2)
        conference = next(i for i in feed["items"] if i["kind"] == "会议")
        self.assertEqual(conference["eventDate"], "2026-12-01")
        self.assertTrue(conference["verified"])
        self.assertNotIn("status", conference)
        again = self.store.ingest_missions([mission_payload(verified=True, title="改写标题")])
        self.assertEqual(again["inserted"], [])
        self.assertEqual(len(again["ignored"]), 1)
        self.assertEqual(self.version(), before + 1)

    def test_review_publish_and_reject_and_rejected_stays_rejected(self):
        created = self.store.ingest_missions([mission_payload()])
        mission_id = created["inserted"][0]
        before = self.version()
        item = self.store.review_mission("admin", mission_id, "publish")
        self.assertEqual(item["status"], "published")
        self.assertEqual(self.version(), before + 1)
        self.assertEqual(len(self.store.missions_public()["items"]), 1)
        self.store.review_mission("admin", mission_id, "reject")
        self.assertEqual(self.store.missions_public()["items"], [])
        resubmitted = self.store.ingest_missions([mission_payload(verified=True)])
        self.assertEqual(resubmitted["published"], [])
        self.assertEqual(self.store.missions_public()["items"], [])
        with self.assertRaises(ApiError):
            self.store.review_mission("admin", "mission-20261120-000000000000", "publish")
        with self.assertRaises(ApiError):
            self.store.review_mission("admin", "news-20261120-000000000000", "publish")

    def test_auto_publish_switch_off_keeps_verified_pending(self):
        os.environ[admin_backend.AUTO_PUBLISH_VERIFIED_ENV] = "off"
        result = self.store.ingest_missions([mission_payload(verified=True)])
        self.assertEqual(result["published"], [])
        self.assertEqual(self.store.missions_public()["items"], [])

    def test_validation_rejects_bad_batches_without_partial_writes(self):
        bad = [
            mission_payload(kind="新闻"),
            mission_payload(kind=None),
            mission_payload(verified="true"),
            mission_payload(category="基督教"),
            mission_payload(event_date="2026-13-40"),
            mission_payload(event_date=20261201),
            mission_payload(source_url="javascript:alert(1)"),
            mission_payload(title=""),
            mission_payload(published_at="2999-01-01"),
        ]
        for item in bad:
            with self.assertRaises(ApiError, msg=str(item)):
                self.store.ingest_missions([mission_payload(source_url="https://example.com/ok"), item])
        missing = mission_payload()
        del missing["kind"]
        with self.assertRaises(ApiError):
            self.store.ingest_missions([missing])
        with self.assertRaises(ApiError):
            self.store.ingest_missions([])
        with self.assertRaises(ApiError):
            self.store.ingest_missions([mission_payload(source_url=f"https://example.com/{n}") for n in range(31)])
        self.assertEqual(self.store.missions_listing()["items"], [])

    def test_missions_never_leak_into_news_or_prayer_feeds(self):
        self.store.ingest_missions([mission_payload(verified=True, title="迫害报告 逮捕 监禁", summary="迫害 监禁 拘留")])
        self.assertEqual(self.store.prayer_requests()["items"], [])
        self.assertEqual([i for i in self.store.content(public=True)["items"] if str(i["id"]).startswith("mission")], [])
        self.assertEqual(self.store.list_news(), [])

    def test_http_ingest_uses_same_key_and_public_feed_is_readable(self):
        os.environ[admin_backend.INGEST_KEY_ENV] = SECRET
        httpd = start_server(self.store)
        port = httpd.server_address[1]
        try:
            status, _ = request(port, "POST", "/api/ingest/missions", {"items": [mission_payload()]})
            self.assertEqual(status, 401)
            status, body = request(port, "GET", "/api/ingest/missions")
            self.assertEqual(status, 405)
            headers = {"Authorization": "Bearer " + SECRET}
            status, body = request(port, "POST", "/api/ingest/missions",
                                   {"items": [mission_payload(verified=True)]}, headers)
            self.assertEqual(status, 200, body)
            self.assertEqual(len(json.loads(body)["published"]), 1)
            status, body = request(port, "POST", "/api/ingest/missions",
                                   {"items": [mission_payload(category="基督教")]}, headers)
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(body)["error"], "unknown_field")
            status, body = request(port, "GET", "/api/missions")
            self.assertEqual(status, 200)
            payload = json.loads(body)
            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["kind"], "会议")
            status, _ = request(port, "POST", "/api/missions", {})
            self.assertEqual(status, 405)
            status, _ = request(port, "GET", "/api/admin/missions")
            self.assertIn(status, (401, 403))
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_admin_http_review_needs_session_origin_and_csrf(self):
        created = self.store.ingest_missions([mission_payload()])["inserted"][0]
        self.store.bootstrap("admin", "temporary-pass-1")
        token, login = self.store.login("admin", "temporary-pass-1", "127.0.0.1")
        session = self.store.change_password(login["user"]["id"], "temporary-pass-1", "permanent-pass-1", token)
        httpd = start_server(self.store)
        port = httpd.server_address[1]
        headers = {
            "Origin": f"http://127.0.0.1:{port}",
            "Cookie": "prayer_admin_session=" + token,
            "X-CSRF-Token": session["csrfToken"],
        }
        try:
            status, _ = request(port, "GET", "/api/admin/missions")
            self.assertEqual(status, 401)
            status, listing = request(port, "GET", "/api/admin/missions?status=pending", None, headers)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(listing)["items"][0]["id"], created)
            status, _ = request(port, "GET", "/api/admin/missions?bogus=1", None, headers)
            self.assertEqual(status, 400)
            no_csrf = dict(headers)
            no_csrf.pop("X-CSRF-Token")
            status, _ = request(port, "POST", f"/api/admin/missions/{created}/publish", {}, no_csrf)
            self.assertEqual(status, 403)
            status, _ = request(port, "POST", f"/api/admin/missions/{created}/publish", {"x": 1}, headers)
            self.assertEqual(status, 400)
            status, body = request(port, "POST", f"/api/admin/missions/{created}/publish", {}, headers)
            self.assertEqual(status, 200, body)
            status, public = request(port, "GET", "/api/missions")
            self.assertEqual(len(json.loads(public)["items"]), 1)
            status, _ = request(port, "POST", f"/api/admin/missions/{created}/reject", {}, headers)
            self.assertEqual(status, 200)
            status, public = request(port, "GET", "/api/missions")
            self.assertEqual(json.loads(public)["items"], [])
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_news_ingest_still_rejects_mission_fields(self):
        with self.assertRaises(ApiError):
            self.store.ingest_news([{**mission_payload(), "category": "宗教宣教"}])


if __name__ == "__main__":
    unittest.main()
