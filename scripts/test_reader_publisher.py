import datetime as dt
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
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

    def test_generated_at_is_outside_release_signature(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "worker.js"
            path.write_text("v1")
            files = {"reader/index.html": "abc"}
            with patch.object(publisher, "SOURCE", path):
                older = publisher.signature({"files": files, "contentVersion": 2, "generatedAt": "2026-10-19T00:00:00+00:00"})
                newer = publisher.signature({"files": files, "contentVersion": 2, "generatedAt": "2026-10-24T12:00:00+00:00"})
                unmarked = publisher.signature({"files": files, "contentVersion": 2})
                changed = publisher.signature({"files": {"reader/index.html": "def"}, "contentVersion": 2,
                                               "generatedAt": "2026-10-24T12:00:00+00:00"})
            self.assertEqual(older, newer)
            self.assertEqual(newer, unmarked)
            self.assertNotEqual(newer, changed)

    def test_publish_state_refreshes_verified_at_and_keeps_deployment(self):
        previous = {"signature": "same", "deploymentId": "dep-1", "note": "核对通过",
                    "verifiedAt": "2026-10-19T00:00:00+00:00", "counts": {"all": 1}}
        manifest = {"contentVersion": 2, "counts": {"all": 211, "morning": 100, "mission": 111}}
        state = publisher.publish_state(previous, manifest, "same")
        self.assertEqual(previous["verifiedAt"], "2026-10-19T00:00:00+00:00")
        self.assertEqual(state["signature"], "same")
        self.assertEqual(state["deploymentId"], "dep-1")
        self.assertEqual(state["note"], "核对通过")
        self.assertEqual(state["contentVersion"], 2)
        self.assertEqual(state["counts"], manifest["counts"])
        self.assertEqual(state["hostname"], publisher.HOSTNAME)
        self.assertGreater(dt.datetime.fromisoformat(state["verifiedAt"]),
                           dt.datetime.fromisoformat(previous["verifiedAt"]))
        replaced = publisher.publish_state(previous, manifest, "new", deployment_id="dep-2")
        self.assertEqual(replaced["deploymentId"], "dep-2")
        self.assertEqual(replaced["signature"], "new")
        self.assertEqual(replaced["note"], "核对通过")
        cleared = publisher.publish_state(previous, manifest, "new", deployment_id=None)
        self.assertIsNone(cleared["deploymentId"])

    def _manifest(self):
        return {"contentVersion": 2, "counts": {"all": 211, "morning": 100, "mission": 111},
                "files": {"reader/index.html": "abc"}, "generatedAt": "2026-10-24T12:00:00+00:00"}

    def _run_main(self, *, previous, current_signature, extra_args=(), verify_public=None):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work = root / "work"
            snapshot = root / "snapshot"
            work.mkdir()
            snapshot.mkdir()
            state_file = work / "state.json"
            raw_previous = None
            if previous is not None:
                raw_previous = json.dumps(previous, ensure_ascii=False, indent=2)
                state_file.write_text(raw_previous, encoding="utf-8")
            argv = ["deploy-reader-failover.py", "--snapshot-directory", str(snapshot), *extra_args]
            stdout = io.StringIO()
            verify = verify_public if verify_public is not None else lambda *args, **kwargs: None
            api_calls = []

            def fake_api(token, path, method="GET", payload=None, raw=None, content_type=None):
                api_calls.append((method, path))
                if path.endswith("/deployments"):
                    return {"id": "prior"}
                if path.endswith("/subdomain"):
                    return {"enabled": False}
                raise AssertionError(path)

            verify_public_patch = patch.object(publisher, "verify_public", side_effect=verify)
            publish_assets_patch = patch.object(publisher, "publish_assets", return_value={"deployment_id": "dep-new"})
            read_token_patch = patch.object(publisher, "read_token", return_value="test-token")
            patches = [
                patch.object(publisher, "WORK", work),
                patch.object(publisher, "validate_snapshot", return_value=self._manifest()),
                patch.object(publisher, "signature", return_value=current_signature),
                verify_public_patch,
                publish_assets_patch,
                patch.object(publisher, "bind_domain"),
                read_token_patch,
                patch.object(publisher, "api", side_effect=fake_api),
                patch.object(publisher.sys, "argv", argv),
            ]
            mocks = {item: item.start() for item in patches}
            try:
                with redirect_stdout(stdout):
                    code = publisher.main()
            finally:
                for item in patches:
                    item.stop()
            state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else None
            raw_state = state_file.read_text(encoding="utf-8") if state_file.exists() else None
            return {
                "code": code,
                "stdout": stdout.getvalue(),
                "state": state,
                "raw_state": raw_state,
                "raw_previous": raw_previous,
                "partial_state": (work / "state.new").exists(),
                "api_calls": api_calls,
                "publish_assets": mocks[publish_assets_patch],
                "read_token": mocks[read_token_patch],
                "verify_public": mocks[verify_public_patch],
            }

    def test_skip_path_refreshes_verified_at_without_deploy(self):
        previous = {"signature": "same", "contentVersion": 2, "counts": {"all": 1},
                    "verifiedAt": "2026-10-19T00:00:00+00:00", "deploymentId": "dep-1",
                    "hostname": publisher.HOSTNAME, "note": "核对通过"}
        result = self._run_main(previous=previous, current_signature="same")
        self.assertEqual(result["code"], 0)
        self.assertIn("publisher state verifiedAt refreshed", result["stdout"])
        self.assertIn("public snapshot verified; no deployment needed", result["stdout"])
        self.assertEqual(result["publish_assets"].call_count, 0)
        self.assertEqual(result["read_token"].call_count, 0)
        self.assertEqual(result["api_calls"], [])
        self.assertFalse(result["partial_state"])
        state = result["state"]
        self.assertEqual(state["signature"], "same")
        self.assertEqual(state["deploymentId"], "dep-1")
        self.assertEqual(state["contentVersion"], 2)
        self.assertEqual(state["counts"]["all"], 211)
        self.assertEqual(state["note"], "核对通过")
        self.assertEqual(state["hostname"], publisher.HOSTNAME)
        self.assertIn("核对通过", result["raw_state"])
        self.assertNotIn("\\u6838", result["raw_state"])
        self.assertGreater(dt.datetime.fromisoformat(state["verifiedAt"]),
                           dt.datetime.fromisoformat(previous["verifiedAt"]))
        self.assertFalse(result["verify_public"].call_args.kwargs["full"])

    def test_non_ascii_state_round_trip_ignores_process_locale(self):
        # Path.read_text() with no encoding follows the process locale (GBK on the
        # publisher host). Force that default to ASCII so this still fails if the
        # publisher forgets encoding="utf-8", even when the CI locale is UTF-8.
        previous = {"signature": "same", "contentVersion": 2, "counts": {"all": 211},
                    "verifiedAt": "2026-10-19T00:00:00+00:00", "deploymentId": "dep-1",
                    "hostname": publisher.HOSTNAME, "note": "核对通过"}
        real_text_encoding = io.text_encoding

        def ascii_default(encoding=None, *args, **kwargs):
            if encoding in (None, "locale"):
                return "ascii"
            return real_text_encoding(encoding, *args, **kwargs)

        with patch.object(io, "text_encoding", side_effect=ascii_default):
            result = self._run_main(previous=previous, current_signature="same")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["state"]["note"], "核对通过")
        self.assertEqual(result["state"]["deploymentId"], "dep-1")
        self.assertIn("核对通过", result["raw_state"])
        self.assertGreater(dt.datetime.fromisoformat(result["state"]["verifiedAt"]),
                           dt.datetime.fromisoformat(previous["verifiedAt"]))

    def test_verify_only_does_not_record_undeployed_signature(self):
        previous = {"signature": "old", "contentVersion": 2, "counts": {"all": 211},
                    "verifiedAt": "2026-10-19T00:00:00+00:00", "deploymentId": "dep-1",
                    "hostname": publisher.HOSTNAME}
        result = self._run_main(previous=previous, current_signature="new", extra_args=["--verify-only"])
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["raw_state"], result["raw_previous"])
        self.assertNotIn("publisher state verifiedAt refreshed", result["stdout"])
        self.assertIn("public snapshot verified; no deployment needed", result["stdout"])
        self.assertEqual(result["publish_assets"].call_count, 0)
        self.assertEqual(result["read_token"].call_count, 0)

    def test_verify_only_without_prior_state_does_not_invent_deployment(self):
        result = self._run_main(previous=None, current_signature="new", extra_args=["--verify-only"])
        self.assertEqual(result["code"], 0)
        self.assertIsNone(result["state"])
        self.assertEqual(result["publish_assets"].call_count, 0)

    def test_failed_public_verify_leaves_state_file_unchanged(self):
        previous = {"signature": "same", "verifiedAt": "2026-10-19T00:00:00+00:00", "deploymentId": "dep-1",
                    "note": "核对通过"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work = root / "work"
            snapshot = root / "snapshot"
            work.mkdir()
            snapshot.mkdir()
            state_file = work / "state.json"
            raw_previous = json.dumps(previous, ensure_ascii=False, indent=2)
            state_file.write_text(raw_previous, encoding="utf-8")
            stdout = io.StringIO()

            def reject(*args, **kwargs):
                raise RuntimeError("public snapshot mismatch: health.json")

            with patch.object(publisher, "WORK", work), \
                    patch.object(publisher, "validate_snapshot", return_value=self._manifest()), \
                    patch.object(publisher, "signature", return_value="same"), \
                    patch.object(publisher, "verify_public", side_effect=reject), \
                    patch.object(publisher, "publish_assets", side_effect=AssertionError("deploy")), \
                    patch.object(publisher.sys, "argv",
                                 ["deploy-reader-failover.py", "--snapshot-directory", str(snapshot)]):
                with redirect_stdout(stdout), self.assertRaises(RuntimeError):
                    publisher.main()
            self.assertEqual(state_file.read_text(encoding="utf-8"), raw_previous)
            self.assertFalse((work / "state.new").exists())
            self.assertNotIn("no deployment needed", stdout.getvalue())
            self.assertNotIn("verifiedAt refreshed", stdout.getvalue())

    def test_dry_run_does_not_refresh_state(self):
        previous = {"signature": "same", "verifiedAt": "2026-10-19T00:00:00+00:00", "deploymentId": "dep-1"}
        result = self._run_main(previous=previous, current_signature="same", extra_args=["--dry-run"])
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["raw_state"], result["raw_previous"])
        self.assertIn("dry run: no Cloudflare changes", result["stdout"])
        self.assertEqual(result["verify_public"].call_count, 0)
        self.assertEqual(result["publish_assets"].call_count, 0)

    def test_deploy_path_records_new_deployment_and_keeps_extra_fields(self):
        previous = {"signature": "old", "contentVersion": 1, "counts": {"all": 1},
                    "verifiedAt": "2026-10-19T00:00:00+00:00", "deploymentId": "dep-1",
                    "hostname": publisher.HOSTNAME, "note": "核对通过"}
        result = self._run_main(previous=previous, current_signature="new")
        self.assertEqual(result["code"], 0)
        self.assertIn("deployed and verified https://reader.bytelanework.com", result["stdout"])
        self.assertEqual(result["read_token"].call_count, 1)
        self.assertEqual(result["publish_assets"].call_count, 1)
        self.assertEqual([method for method, _path in result["api_calls"]], ["GET", "POST"])
        state = result["state"]
        self.assertEqual(state["signature"], "new")
        self.assertEqual(state["deploymentId"], "dep-new")
        self.assertEqual(state["contentVersion"], 2)
        self.assertEqual(state["counts"]["all"], 211)
        self.assertEqual(state["note"], "核对通过")
        self.assertGreater(dt.datetime.fromisoformat(state["verifiedAt"]),
                           dt.datetime.fromisoformat(previous["verifiedAt"]))
        self.assertFalse(result["partial_state"])

    def test_force_deploys_when_signature_matches(self):
        previous = {"signature": "same", "verifiedAt": "2026-10-19T00:00:00+00:00", "deploymentId": "dep-1",
                    "note": "核对通过"}
        result = self._run_main(previous=previous, current_signature="same", extra_args=["--force"])
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["publish_assets"].call_count, 1)
        self.assertEqual(result["state"]["signature"], "same")
        self.assertEqual(result["state"]["deploymentId"], "dep-new")
        self.assertEqual(result["state"]["note"], "核对通过")
        self.assertNotIn("no deployment needed", result["stdout"])


if __name__ == "__main__":
    unittest.main()
