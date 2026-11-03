"""Whitelist checks for the Expo Router static fallback.

Run with ``python -m unittest scripts.test_serve_static``.
"""
from __future__ import annotations

import http.client
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_SPEC = importlib.util.spec_from_file_location(
    "serve_static", Path(__file__).with_name("serve-static.py")
)
assert _SPEC and _SPEC.loader
serve_static = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(serve_static)

from admin_backend import AdminStore  # noqa: E402

SPA_MARKER = "SPA-ENTRY-MARKER"
SECRET = "OUTSIDE-SECRET-SHOULD-NOT-LEAK"
HASHED_BODY = "hashed-static-body"
NESTED_MARKER = "NESTED-INDEX"


class QuietHandler(serve_static.SpaHandler):
    def log_message(self, fmt, *args):
        return


class SpaFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.site = root / "site"
        cls.site.mkdir()
        cls.outside = root / "secret-outside.txt"
        cls.outside.write_text(SECRET, encoding="utf-8")
        (cls.site / "index.html").write_text(
            f"<!doctype html><title>home</title>{SPA_MARKER}",
            encoding="utf-8",
        )
        assets = cls.site / "assets"
        assets.mkdir()
        (assets / "keep.txt").write_text("keep-me", encoding="utf-8")
        hashed = "app." + ("a" * 32) + ".js"
        (cls.site / hashed).write_text(HASHED_BODY, encoding="utf-8")
        cls.hashed_name = hashed
        nested = cls.site / "nested"
        nested.mkdir()
        (nested / "index.html").write_text(NESTED_MARKER, encoding="utf-8")
        data = root / "data"
        cls.store = AdminStore(data, secure_cookies=True)
        handler = lambda *args: QuietHandler(*args, directory=str(cls.site))  # noqa: E731
        cls.httpd = serve_static.LimitedHTTPServer(("127.0.0.1", 0), handler, max_workers=8)
        cls.httpd.allowed_hosts = {"prayer.diagport.com", "localhost", "127.0.0.1", "::1"}
        cls.httpd.admin_store = cls.store
        cls.httpd.request_limiter = serve_static.MutationRateLimiter()
        cls.httpd.ingest_limiter = serve_static.IngestLimiter()
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def request(self, method, path, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        header_map = {"Accept-Encoding": "identity"}
        header_map.update(headers or {})
        connection.request(method, path, headers=header_map)
        response = connection.getresponse()
        payload = response.read()
        status = response.status
        header_items = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return status, header_items, payload

    def test_exact_and_dynamic_routes_return_spa_entry(self):
        routes = [
            "/prayers",
            "/prayers/",
            "/prayers?from=home",
            "/testimonies",
            "/profile",
            "/about",
            "/compose",
            "/compose/",
            "/legal/community",
            "/legal/privacy",
            "/content/mission-20261017-090",
            "/content/morning-20261018-5305d48efd12/",
            "/prayer/seed-sudan-peace",
            "/prayer/user-1730580000000-ab12cd",
        ]
        entry = (self.site / "index.html").read_bytes()
        home_status, home_headers, home_body = self.request("GET", "/")
        self.assertEqual(home_status, 200)
        self.assertEqual(home_body, entry)
        for route in routes:
            status, headers, body = self.request("GET", route)
            self.assertEqual(status, 200, route)
            self.assertEqual(body, entry, route)
            self.assertIn("text/html", headers["content-type"])
            for name in (
                "x-content-type-options",
                "referrer-policy",
                "x-frame-options",
                "permissions-policy",
                "cross-origin-resource-policy",
                "content-security-policy",
                "cache-control",
                "strict-transport-security",
                "vary",
            ):
                self.assertEqual(headers[name], home_headers[name], f"{route} {name}")
        status, headers, body = self.request("HEAD", "/prayers")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertIn("text/html", headers["content-type"])
        self.assertEqual(headers["cache-control"], "no-cache")

    def test_unknown_paths_assets_and_traversal_stay_404(self):
        missing = [
            "/unknown",
            "/prayers/extra",
            "/Prayers",
            "/legal",
            "/legal/other",
            "/content",
            "/content/",
            "/content/mission-20261017-090/extra",
            "/content/has.dot",
            "/content/%2e%2e",
            "/content/%2e%2e/",
            "/foo/..",
            "/prayer",
            "/prayer/",
            "/assets/missing.png",
            "/assets/missing.js",
            "/.env",
            "/.well-known/security.txt",
            "/../secret-outside.txt",
            "/%2e%2e/secret-outside.txt",
            "/content/../secret-outside.txt",
            "/prayers/../../secret-outside.txt",
        ]
        for route in missing:
            status, _headers, body = self.request("GET", route)
            self.assertEqual(status, 404, route)
            self.assertNotIn(SPA_MARKER.encode(), body, route)
            self.assertNotIn(SECRET.encode(), body, route)
        status, headers, body = self.request("GET", "/assets/keep.txt")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"keep-me")
        self.assertNotIn(SPA_MARKER.encode(), body)
        status, headers, body = self.request("GET", "/" + self.hashed_name)
        self.assertEqual(status, 200)
        self.assertEqual(body, HASHED_BODY.encode())
        self.assertIn("max-age=31536000", headers["cache-control"])
        self.assertIn("immutable", headers["cache-control"])
        status, _headers, body = self.request("GET", "/nested")
        self.assertEqual(status, 200)
        self.assertEqual(body, NESTED_MARKER.encode())
        status, _headers, body = self.request("GET", "/nested/")
        self.assertEqual(status, 200)
        self.assertEqual(body, NESTED_MARKER.encode())

    def test_api_admin_and_reader_are_not_rewritten(self):
        status, headers, body = self.request("GET", "/api/content")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["content-type"])
        payload = json.loads(body)
        self.assertIn("items", payload)
        self.assertNotIn(SPA_MARKER.encode(), body)
        status, headers, body = self.request("GET", "/api/does-not-exist")
        self.assertEqual(status, 404)
        self.assertNotIn(SPA_MARKER.encode(), body)
        status, headers, body = self.request("POST", "/api/content")
        self.assertEqual(status, 405)
        self.assertIn("application/json", headers["content-type"])
        self.assertNotIn(SPA_MARKER.encode(), body)
        status, _headers, body = self.request("GET", "/admin")
        self.assertEqual(status, 200)
        self.assertIn("同工管理".encode(), body)
        self.assertNotIn(SPA_MARKER.encode(), body)
        status, headers, body = self.request("GET", "/reader")
        self.assertEqual(status, 302)
        self.assertEqual(headers["location"], "/reader/index.html")
        self.assertNotIn(SPA_MARKER.encode(), body)
        status, _headers, body = self.request("GET", "/reader/index.html")
        self.assertEqual(status, 200)
        self.assertIn("轻量阅读".encode(), body)
        self.assertNotIn(SPA_MARKER.encode(), body)
        status, _headers, body = self.request("GET", "/reader/does-not-exist.html")
        self.assertEqual(status, 404)
        self.assertNotIn(SPA_MARKER.encode(), body)
        status, _headers, body = self.request("GET", "/media/missing.jpg")
        self.assertEqual(status, 404)
        self.assertNotIn(SPA_MARKER.encode(), body)

    def test_other_methods_and_host_guards_do_not_serve_the_shell(self):
        for method in ("POST", "PUT", "PATCH"):
            status, _headers, body = self.request(method, "/prayers")
            self.assertEqual(status, 404, method)
            self.assertNotIn(SPA_MARKER.encode(), body)
        status, headers, body = self.request(
            "GET",
            "/prayers",
            {"Host": "prayer.diagport.com", "X-Forwarded-Proto": "http"},
        )
        self.assertEqual(status, 308)
        self.assertIn("/prayers", headers["location"])
        self.assertTrue(headers["location"].startswith("https://"))
        self.assertNotIn(SPA_MARKER.encode(), body)
        status, _headers, body = self.request("GET", "/prayers", {"Host": "evil.example"})
        self.assertEqual(status, 421)
        self.assertNotIn(SPA_MARKER.encode(), body)

    def test_route_predicate_matches_the_whitelist_only(self):
        self.assertEqual(
            serve_static.SPA_EXACT_ROUTES,
            frozenset({
                "/prayers",
                "/testimonies",
                "/profile",
                "/about",
                "/compose",
                "/legal/community",
                "/legal/privacy",
            }),
        )
        self.assertTrue(serve_static.is_spa_client_route("/prayers/"))
        self.assertTrue(serve_static.is_spa_client_route("/content/mission-20261017-090"))
        self.assertFalse(serve_static.is_spa_client_route("/api/content"))
        self.assertFalse(serve_static.is_spa_client_route("/admin"))
        self.assertFalse(serve_static.is_spa_client_route("/reader/index.html"))
        self.assertFalse(serve_static.is_spa_client_route("/content/a/b"))
        self.assertFalse(serve_static.is_spa_client_route("/content/has.dot"))
        self.assertFalse(serve_static.is_spa_client_route("/../prayers"))
        self.assertFalse(serve_static.is_spa_client_route("/.env"))


if __name__ == "__main__":
    unittest.main()
