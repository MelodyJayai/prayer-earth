import json
import importlib.util
import sys
import tempfile
import os
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image

from scripts.admin_backend import AdminStore
_SNAPSHOT_SPEC = importlib.util.spec_from_file_location("generate_static_snapshot", Path(__file__).with_name("generate-static-snapshot.py"))
assert _SNAPSHOT_SPEC and _SNAPSHOT_SPEC.loader
_SNAPSHOT = importlib.util.module_from_spec(_SNAPSHOT_SPEC)
_SNAPSHOT_SPEC.loader.exec_module(_SNAPSHOT)
build_snapshot = _SNAPSHOT.build_snapshot


_BACKUP_SPEC = importlib.util.spec_from_file_location("backup_prayer_data", Path(__file__).with_name("backup-prayer-data.py"))
assert _BACKUP_SPEC and _BACKUP_SPEC.loader
_BACKUP = importlib.util.module_from_spec(_BACKUP_SPEC)
_BACKUP_SPEC.loader.exec_module(_BACKUP)
backup_once = _BACKUP.backup_once


class ResilienceToolTests(unittest.TestCase):
    def test_snapshot_is_self_contained_and_has_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            site = root / "site"
            data = root / "data"
            media = data / "media" / "upload"
            (site / "assets" / "content" / "morning").mkdir(parents=True)
            media.mkdir(parents=True)
            seed = site / "content-seed.json"
            seed.write_text(json.dumps({"items": [{
                "id": "morning-2026-01-01", "date": "2026-01-01", "channel": "晨修",
                "segments": [{"uri": "/assets/content/morning/a.jpg", "width": 3, "height": 4}],
            }]}, ensure_ascii=False), encoding="utf-8")
            (site / "assets" / "content" / "morning" / "a.jpg").write_bytes(b"seed")
            store = AdminStore(data, seed, secure_cookies=False)
            store.bootstrap("admin", "temporary-password")
            output = root / "mirror"
            manifest = build_snapshot(data_dir=data, site_root=site, output=output)
            self.assertEqual(manifest["counts"]["morning"], 1)
            self.assertTrue((output / "reader" / "index.html").is_file())
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "manifest.json").is_file())
            self.assertNotIn("管理员入口", (output / "index.html").read_text(encoding="utf-8"))
            self.assertIn('<base href="/reader/">', (output / "index.html").read_text(encoding="utf-8"))
            self.assertEqual((output / "assets" / "content" / "morning" / "a.jpg").read_bytes(), b"seed")
            self.assertNotIn("admin.sqlite3", {path.name for path in output.rglob("*")})

    def test_snapshot_includes_published_uploads_and_removes_archived_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            site, data = root / "site", root / "data"
            site.mkdir()
            store = AdminStore(data, secure_cookies=False)
            store.bootstrap("admin", "temporary-password")
            (data / "media" / "daily.jpg").write_bytes(b"published image")
            item = {"id": "daily-001", "date": "2026-10-19", "channel": "晨修", "title": "Daily",
                    "segments": [{"uri": "/media/daily.jpg", "width": 100, "height": 200}]}
            with store._db() as db:
                db.execute("INSERT INTO content VALUES (?,?,?,0,'now','now')", (item["id"], json.dumps(item), "published"))
                db.execute("INSERT INTO content VALUES ('private-draft',?,'draft',0,'now','now')", (json.dumps(dict(item, id="private-draft")),))
            first = root / "first"
            manifest = build_snapshot(data_dir=data, site_root=site, output=first)
            self.assertEqual(manifest["counts"]["all"], 1)
            self.assertTrue((first / "media" / "daily.jpg").is_file())
            self.assertFalse((first / "reader" / "private-draft.html").exists())
            with store._db() as db:
                db.execute("UPDATE content SET status='archived' WHERE id='daily-001'")
                store._bump(db)
            second = root / "second"
            updated = build_snapshot(data_dir=data, site_root=site, output=second)
            self.assertEqual(updated["counts"]["all"], 0)
            self.assertFalse((second / "reader" / "daily-001.html").exists())
            self.assertFalse((second / "media" / "daily.jpg").exists())

    def test_backup_uses_sqlite_snapshot_and_rotates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root / "data"
            store = AdminStore(data, secure_cookies=False)
            store.bootstrap("admin", "temporary-password")
            backup = root / "backups"
            archive = backup_once(data, backup)
            self.assertTrue(archive.is_file())
            if os.name != "nt":
                self.assertEqual(archive.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
