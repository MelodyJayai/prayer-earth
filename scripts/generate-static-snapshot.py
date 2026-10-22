#!/usr/bin/env python3
"""Build a self-contained, read-only snapshot of published trial content.

The output contains only HTML, images, and a small manifest. It has no admin
API, database, JavaScript, or dependency on the primary origin. A provider
adapter can upload the resulting directory to an independent static host.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from admin_backend import AdminStore


_READER_SPEC = importlib.util.spec_from_file_location(
    "prayer_reader", Path(__file__).with_name("generate-reader.py")
)
assert _READER_SPEC and _READER_SPEC.loader
_READER = importlib.util.module_from_spec(_READER_SPEC)
_READER_SPEC.loader.exec_module(_READER)
render_feed_reader = _READER.render_feed_reader


def safe_relative(uri: str) -> Path:
    parsed = PurePosixPath(uri.lstrip("/"))
    if not uri.startswith("/") or not parsed.parts or any(part in ("", ".", "..") for part in parsed.parts):
        raise ValueError(f"unsafe content URI: {uri!r}")
    return Path(*parsed.parts)


def copy_uri(uri: str, *, site_root: Path, data_dir: Path, output: Path) -> str:
    relative = safe_relative(uri)
    if relative.parts[0] == "media":
        source = data_dir / relative
    elif relative.parts[0] == "assets":
        source = site_root / relative
    else:
        raise ValueError(f"unsupported content URI: {uri!r}")
    source = source.resolve()
    allowed = (data_dir / "media").resolve() if relative.parts[0] == "media" else site_root.resolve()
    if not source.is_relative_to(allowed) or not source.is_file():
        raise FileNotFoundError(source)
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return "/" + relative.as_posix()


def sha256_tree(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in {"manifest.json", "health.json"}:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[path.relative_to(root).as_posix()] = digest
    return result


def build_snapshot(*, data_dir: Path, site_root: Path, output: Path) -> dict:
    store = AdminStore(data_dir, secure_cookies=True)
    feed = store.content(public=True)
    items = feed["items"]
    output.mkdir(parents=True, exist_ok=True)
    copied = set()
    for item in items:
        for segment in item.get("segments", []):
            uri = str(segment.get("uri", ""))
            if uri not in copied:
                segment["uri"] = copy_uri(uri, site_root=site_root, data_dir=data_dir, output=output)
                copied.add(uri)
    reader = output / "reader"
    reader.mkdir(parents=True, exist_ok=True)
    routes = ["index.html", "morning.html", "mission.html"]
    routes.extend(f'{item["id"]}.html' for item in items)
    for route in routes:
        markup = render_feed_reader(route, items, include_admin=False)
        if markup is None:
            raise ValueError(f"reader route failed: {route}")
        markup = markup.replace("返回主应用", "阅读首页")
        markup = markup.replace("</footer>", f' · 备用阅读 · 内容版本 {feed["version"]}</footer>')
        (reader / route).write_text(markup, encoding="utf-8")
    # Links in the reader are relative to /reader/. A plain static host must
    # resolve them correctly even when it serves the copied root index.
    root_index = (reader / "index.html").read_text(encoding="utf-8")
    (output / "index.html").write_text(root_index.replace("<head>", '<head>\n  <base href="/reader/">'), encoding="utf-8")
    counts = {
        "all": len(items),
        "morning": sum(1 for item in items if item.get("channel") == "晨修"),
        "mission": sum(1 for item in items if item.get("channel") == "宣教动态与见证"),
    }
    manifest = {
        "schema": 1,
        "contentVersion": feed["version"],
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "counts": counts,
        "files": sha256_tree(output),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    health = {"ok": True, "contentVersion": manifest["contentVersion"], "generatedAt": manifest["generatedAt"], "counts": counts}
    (output / "health.json").write_text(json.dumps(health, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-directory", type=Path, required=True)
    parser.add_argument("--site-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="snapshot-", dir=output.parent))
    try:
        manifest = build_snapshot(data_dir=args.data_directory.resolve(), site_root=args.site_directory.resolve(), output=staging)
        if output.exists():
            backup = output.with_name(output.name + ".previous")
            if backup.exists():
                shutil.rmtree(backup)
            output.replace(backup)
        staging.replace(output)
        previous = output.with_name(output.name + ".previous")
        if previous.exists():
            shutil.rmtree(previous)
        print(json.dumps({"output": str(output), "contentVersion": manifest["contentVersion"], "counts": manifest["counts"]}, ensure_ascii=False))
        return 0
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
