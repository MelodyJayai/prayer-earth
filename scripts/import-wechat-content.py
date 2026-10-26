"""Import WeChat image posts into the local trial content library.

Option A keeps the PC WeChat "Save As" folder outside git. Resolve that folder
from ``--source``, then ``PRAYER_WECHAT_IMAGES``, then
``<repo>/WeChatImages/WeChatImages`` when the directory exists, then a sibling
``<repo>/../WeChatImages``. ``--dry-run`` only prints the chosen directory and
``.jpg`` names. The real import still classifies, excludes, splits, and writes
the manifest and ``contentData.ts`` as before.

The source folder is intentionally kept outside the generated asset folders. Run
this script again after adding new WeChat exports to refresh the trial build.
Only decodable images that meet the minimum dimensions are copied; this is a
technical filter and does not replace a visual review for sharpness or content
completeness. Exact duplicates and the known non-content holiday greeting are
skipped. Long screenshots are split into texture-safe segments for mobile
devices.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image


PROJECT = Path(__file__).resolve().parents[1]
# Keep this order aligned with scripts/watch-wechat-images.ps1.
SOURCE_ENV = "PRAYER_WECHAT_IMAGES"
LEGACY_SOURCE = PROJECT / "WeChatImages" / "WeChatImages"
SIBLING_SOURCE = PROJECT.parent / "WeChatImages"
ASSET_ROOT = PROJECT / "assets" / "content"
MANIFEST_PATH = PROJECT / "docs" / "content-import-manifest.json"
DATA_PATH = PROJECT / "src" / "contentData.ts"
MAX_SEGMENT_HEIGHT = 4096
EXCLUDED_NAMES = {"Weixin Image_20260925090524_210_169.jpg"}
CHANNEL_OVERRIDES = {
    "Weixin Image_20260714103604_1150_51.jpg": {
        "channel": "morning",
        "reason": "图片内容为 MS 解经／马可福音逐节查经，人工归入晨修",
    },
}


def require_source_directory(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise SystemExit(f"Source folder not found ({label}): {resolved}")
    return resolved


def resolve_source_directory(
    explicit: Path | None = None,
    env: Mapping[str, str] | None = None,
    *,
    legacy: Path | None = None,
    sibling: Path | None = None,
) -> Path:
    """Return the Save As directory. Explicit paths and env do not fall through."""
    environment = os.environ if env is None else env
    legacy_path = LEGACY_SOURCE if legacy is None else legacy
    sibling_path = SIBLING_SOURCE if sibling is None else sibling
    if explicit is not None:
        return require_source_directory(explicit, "--source")
    raw_env = environment.get(SOURCE_ENV, "").strip()
    if raw_env:
        return require_source_directory(Path(raw_env), SOURCE_ENV)
    for candidate in (legacy_path, sibling_path):
        if candidate.is_dir():
            return candidate.resolve()
    raise SystemExit(
        "Source folder not found. Pass --source, set "
        f"{SOURCE_ENV}, or create one of:\n"
        f"  - {legacy_path}\n"
        f"  - {sibling_path}"
    )


def require_imaging_libraries():
    """Import Pillow and numpy before the importer replaces generated assets."""
    try:
        import numpy  # noqa: F401
        from PIL import Image
    except ImportError as error:
        raise SystemExit(
            "Pillow and numpy are required to import WeChat images. "
            "Install them and rerun. --dry-run only checks the source folder."
        ) from error
    return Image


def color_density(image: Image.Image) -> float:
    import numpy as np

    width, height = image.size
    sample = np.asarray(
        image.resize((100, max(1, int(100 * height / width)))).convert("RGB")
    ) / 255.0
    maximum = sample.max(2)
    minimum = sample.min(2)
    saturation = (maximum - minimum) / np.maximum(maximum, 1e-6)
    return float((saturation > 0.22).mean())


def split_image(source: Path, target_dir: Path, stem: str) -> list[dict[str, int | str]]:
    """Write JPEG segments without resizing the source image."""
    from PIL import Image

    segments: list[dict[str, int | str]] = []
    with Image.open(source) as image:
        image = image.convert("RGB")
        width, height = image.size
        start = 0
        index = 1
        while start < height:
            end = min(height, start + MAX_SEGMENT_HEIGHT)
            segment_name = f"{stem}-{index:02d}.jpg"
            destination = target_dir / segment_name
            image.crop((0, start, width, end)).save(
                destination, format="JPEG", quality=90, optimize=True
            )
            segments.append(
                {
                    "fileName": segment_name,
                    "width": width,
                    "height": end - start,
                }
            )
            start = end
            index += 1
    return segments


def read_previous_manifest() -> dict[str, object]:
    """Load the prior manifest so existing source files keep their IDs."""
    if not MANIFEST_PATH.exists():
        return {}
    try:
        value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def previous_ids(manifest: dict[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    raw_items = manifest.get("items", [])
    if not isinstance(raw_items, list):
        return result
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        source_file = raw_item.get("sourceFile")
        item_id = raw_item.get("id")
        if isinstance(source_file, str) and isinstance(item_id, str):
            result[source_file] = item_id
    return result


def stable_item_id(
    channel: str,
    date_key: str,
    digest: str,
    source_file: str,
    old_ids: dict[str, str],
    used_ids: set[str],
) -> str:
    """Reuse a prior source-file ID; derive a deterministic ID for new files."""
    existing = old_ids.get(source_file)
    if existing:
        used_ids.add(existing)
        return existing

    prefix = "mission" if channel == "宣教动态与见证" else "morning"
    candidate = f"{prefix}-{date_key}-{digest[:12]}"
    if candidate in used_ids:
        # A 12-character collision is extraordinarily unlikely, but extending
        # the digest keeps the ID deterministic if it ever occurs.
        candidate = f"{candidate}-{digest[12:20]}"
    used_ids.add(candidate)
    return candidate


def list_source_images(source_dir: Path) -> list[Path]:
    return sorted(source_dir.glob("*.jpg"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source",
        type=Path,
        help=(
            "WeChat Save As directory. Overrides PRAYER_WECHAT_IMAGES. "
            "When omitted, use <repo>/WeChatImages/WeChatImages if that directory "
            "exists, otherwise <repo>/../WeChatImages."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print the resolved source directory and .jpg names without writing "
            "assets, the manifest, or contentData.ts."
        ),
    )
    args = parser.parse_args(argv)
    source_dir = resolve_source_directory(args.source)
    if args.dry_run:
        files = list_source_images(source_dir)
        print(f"source={source_dir}")
        print(f"jpg={len(files)}")
        for path in files:
            print(path.name)
        return 0

    Image = require_imaging_libraries()
    prior_manifest = read_previous_manifest()
    old_ids = previous_ids(prior_manifest)
    for directory in (ASSET_ROOT / "morning", ASSET_ROOT / "mission"):
        directory.mkdir(parents=True, exist_ok=True)
        for old_file in directory.glob("*.jpg"):
            old_file.unlink()

    seen_hashes: set[str] = set()
    # Reserve every prior ID, including files that may be temporarily absent,
    # so a newly derived hash ID can never reuse an old link by accident.
    used_ids: set[str] = set(old_ids.values())
    counts: Counter[str] = Counter()
    items: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for source in list_source_images(source_dir):
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest in seen_hashes:
            counts["duplicate"] += 1
            skipped.append({"sourceFile": source.name, "sha256": digest, "reason": "duplicate"})
            continue
        seen_hashes.add(digest)
        date_match = re.search(r"Image_(\d{8})", source.name)
        if not date_match:
            counts["excluded"] += 1
            skipped.append({"sourceFile": source.name, "sha256": digest, "reason": "missing-date"})
            continue
        date_key = date_match.group(1)
        try:
            with Image.open(source) as image:
                width, height = image.size
                image.verify()
            with Image.open(source) as image:
                density = color_density(image)
        except Exception:
            counts["excluded"] += 1
            skipped.append({"sourceFile": source.name, "sha256": digest, "reason": "unreadable-image"})
            continue
        if source.name in EXCLUDED_NAMES or width < 700 or height < 1800:
            counts["excluded"] += 1
            reason = "known-exclusion" if source.name in EXCLUDED_NAMES else "below-minimum-dimensions"
            skipped.append(
                {
                    "sourceFile": source.name,
                    "sha256": digest,
                    "reason": reason,
                    "width": width,
                    "height": height,
                }
            )
            continue

        # Long photo/text collages are the mission stream. The remaining
        # vertical scripture study sheets form the morning stream. A small
        # explicit override list handles clear editorial exceptions.
        override = CHANNEL_OVERRIDES.get(source.name)
        channel = override["channel"] if override else ("mission" if height >= 8500 or density >= 0.05 else "morning")
        label = "宣教动态与见证" if channel == "mission" else "晨修"
        counts[channel] += 1
        date = f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}"
        item_id = stable_item_id(channel, date_key, digest, source.name, old_ids, used_ids)
        target_dir = ASSET_ROOT / channel
        segments = split_image(source, target_dir, item_id)
        items.append(
            {
                "id": item_id,
                "date": date,
                "channel": label,
                "label": label,
                "sourceFile": source.name,
                "sha256": digest,
                "width": width,
                "height": height,
                "segments": segments,
            }
        )
        if override:
            items[-1]["classificationOverride"] = override["reason"]

    items.sort(key=lambda item: (str(item["date"]), str(item["id"])))
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "source": str(source_dir),
                "counts": dict(counts),
                "maxSegmentHeight": MAX_SEGMENT_HEIGHT,
                "items": items,
                "skipped": skipped,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        'import type { ImageSourcePropType } from "react-native";',
        "",
        'export type ContentChannel = "晨修" | "宣教动态与见证";',
        "export type ImportedContentSegment = { image: ImageSourcePropType; width: number; height: number };",
        "export type ImportedContentItem = {",
        "  id: string; date: string; channel: ContentChannel; label: ContentChannel;",
        "  image: ImageSourcePropType; width: number; height: number; sourceFile: string;",
        "  segments: ImportedContentSegment[]; title: string; excerpt: string; searchText: string;",
        "};",
        "",
        "/** Generated by scripts/import-wechat-content.py. Do not edit manually. */",
        "export const importedContentItems: ImportedContentItem[] = [",
    ]
    for item in items:
        channel_key = "mission" if item["channel"] == "宣教动态与见证" else "morning"
        segments = item["segments"]
        first_segment = segments[0]
        title = f'{item["label"]} · {item["date"]}'
        excerpt = "微信群图片原文，点击查看完整内容。"
        search_text = f'{item["label"]} {item["date"]} {item["sourceFile"]}'
        lines.extend(
            [
                "  {",
                f'    id: {json.dumps(item["id"], ensure_ascii=False)}, date: {json.dumps(item["date"])}, channel: {json.dumps(item["channel"], ensure_ascii=False)}, label: {json.dumps(item["label"], ensure_ascii=False)},',
                f'    image: require("../assets/content/{channel_key}/{first_segment["fileName"]}"), width: {item["width"]}, height: {item["height"]}, sourceFile: {json.dumps(item["sourceFile"], ensure_ascii=False)},',
                f'    title: {json.dumps(title, ensure_ascii=False)}, excerpt: {json.dumps(excerpt, ensure_ascii=False)}, searchText: {json.dumps(search_text, ensure_ascii=False)},',
                "    segments: [",
            ]
        )
        for segment in segments:
            lines.append(
                f'      {{ image: require("../assets/content/{channel_key}/{segment["fileName"]}"), width: {segment["width"]}, height: {segment["height"]} }},'
            )
        lines.extend(["    ],", "  },"])
    lines.append("];\n")
    DATA_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(dict(counts), ensure_ascii=False))
    print(f"items={len(items)} segments={sum(len(item['segments']) for item in items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
