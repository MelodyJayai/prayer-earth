"""Regression checks for archive and daily content in the no-JavaScript reader."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("generate_reader", Path(__file__).with_name("generate-reader.py"))
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.item = {
            "id": "morning-daily-001", "date": "2026-10-19", "channel": "晨修",
            "title": "今日晨修 <script>alert(1)</script>", "excerpt": "约翰福音第一章", "sourceFile": "",
            "segments": [{"uri": "/media/daily-001.jpg", "width": 900, "height": 2400}],
        }

    def test_daily_content_and_images_render_without_scripts(self):
        listing = reader.render_feed_reader("/reader/morning.html", [self.item])
        self.assertIn("morning-daily-001.html", listing)
        self.assertIn("约翰福音第一章", listing)
        detail = reader.render_feed_reader("/reader/morning-daily-001.html", [self.item])
        self.assertIn('src="/media/daily-001.jpg"', detail)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", detail)
        self.assertNotIn("<script>", detail)

    def test_text_news_renders_summary_source_and_unverified_flag(self):
        item = {
            "id": "news-20261027-0123456789ab", "kind": "news", "date": "2026-10-27", "channel": "宗教动态",
            "title": "周报 <script>alert(1)</script>", "summary": "只有短摘要", "excerpt": "只有短摘要",
            "sourceName": "教会通讯", "sourceUrl": "https://example.com/church?q=1",
            "region": "全球", "verified": False, "category": "基督教",
        }
        listing = reader.render_feed_reader("/reader/news.html", [item, self.item])
        self.assertIn("news-20261027-0123456789ab.html", listing)
        self.assertIn("待核实", listing)
        self.assertIn("只有短摘要", listing)
        self.assertNotIn("morning-daily-001", listing)
        detail = reader.render_feed_reader("/reader/news-20261027-0123456789ab.html", [item])
        self.assertIn('rel="noopener noreferrer"', detail)
        self.assertIn('target="_blank"', detail)
        self.assertIn("https://example.com/church?q=1", detail)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", detail)
        self.assertNotIn("<script>", detail)
        self.assertNotIn("<img", detail)
        morning = reader.render_feed_reader("/reader/morning.html", [item, self.item])
        self.assertIn("morning-daily-001", morning)
        self.assertNotIn("news-20261027", morning)
        verified = dict(item, verified=True, title="已核实标题")
        safe = reader.render_feed_reader("/reader/news.html", [verified])
        self.assertNotIn("待核实", safe)
        blocked = dict(item, sourceUrl="javascript:alert(1)")
        rendered = reader.render_feed_reader("/reader/news-20261027-0123456789ab.html", [blocked])
        self.assertNotIn("javascript:", rendered)
        self.assertIn("教会通讯", rendered)

    def test_removed_content_and_unknown_routes_are_not_rendered(self):
        self.assertIsNone(reader.render_feed_reader("/reader/morning-daily-001.html", []))
        self.assertIsNone(reader.render_feed_reader("/reader/../admin.html", [self.item]))
        self.assertNotIn("morning-daily-001", reader.render_feed_reader("/reader/mission.html", [self.item]))

    def test_seed_preserves_hashed_export_image_uri_and_dimensions(self):
        with tempfile.TemporaryDirectory() as folder:
            dist = Path(folder)
            image = dist / "assets" / "assets" / "content" / "morning" / "morning-001-01.abc123.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"test image")
            manifest = {"items": [{
                "id": "morning-001", "date": "2026-06-08", "channel": "晨修", "width": 888, "height": 2200,
                "sourceFile": "original.jpg", "segments": [{"fileName": "morning-001-01.jpg", "width": 888, "height": 2200}],
            }]}
            seed = reader.build_seed(dist, manifest)
            self.assertEqual(seed["items"][0]["segments"][0]["uri"], "/assets/assets/content/morning/morning-001-01.abc123.jpg")
            self.assertEqual(seed["items"][0]["height"], 2200)
            self.assertEqual(reader.write_reader(dist, manifest), 1)
            self.assertTrue((dist / "content-seed.json").is_file())
            self.assertTrue((dist / "reader" / "morning-001.html").is_file())


if __name__ == "__main__":
    unittest.main()
