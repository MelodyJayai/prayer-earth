#!/usr/bin/env python3
"""Focused regression tests for admin persistence and upload safety.

Run with ``python -m unittest scripts.test_admin_backend``.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.admin_backend import AdminStore, ApiError


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


if __name__ == "__main__":
    unittest.main()
