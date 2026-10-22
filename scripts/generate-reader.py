#!/usr/bin/env python3
"""Generate a zero-JavaScript fallback reader for the trial content.

The Expo export is the primary application.  This reader is deliberately
plain HTML so that a phone can still browse the imported WeChat content when
the application bundle is blocked, times out, or cannot hydrate.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import re
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT / "docs" / "content-import-manifest.json"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def page(title: str, body: str, *, description: str = "祷告地球同工试用版轻量阅读") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#173f37">
  <meta name="description" content="{esc(description)}">
  <title>{esc(title)} · 祷告地球</title>
  <style>
    :root {{ color-scheme: light; --ink:#173f37; --soft:#526963; --cream:#f7f5f0; --line:#dce6e0; --mint:#e6f1eb; --white:#fff; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--cream); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; line-height:1.55; }}
    a {{ color:inherit; }}
    .shell {{ max-width:860px; margin:0 auto; padding:18px 15px 46px; }}
    header {{ padding:7px 0 16px; }}
    .brand {{ font-size:20px; font-weight:800; letter-spacing:.02em; }}
    .sub {{ color:var(--soft); font-size:13px; margin-top:2px; }}
    nav {{ display:flex; gap:8px; overflow:auto; padding:4px 0 14px; }}
    nav a, .back {{ display:inline-flex; align-items:center; min-height:39px; padding:0 14px; border:1px solid var(--line); border-radius:21px; background:var(--white); text-decoration:none; white-space:nowrap; font-size:13px; }}
    nav a.active {{ background:var(--ink); border-color:var(--ink); color:#fff; }}
    .notice {{ background:var(--mint); border-radius:14px; padding:12px 14px; color:#285d4f; font-size:13px; margin:5px 0 16px; }}
    h1 {{ font-size:22px; line-height:1.3; margin:12px 0 5px; }}
    h2 {{ font-size:16px; margin:22px 0 9px; }}
    .muted {{ color:var(--soft); font-size:13px; }}
    .list {{ display:grid; gap:10px; }}
    .card {{ display:block; background:var(--white); border:1px solid var(--line); border-radius:15px; padding:14px 15px; text-decoration:none; }}
    .card:active {{ background:var(--mint); }}
    .card-title {{ font-size:16px; font-weight:750; }}
    .card-meta {{ color:var(--soft); font-size:12px; margin-top:4px; }}
    .card-copy {{ color:#526963; font-size:13px; margin-top:7px; }}
    .back {{ margin:3px 0 12px; }}
    .notice + .list {{ margin-top:0; }}
    .article {{ background:var(--white); border-radius:15px; overflow:hidden; border:1px solid var(--line); }}
    .article img {{ display:block; width:100%; height:auto; background:#f0f3ef; }}
    .source {{ color:#70827d; font-size:11px; padding:11px 13px; word-break:break-all; }}
    footer {{ color:#7a8b86; font-size:11px; padding-top:18px; text-align:center; }}
    @media (min-width:700px) {{ .list {{ grid-template-columns:1fr 1fr; }} .article {{ max-width:620px; margin:0 auto; }} }}
  </style>
</head>
<body><main class="shell">{body}</main></body>
</html>
"""


def nav(active: str) -> str:
    links = [("全部", "index.html"), ("晨修", "morning.html"), ("宣教动态与见证", "mission.html")]
    return "<nav>" + "".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{esc(key)}</a>'
        for key, href in links
    ) + "</nav>"


def resolve_segment(dist: Path, channel: str, file_name: str) -> Path:
    folder = "morning" if channel == "晨修" else "mission"
    # Expo appends a content hash before the extension (foo.abc123.jpg),
    # while the manifest stores the source segment name (foo.jpg).
    stem = Path(file_name).stem
    roots = [dist / "assets" / "assets" / "content" / folder, dist / "assets" / "content" / folder]
    matches = sorted(path for root in roots if root.exists() for path in root.glob(stem + ".*"))
    if not matches:
        raise FileNotFoundError(f"exported image not found: {folder}/{file_name}")
    return matches[0]


def card(item: dict[str, object]) -> str:
    item_id = str(item["id"])
    title = str(item.get("title") or f'{item.get("channel", "内容")} · {item.get("date", "")}')
    excerpt = str(item.get("excerpt") or f'点击打开完整图片内容（共 {len(item.get("segments", []))} 段）')
    return f'''<a class="card" href="{esc(item_id)}.html">
  <div class="card-title">{esc(title)}</div>
  <div class="card-meta">{esc(item["date"])} · {esc(item["channel"])}</div>
  <div class="card-copy">{esc(excerpt)}</div>
</a>'''


def render_feed_reader(path: str, items: list[dict[str, object]], *, include_admin: bool = True) -> str | None:
    """Render a live, zero-JavaScript reader route without writing any files.

    ``items`` uses the public GET /api/content schema. Each segment has a
    root-relative ``uri`` plus ``width`` and ``height``. Archive URIs point to
    Expo's hashed /assets/... files; uploads use their own root-relative URI.
    Return None for unknown routes so the server can send a genuine 404.
    """
    name = path.split("?", 1)[0]
    if name in ("/reader", "/reader/", "reader", "reader/"):
        name = "index.html"
    elif name.startswith("/reader/"):
        name = name[len("/reader/"):]
    elif name.startswith("reader/"):
        name = name[len("reader/"):]
    if "/" in name or "\\" in name:
        return None
    ordered = [item for item in items if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", str(item.get("id", "")))]
    ordered.sort(key=lambda item: (str(item.get("date", "")), str(item.get("id", ""))), reverse=True)
    header = '<header><div class="brand">祷告地球</div><div class="sub">同工内容 · 轻量阅读版</div></header>'
    footer = '<footer><a href="index.html">返回全部内容</a> · <a href="/">返回主应用</a>'
    if include_admin:
        footer += ' · <a href="/admin">管理员入口</a>'
    footer += '</footer>'
    intro = '<div class="notice">按日期阅读同工发布的晨修与宣教图片。新发布的内容会显示在最前面。</div>'
    list_channels = {"index.html": "全部", "morning.html": "晨修", "mission.html": "宣教动态与见证"}
    if name in list_channels:
        active = list_channels[name]
        visible = ordered if active == "全部" else [item for item in ordered if item.get("channel") == active]
        title = "晨修与宣教" if active == "全部" else active
        counts = f'共 {len(visible)} 条'
        if active == "全部":
            morning_count = sum(1 for item in ordered if item.get("channel") == "晨修")
            mission_count = sum(1 for item in ordered if item.get("channel") == "宣教动态与见证")
            counts += f' · 晨修 {morning_count} 条 · 宣教动态与见证 {mission_count} 条'
        body = (header + nav(active) + intro + f'<h1>{esc(title)}</h1><div class="muted">{esc(counts)}</div>'
                + f'<div class="list">{"".join(card(item) for item in visible)}</div>' + footer)
        return page(title, body)
    item = next((item for item in ordered if f'{item["id"]}.html' == name), None)
    if item is None:
        return None
    channel = str(item["channel"])
    date = str(item["date"])
    title = str(item.get("title") or f"{channel} · {date}")
    image_tags: list[str] = []
    for segment in item.get("segments", []):
        if not isinstance(segment, dict):
            continue
        src = str(segment.get("uri", ""))
        if not src.startswith("/") or src.startswith("//"):
            continue
        image_tags.append(
            f'<img src="{esc(src)}" width="{esc(segment["width"])}" height="{esc(segment["height"])}" '
            f'loading="lazy" decoding="async" alt="{esc(title)}">'
        )
    excerpt = str(item.get("excerpt") or "同工发布的完整图片内容，按原顺序连续显示。")
    body = (header
            + f'<a class="back" href="{"morning.html" if channel == "晨修" else "mission.html"}">← 返回{esc(channel)}</a>'
            + f'<h1>{esc(title)}</h1><div class="muted">{esc(date)}</div>'
            + f'<div class="notice">{esc(excerpt)}</div>'
            + f'<article class="article">{"".join(image_tags)}<div class="source">图片按原顺序连续显示，共 {len(image_tags)} 段。</div></article>'
            + footer)
    return page(title, body)


def build_seed(dist: Path, manifest: dict[str, object]) -> dict[str, object]:
    """Resolve the archive's source filenames to deployed, hashed image URIs."""
    items: list[dict[str, object]] = []
    for source in manifest.get("items", []):
        if not isinstance(source, dict):
            continue
        item = dict(source)
        channel = str(item["channel"])
        segments = []
        for segment in item.get("segments", []):
            exported = resolve_segment(dist, channel, str(segment["fileName"]))
            segments.append({"uri": "/" + exported.relative_to(dist).as_posix(), "width": segment["width"], "height": segment["height"]})
        if not segments:
            raise ValueError(f'No images for {item["id"]}')
        item["segments"] = segments
        item["image"] = {"uri": segments[0]["uri"]}
        item["title"] = f'{channel} · {item["date"]}'
        item["excerpt"] = "微信群图片原文，点击查看完整内容。"
        item["searchText"] = f'{channel} {item["date"]} {item.get("sourceFile", "")}'
        items.append(item)
    return {"version": 1, "items": items}


def write_reader(dist: Path, manifest: dict[str, object]) -> int:
    seed = build_seed(dist, manifest)
    (dist / "content-seed.json").write_text(json.dumps(seed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    root = dist / "reader"
    if root.resolve().parent != dist.resolve():
        raise ValueError("Reader directory must remain within the export directory")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    items = seed["items"]
    names = ["index.html", "morning.html", "mission.html"] + [f'{item["id"]}.html' for item in items]
    for name in names:
        rendered = render_feed_reader(name, items)
        if rendered is None:
            raise ValueError(f"Reader route could not be rendered: {name}")
        (root / name).write_text(rendered, encoding="utf-8")
    return len(items)


def inject_watchdog(dist: Path) -> int:
    """Add a tiny ES5 fallback prompt without touching React's root tree."""
    noscript = r'''<noscript><div style="position:fixed;z-index:2147483647;left:12px;right:12px;bottom:16px;padding:14px 15px;border-radius:15px;background:#173f37;color:#fff;box-shadow:0 8px 30px rgba(0,0,0,.22);font:14px/1.55 -apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif"><div style="font-weight:700">可以直接阅读同工内容</div><a href="/reader/index.html" style="display:inline-block;margin-top:10px;padding:8px 12px;border-radius:18px;background:#e6f1eb;color:#173f37;text-decoration:none;font-weight:700">打开轻量阅读版</a></div></noscript>'''
    script = r'''<script>
(function(){
  var shown=false, timer=0, poll=0;
  function root(){return document.getElementById('root');}
  function ready(){var r=root(); return r && r.textContent && r.textContent.indexOf('正在准备祷告空间')===-1;}
  function remove(){var n=document.getElementById('prayer-bootstrap-fallback'); if(n&&n.parentNode)n.parentNode.removeChild(n);shown=false;}
  function show(){if(shown||ready())return; shown=true;
    var n=document.createElement('div'); n.id='prayer-bootstrap-fallback';
    n.innerHTML='<div style="position:fixed;z-index:2147483647;left:12px;right:12px;bottom:16px;padding:14px 15px;border-radius:15px;background:#173f37;color:#fff;box-shadow:0 8px 30px rgba(0,0,0,.22);font:14px/1.55 -apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif"><div style="font-weight:700">页面加载时间较长</div><div style="opacity:.9;margin-top:3px">可以先打开轻量阅读版浏览晨修和宣教内容。</div><a href="/reader/index.html" style="display:inline-block;margin-top:10px;padding:8px 12px;border-radius:18px;background:#e6f1eb;color:#173f37;text-decoration:none;font-weight:700">打开轻量阅读版</a><button type="button" style="float:right;margin-top:10px;padding:7px 10px;border:1px solid rgba(255,255,255,.5);border-radius:16px;background:transparent;color:#fff" onclick="this.parentNode.parentNode.remove()">关闭</button></div>';
    document.body.appendChild(n);
  }
  function tick(){if(ready())remove();}
  setTimeout(show,8000); poll=setInterval(tick,500);
  window.addEventListener('error',function(e){if(e&&e.target&&e.target.tagName==='SCRIPT')setTimeout(show,300);},true);
  window.addEventListener('unhandledrejection',function(){setTimeout(show,300);});
  window.addEventListener('load',function(){setTimeout(tick,100);});
})();
</script>'''
    count = 0
    for file in dist.rglob("*.html"):
        if str(file.parent).replace("\\", "/").endswith("/reader"):
            continue
        text = file.read_text(encoding="utf-8")
        if "prayer-bootstrap-fallback" in text:
            continue
        marker = "</head>"
        if marker not in text:
            continue
        text = text.replace(marker, script + marker, 1)
        text = text.replace("</body>", noscript + "</body>", 1)
        file.write_text(text, encoding="utf-8")
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", type=Path, default=PROJECT / "dist")
    args = parser.parse_args()
    dist = args.dist.resolve()
    if not (dist / "index.html").exists():
        raise SystemExit(f"Expo export not found: {dist / 'index.html'}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    count = write_reader(dist, manifest)
    pages = inject_watchdog(dist)
    print(f"Generated zero-JavaScript reader for {count} items; injected watchdog into {pages} Expo pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
