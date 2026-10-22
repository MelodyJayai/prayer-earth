#!/usr/bin/env python3
"""Serve an Expo static export with client-side route fallback.

Expo's static export keeps dynamic routes as placeholders. A small fallback
server lets direct links such as /content/mission-20261017-090 load index.html,
then Expo Router resolves the route in the browser.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import importlib.util
import io
import re
import threading
import time
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from admin_backend import AdminRequestMixin, AdminStore


_reader_spec = importlib.util.spec_from_file_location(
    "prayer_reader", Path(__file__).with_name("generate-reader.py")
)
assert _reader_spec and _reader_spec.loader
_reader = importlib.util.module_from_spec(_reader_spec)
_reader_spec.loader.exec_module(_reader)


COMPRESSIBLE = {".html", ".js", ".css", ".json", ".svg", ".txt"}


class MutationRateLimiter:
    """Small in-process guard for authenticated write bursts.

    The login endpoint has its own persistent per-account limiter. This guard
    adds a cheap second layer for upload, password and account-management
    requests so a stolen session cannot generate an unbounded write burst.
    """

    def __init__(self, limit: int = 30, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._events: dict[str, collections.deque[float]] = {}

    def allow(self, identity: str) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events.setdefault(identity, collections.deque())
            cutoff = now - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            if len(self._events) > 2048:
                stale = [key for key, value in self._events.items() if not value or value[-1] <= cutoff]
                for key in stale[:1024]:
                    self._events.pop(key, None)
            return True


class LimitedHTTPServer(ThreadingHTTPServer):
    """Bound origin concurrency so slow clients cannot create unlimited threads."""

    daemon_threads = True
    request_queue_size = 64

    def __init__(self, *args, max_workers: int = 64, **kwargs):
        super().__init__(*args, **kwargs)
        self._slots = threading.BoundedSemaphore(max_workers)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


@lru_cache(maxsize=32)
def compressed_file(path: str, modified: int, size: int) -> bytes:
    """Cache small text responses; the file signature invalidates old versions."""
    return gzip.compress(Path(path).read_bytes(), compresslevel=6, mtime=0)


class SpaHandler(AdminRequestMixin, SimpleHTTPRequestHandler):
    server_version = "PrayerEarth"
    sys_version = ""

    def __init__(self, *args, directory: str, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def _reject_bad_host(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0].lower().strip("[]")
        if host in self.server.allowed_hosts:
            return False
        self.send_error(421, "Misdirected Request")
        self.close_connection = True
        return True

    def _redirect_insecure(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0].lower().strip("[]")
        forwarded = self.headers.get("X-Forwarded-Proto", "https").split(",", 1)[0].strip().lower()
        if host == "prayer.diagport.com" and forwarded == "http":
            target = "https://" + self.headers.get("Host", "prayer.diagport.com") + self.path
            self.send_response(308)
            self.send_header("Location", target)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        return False

    def prepare_route(self) -> None:
        path = urlsplit(self.path).path
        candidate = Path(self.directory, path.lstrip("/"))
        if path == "/":
            self.path = "/index.html"
        elif path.startswith("/.") or "/." in path:
            return
        elif candidate.is_dir() and (candidate / "index.html").is_file():
            self.path = path.rstrip("/") + "/index.html"
        elif not candidate.exists() and Path(path).suffix == "" and (
            path.startswith("/content/") or path.startswith("/prayer/")
        ):
            self.path = "/index.html"

    def do_GET(self) -> None:  # noqa: N802
        if self._reject_bad_host():
            return
        if self._redirect_insecure():
            return
        if self.handle_admin_request():
            return
        if self.serve_managed_page():
            return
        self.prepare_route()
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if self._reject_bad_host():
            return
        if self._redirect_insecure():
            return
        if self.handle_admin_request():
            return
        if self.serve_managed_page(head_only=True):
            return
        self.prepare_route()
        super().do_HEAD()

    def do_POST(self) -> None:  # noqa: N802
        if self._reject_bad_host():
            return
        if self._redirect_insecure():
            return
        if not self.handle_admin_request():
            self.send_error(404)

    def do_PUT(self) -> None:  # noqa: N802
        if self._reject_bad_host():
            return
        if self._redirect_insecure():
            return
        if not self.handle_admin_request():
            self.send_error(404)

    def do_PATCH(self) -> None:  # noqa: N802
        if self._reject_bad_host():
            return
        if self._redirect_insecure():
            return
        if not self.handle_admin_request():
            self.send_error(404)

    def serve_managed_page(self, *, head_only: bool = False) -> bool:
        path = urlsplit(self.path).path
        if path in {"/admin", "/admin/", "/admin.html"}:
            self.send_html(Path(__file__).with_name("admin.html").read_text(encoding="utf-8"), head_only=head_only)
            return True
        if path == "/reader":
            self.send_response(302)
            self.send_header("Location", "/reader/index.html")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        if path.startswith("/reader/"):
            if path == "/reader/":
                path = "/reader/index.html"
            markup = _reader.render_feed_reader(path, self.server.admin_store.public_items())
            if markup is None:
                self.send_error(404, "Content not found")
            else:
                self.send_html(markup, head_only=head_only)
            return True
        if path.startswith("/media/"):
            # Media may only reference the dedicated upload directory.
            root = self.server.admin_store.media_dir.resolve()
            requested = (root / path[len("/media/"):]).resolve()
            if not requested.is_relative_to(root) or not requested.is_file():
                self.send_error(404)
                return True
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(str(requested)))
            self.send_header("Content-Length", str(requested.stat().st_size))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not head_only:
                with requested.open("rb") as stream:
                    self.copyfile(stream, self.wfile)
            return True
        return False

    def send_html(self, markup: str, *, head_only: bool = False) -> None:
        body = markup.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def end_headers(self) -> None:
        path = Path(self.translate_path(self.path))
        if path.suffix.lower() == ".html" or path.is_dir():
            # Entry pages must see a new release instead of stale bundle URLs.
            self.send_header("Cache-Control", "no-cache")
        elif path.is_file() and re.search(r"[.-][a-f0-9]{32}\.", path.name):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        if path.suffix.lower() in COMPRESSIBLE:
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if getattr(self.server.admin_store, "secure_cookies", False):
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self' data:; form-action 'self'")
        super().end_headers()

    def send_head(self):
        path = Path(self.translate_path(self.path))
        accepts_gzip = False
        for entry in self.headers.get("Accept-Encoding", "").lower().split(","):
            parts = [part.strip() for part in entry.split(";")]
            if parts[0] != "gzip":
                continue
            quality = next((part[2:] for part in parts[1:] if part.startswith("q=")), "1")
            try:
                accepts_gzip = float(quality) > 0
            except ValueError:
                pass
        if accepts_gzip and path.suffix.lower() in COMPRESSIBLE and path.is_file():
            stat = path.stat()
            if 256 <= stat.st_size <= 8 * 1024 * 1024:
                body = compressed_file(str(path), stat.st_mtime_ns, stat.st_size)
                self.send_response(200)
                self.send_header("Content-Type", self.guess_type(str(path)))
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
                self.end_headers()
                return io.BytesIO(body)
        return super().send_head()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--directory", required=True, help="Expo export directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--data-directory", type=Path, default=Path(__file__).resolve().parents[1] / ".local-data")
    parser.add_argument("--insecure-cookie", action="store_true", help="Allow local HTTP testing only")
    parser.add_argument("--max-workers", type=int, default=64)
    parser.add_argument("--allowed-host", action="append", default=["prayer.diagport.com", "localhost", "127.0.0.1", "::1"])
    args = parser.parse_args()

    root = str(Path(args.directory).resolve())
    server = LimitedHTTPServer(
        (args.host, args.port),
        lambda *handler_args: SpaHandler(*handler_args, directory=root),
        max_workers=args.max_workers,
    )
    server.allowed_hosts = {host.lower().split(":", 1)[0].strip("[]") for host in args.allowed_host}
    server.admin_store = AdminStore(args.data_directory, Path(root) / "content-seed.json")
    server.request_limiter = MutationRateLimiter()
    server.admin_store.secure_cookies = not args.insecure_cookie
    print(f"Serving {root} on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
