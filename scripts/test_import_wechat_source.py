"""Source-folder resolution for the WeChat Save As importer."""

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "import_wechat_content",
    Path(__file__).with_name("import-wechat-content.py"),
)
assert SPEC and SPEC.loader
importer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(importer)


class WechatSourceResolutionTests(unittest.TestCase):
    def test_legacy_directory_wins_when_sibling_also_exists(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root / "repo" / "WeChatImages" / "WeChatImages"
            sibling = root / "WeChatImages"
            legacy.mkdir(parents=True)
            sibling.mkdir()
            resolved = importer.resolve_source_directory(
                env={},
                legacy=legacy,
                sibling=sibling,
            )
            self.assertEqual(resolved, legacy.resolve())

    def test_sibling_directory_is_used_when_legacy_folder_is_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root / "repo" / "WeChatImages" / "WeChatImages"
            sibling = root / "WeChatImages"
            sibling.mkdir()
            resolved = importer.resolve_source_directory(
                env={},
                legacy=legacy,
                sibling=sibling,
            )
            self.assertEqual(resolved, sibling.resolve())

    def test_env_overrides_existing_default_directories(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            chosen = root / "chosen"
            legacy = root / "legacy"
            sibling = root / "sibling"
            for path in (chosen, legacy, sibling):
                path.mkdir()
            resolved = importer.resolve_source_directory(
                env={importer.SOURCE_ENV: str(chosen)},
                legacy=legacy,
                sibling=sibling,
            )
            self.assertEqual(resolved, chosen.resolve())

    def test_blank_env_falls_through_to_legacy_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root / "legacy"
            legacy.mkdir()
            resolved = importer.resolve_source_directory(
                env={importer.SOURCE_ENV: "  "},
                legacy=legacy,
                sibling=root / "missing-sibling",
            )
            self.assertEqual(resolved, legacy.resolve())

    def test_missing_env_directory_does_not_fall_through(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root / "legacy"
            legacy.mkdir()
            missing = root / "missing"
            with self.assertRaises(SystemExit) as caught:
                importer.resolve_source_directory(
                    env={importer.SOURCE_ENV: str(missing)},
                    legacy=legacy,
                    sibling=root / "sibling",
                )
            message = str(caught.exception)
            self.assertIn(importer.SOURCE_ENV, message)
            self.assertIn(str(missing.resolve()), message)

    def test_explicit_source_overrides_env_and_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            chosen = root / "chosen"
            other = root / "other"
            legacy = root / "legacy"
            sibling = root / "sibling"
            for path in (chosen, other, legacy, sibling):
                path.mkdir()
            resolved = importer.resolve_source_directory(
                explicit=chosen,
                env={importer.SOURCE_ENV: str(other)},
                legacy=legacy,
                sibling=sibling,
            )
            self.assertEqual(resolved, chosen.resolve())

    def test_missing_explicit_source_does_not_fall_through(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root / "legacy"
            legacy.mkdir()
            missing = root / "missing"
            with self.assertRaises(SystemExit) as caught:
                importer.resolve_source_directory(
                    explicit=missing,
                    legacy=legacy,
                    sibling=root / "sibling",
                )
            message = str(caught.exception)
            self.assertIn("--source", message)
            self.assertIn(str(missing.resolve()), message)

    def test_relative_source_resolves_from_the_working_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            images = root / "images"
            images.mkdir()
            previous = Path.cwd()
            try:
                os.chdir(root)
                resolved = importer.resolve_source_directory(
                    explicit=Path("images"),
                    env={},
                    legacy=root / "legacy",
                    sibling=root / "sibling",
                )
            finally:
                os.chdir(previous)
            self.assertEqual(resolved, images.resolve())

    def test_missing_defaults_name_the_env_var_and_both_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root / "legacy"
            sibling = root / "sibling"
            with self.assertRaises(SystemExit) as caught:
                importer.resolve_source_directory(env={}, legacy=legacy, sibling=sibling)
            message = str(caught.exception)
            self.assertIn(importer.SOURCE_ENV, message)
            self.assertIn(str(legacy), message)
            self.assertIn(str(sibling), message)

    def test_help_documents_env_and_dry_run(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as caught:
                importer.main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        text = stdout.getvalue()
        self.assertIn(importer.SOURCE_ENV, text)
        self.assertIn("--dry-run", text)
        self.assertIn("--source", text)

    def test_dry_run_lists_top_level_jpg_names_without_writing(self):
        real_manifest = importer.MANIFEST_PATH.read_bytes()
        real_data = importer.DATA_PATH.read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            nested = source / "nested"
            source.mkdir()
            nested.mkdir()
            (source / "Weixin Image_20261026.jpg").write_bytes(b"flat")
            (source / "notes.txt").write_text("skip", encoding="utf-8")
            (nested / "Weixin Image_20261025.jpg").write_bytes(b"nested")
            manifest = root / "manifest.json"
            data = root / "contentData.ts"
            assets = root / "assets"
            manifest.write_text("keep-manifest", encoding="utf-8")
            data.write_text("keep-data", encoding="utf-8")

            def fail_if_called():
                raise AssertionError("dry-run loaded imaging libraries")

            stdout = io.StringIO()
            with patch.object(importer, "MANIFEST_PATH", manifest), patch.object(
                importer, "DATA_PATH", data
            ), patch.object(importer, "ASSET_ROOT", assets), patch.object(
                importer, "require_imaging_libraries", fail_if_called
            ), contextlib.redirect_stdout(stdout):
                code = importer.main(["--dry-run", "--source", str(source)])
            self.assertEqual(code, 0)
            text = stdout.getvalue().splitlines()
            self.assertEqual(text[0], f"source={source.resolve()}")
            self.assertEqual(text[1], "jpg=1")
            self.assertEqual(text[2], "Weixin Image_20261026.jpg")
            self.assertNotIn("notes.txt", stdout.getvalue())
            self.assertNotIn("Weixin Image_20261025.jpg", stdout.getvalue())
            self.assertEqual(manifest.read_text(encoding="utf-8"), "keep-manifest")
            self.assertEqual(data.read_text(encoding="utf-8"), "keep-data")
            self.assertFalse(assets.exists())
        self.assertEqual(importer.MANIFEST_PATH.read_bytes(), real_manifest)
        self.assertEqual(importer.DATA_PATH.read_bytes(), real_data)

    def test_cli_source_overrides_env_and_main_uses_sibling_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            chosen = root / "chosen"
            other = root / "other"
            legacy = root / "repo" / "WeChatImages" / "WeChatImages"
            sibling = root / "WeChatImages"
            chosen.mkdir()
            other.mkdir()
            sibling.mkdir()
            (chosen / "Weixin Image_20261008.jpg").write_bytes(b"chosen")
            (other / "Weixin Image_20261009.jpg").write_bytes(b"other")
            (sibling / "Weixin Image_20261026.jpg").write_bytes(b"sibling")

            overridden = io.StringIO()
            with patch.dict(os.environ, {importer.SOURCE_ENV: str(other)}), contextlib.redirect_stdout(
                overridden
            ):
                code = importer.main(["--dry-run", "--source", str(chosen)])
            self.assertEqual(code, 0)
            self.assertIn("Weixin Image_20261008.jpg", overridden.getvalue())
            self.assertNotIn("Weixin Image_20261009.jpg", overridden.getvalue())

            fallback = io.StringIO()
            with patch.object(importer, "LEGACY_SOURCE", legacy), patch.object(
                importer, "SIBLING_SOURCE", sibling
            ), patch.dict(os.environ, {importer.SOURCE_ENV: ""}, clear=False), contextlib.redirect_stdout(
                fallback
            ):
                code = importer.main(["--dry-run"])
            self.assertEqual(code, 0)
            fallback_text = fallback.getvalue()
            self.assertIn(f"source={sibling.resolve()}", fallback_text)
            self.assertIn("Weixin Image_20261026.jpg", fallback_text)


if __name__ == "__main__":
    unittest.main()
