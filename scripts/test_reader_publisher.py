import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("reader_publisher", Path(__file__).with_name("deploy-reader-failover.py"))
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


class PublisherTests(unittest.TestCase):
    def test_only_public_paths_are_allowed(self):
        for name in ("../admin.sqlite3", "/admin", "admin.sqlite3", "api/content", "media/a.jpg:stream", "media/a.svg", "reader/../a.html"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                publisher.safe_path(name)
        self.assertEqual(str(publisher.safe_path("media/upload/daily.jpg")), "media/upload/daily.jpg")

    def test_archive_rejects_links_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "bad.tar"
            with tarfile.open(archive, "w") as stream:
                entry = tarfile.TarInfo("media/image.jpg")
                entry.type = tarfile.SYMTYPE
                entry.linkname = "../../outside"
                stream.addfile(entry)
            with self.assertRaises(ValueError):
                publisher.extract_delta(archive, root / "snapshot")

    def test_failed_asset_upload_does_not_publish_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "index.html").write_text("reader")
            manifest, _ = publisher.asset_manifest(root)
            hashed = manifest["/index.html"]["hash"]
            with patch.object(publisher, "api", side_effect=[{"jwt": "upload-test", "buckets": [[hashed]]}, RuntimeError("upload failed")]) as api:
                with self.assertRaises(RuntimeError):
                    publisher.publish_assets("test-only", root)
                self.assertEqual(api.call_count, 2)
                self.assertTrue(all(call.args[2] != "PUT" for call in api.call_args_list))

    def test_deletion_and_worker_change_affect_release_signature(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "worker.js"
            path.write_text("v1")
            with patch.object(publisher, "SOURCE", path):
                first = publisher.signature({"files": {"a": "one", "b": "two"}, "contentVersion": 1})
                second = publisher.signature({"files": {"a": "one"}, "contentVersion": 1})
                self.assertNotEqual(first, second)
                path.write_text("v2")
                self.assertNotEqual(second, publisher.signature({"files": {"a": "one"}, "contentVersion": 1}))


if __name__ == "__main__":
    unittest.main()
