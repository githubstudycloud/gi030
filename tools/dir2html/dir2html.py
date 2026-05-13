#!/usr/bin/env python3
"""dir2html — turn any directory into a browsable static HTML site.

Features:
  * Recursive walk of a source directory.
  * Per-file HTML page with embedded CSS (no external deps required).
  * Collapsible directory tree sidebar (pure CSS, no JavaScript).
  * Markdown rendering (uses ``markdown`` lib if installed, else a built-in
    minimal subset: headings, fenced code, inline code, bold/italic, links,
    images, blockquotes, lists, hr, paragraphs).
  * Optional Obsidian-style ``[[wiki]]`` and ``[[wiki#heading]]`` resolution
    when ``--wiki`` is passed.
  * Inline previews for images, audio, video; embed for PDF; iframe for HTML;
    syntax-friendly ``<pre><code>`` blocks for source files; download link for
    everything else.
  * Original files are copied into the output tree alongside the wrapper
    pages so links and ``<img>`` / ``<audio>`` / ``<video>`` tags resolve.

Stdlib only. Tested on Python 3.10+.
"""
from __future__ import annotations

import argparse
import html
import mimetypes
import os
import re
import shutil
import sys
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

# ---------------------------------------------------------------------------
# Optional acceleration
# ---------------------------------------------------------------------------
try:
    import markdown as _md_lib  # type: ignore

    _HAS_MD_LIB = True
except Exception:  # pragma: no cover
    _HAS_MD_LIB = False


# ---------------------------------------------------------------------------
# File-type tables
# ---------------------------------------------------------------------------
MD_EXTS = {".md", ".markdown", ".mdown", ".mkd"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico", ".avif"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".m4v"}
PDF_EXTS = {".pdf"}
HTML_EXTS = {".html", ".htm"}
TEXT_EXTS = {
    ".txt", ".log", ".csv", ".tsv", ".ini", ".cfg", ".conf", ".toml",
    ".env", ".gitignore", ".gitattributes", ".editorconfig",
}
CODE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".kt", ".kts", ".scala", ".groovy",
    ".go", ".rs", ".rb", ".php", ".pl", ".lua",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".cxx", ".m", ".mm",
    ".cs", ".fs", ".vb",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1", ".bat", ".cmd",
    ".sql", ".graphql", ".gql",
    ".json", ".jsonc", ".yaml", ".yml", ".xml", ".plist",
    ".dockerfile", ".tf", ".hcl", ".nix",
    ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte", ".astro",
}

# files we never copy / never index
DEFAULT_IGNORES = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules",
    ".venv", "venv", ".env", "dist", "build", "site", "_site",
    ".DS_Store", "Thumbs.db",
}


@dataclass
class Args:
    src: Path
    out: Path
    title: str
    wiki: bool
    open_browser: bool
    md_only_index: bool
    extra_ignores: set[str]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> Args:
    p = argparse.ArgumentParser(
        prog="dir2html",
        description="Convert a directory into a browsable static HTML site.",
    )
    p.add_argument("src", type=Path, help="Source directory")
    p.add_argument("--out", type=Path, default=Path("site"), help="Output directory (default: ./site)")
    p.add_argument("--title", default=None, help="Site title (default: source dir name)")
    p.add_argument("--wiki", action="store_true", help="Resolve Obsidian-style [[wiki]] links")
    p.add_argument("--open", dest="open_browser", action="store_true", help="Open the generated index.html in the default browser")
    p.add_argument("--md", dest="md_only_index", action="store_true",
                   help="When set, the homepage lists only Markdown files (full tree still in sidebar)")
    p.add_argument("--ignore", action="append", default=[],
                   help="Additional directory/file name to ignore (repeatable)")
    ns = p.parse_args(argv)

    src = ns.src.resolve()
    if not src.is_dir():
        p.error(f"source is not a directory: {src}")
    out = ns.out.resolve()
    return Args(
        src=src,
        out=out,
        title=ns.title or src.name,
        wiki=ns.wiki,
        open_browser=ns.open_browser,
        md_only_index=ns.md_only_index,
        extra_ignores=set(ns.ignore),
    )


# ---------------------------------------------------------------------------
# Filesystem walk
# ---------------------------------------------------------------------------
def is_ignored(name: str, extras: set[str]) -> bool:
    return name in DEFAULT_IGNORES or name in extras or name.startswith(".") and name not in {".gitignore", ".gitattributes", ".env.example", ".editorconfig"}


def walk_files(src: Path, extras: set[str]) -> list[Path]:
    out: list[Path] = []
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if not is_ignored(d, extras))
        for f in sorted(files):
            if is_ignored(f, extras):
                continue
            out.append(Path(root) / f)
    return out


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def rel_posix(path: Path, base: Path) -> str:
    return PurePosixPath(*path.relative_to(base).parts).as_posix()


def url_quote(p: str) -> str:
    return urllib.parse.quote(p, safe="/#")


def relative_url(target_rel: str, current_rel: str) -> str:
    """Build a URL from current page (relative to out_root) to target (also rel to out_root)."""
    cur_dir = PurePosixPath(current_rel).parent
    tgt = PurePosixPath(target_rel)
    rel = os.path.relpath(tgt, cur_dir).replace(os.sep, "/")
    return url_quote(rel)


def page_path_for(src_file: Path, src_root: Path) -> str:
    """Output relpath (posix) for the wrapper HTML page corresponding to src_file."""
    rel = PurePosixPath(*src_file.relative_to(src_root).parts)
    if src_file.suffix.lower() in HTML_EXTS:
        return rel.as_posix()
    return rel.with_suffix(".html").as_posix()


def asset_path_for(src_file: Path, src_root: Path) -> str:
    return PurePosixPath(*src_file.relative_to(src_root).parts).as_posix()


# ---------------------------------------------------------------------------
# Minimal Markdown renderer (fallback when `markdown` lib not installed)
# ---------------------------------------------------------------------------
_INLINE_CODE_RE = re.compile(r"`([^`\n]+?)`")
_BOLD_RE = re.compile(r"\*\*([^*\n]+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")


def _slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s)
    return s.strip("-") or "section"


def _inline(text: str) -> str:
    # protect code spans first
    spans: list[str] = []

    def _grab(m: re.Match) -> str:
        spans.append(html.escape(m.group(1)))
        return f"\x00{len(spans) - 1}\x00"

    text = _INLINE_CODE_RE.sub(_grab, text)
    text = html.escape(text)
    text = _IMAGE_RE.sub(lambda m: f'<img alt="{html.escape(m.group(1))}" src="{html.escape(m.group(2))}">', text)
    text = _LINK_RE.sub(
        lambda m: f'<a href="{html.escape(m.group(2))}"'
                  f'{f" title=\"{html.escape(m.group(3))}\"" if m.group(3) else ""}>'
                  f'{m.group(1)}</a>',
        text,
    )
    text = _AUTOLINK_RE.sub(lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _ITALIC_RE.sub(r"<em>\1</em>", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{spans[int(m.group(1))]}</code>", text)
    return text


def render_markdown_minimal(src: str) -> str:
    out: list[str] = []
    lines = src.splitlines()
    i = 0
    in_list = False
    list_kind = ""

    def close_list():
        nonlocal in_list, list_kind
        if in_list:
            out.append(f"</{list_kind}>")
            in_list = False
            list_kind = ""

    while i < len(lines):
        line = lines[i]

        # fenced code
        m_fence = re.match(r"^```(\S+)?\s*$", line)
        if m_fence:
            close_list()
            lang = m_fence.group(1) or ""
            i += 1
            buf: list[str] = []
            while i < len(lines) and not re.match(r"^```\s*$", lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(buf))}</code></pre>")
            continue

        # heading
        m_h = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m_h:
            close_list()
            level = len(m_h.group(1))
            text = m_h.group(2)
            slug = _slugify(text)
            out.append(f'<h{level} id="{slug}">{_inline(text)}</h{level}>')
            i += 1
            continue

        # hr
        if re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", line):
            close_list()
            out.append("<hr>")
            i += 1
            continue

        # blockquote (group consecutive)
        if line.startswith(">"):
            close_list()
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").lstrip())
                i += 1
            out.append("<blockquote><p>" + _inline("<br>".join(buf)) + "</p></blockquote>")
            continue

        # unordered list
        m_ul = re.match(r"^[-*+]\s+(.*)$", line)
        if m_ul:
            if not in_list or list_kind != "ul":
                close_list()
                out.append("<ul>")
                in_list, list_kind = True, "ul"
            out.append(f"<li>{_inline(m_ul.group(1))}</li>")
            i += 1
            continue

        # ordered list
        m_ol = re.match(r"^\d+\.\s+(.*)$", line)
        if m_ol:
            if not in_list or list_kind != "ol":
                close_list()
                out.append("<ol>")
                in_list, list_kind = True, "ol"
            out.append(f"<li>{_inline(m_ol.group(1))}</li>")
            i += 1
            continue

        # blank line
        if not line.strip():
            close_list()
            i += 1
            continue

        # paragraph (collect until blank)
        close_list()
        buf = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|```|>|[-*+]\s|\d+\.\s)", lines[i]):
            buf.append(lines[i])
            i += 1
        out.append("<p>" + _inline(" ".join(buf)) + "</p>")

    close_list()
    return "\n".join(out)


def render_markdown(src: str) -> str:
    if _HAS_MD_LIB:
        return _md_lib.markdown(
            src,
            extensions=["fenced_code", "tables", "toc", "sane_lists"],
            output_format="html5",
        )
    return render_markdown_minimal(src)


# ---------------------------------------------------------------------------
# Wiki link resolution
# ---------------------------------------------------------------------------
_WIKI_RE = re.compile(r"\[\[([^\[\]|]+?)(?:#([^\[\]|]+?))?(?:\|([^\[\]]+?))?\]\]")


def resolve_wiki(text: str, basename_index: dict[str, str], current_page_rel: str) -> str:
    """Convert [[Page]] / [[Page#Heading]] / [[Page|Alias]] to Markdown links.

    ``basename_index`` maps lowercase basename (without extension) -> output
    page rel path (posix). ``current_page_rel`` is the rel path of the page
    currently being rendered (used to compute relative URL).
    """

    def _sub(m: re.Match) -> str:
        target = m.group(1).strip()
        heading = (m.group(2) or "").strip()
        alias = (m.group(3) or "").strip() or target + (f"#{heading}" if heading else "")
        key = target.lower()
        if key not in basename_index:
            # leave broken link visible but non-fatal
            return f"<span class=\"broken-wiki\">[[{html.escape(target)}{('#' + html.escape(heading)) if heading else ''}]]</span>"
        target_rel = basename_index[key]
        href = relative_url(target_rel, current_page_rel)
        if heading:
            href += f"#{_slugify(heading)}"
        return f"[{alias}]({href})"

    return _WIKI_RE.sub(_sub, text)


# ---------------------------------------------------------------------------
# Page rendering
# ---------------------------------------------------------------------------
CSS = """
:root { color-scheme: light dark; --fg:#222; --bg:#fdfdfd; --muted:#666; --link:#0b67c2; --code-bg:#f3f3f3; --border:#e3e3e3; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e6e6e6; --bg:#1a1a1a; --muted:#aaa; --link:#7ab8ff; --code-bg:#2a2a2a; --border:#333; }
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg); color: var(--fg); font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, "Microsoft YaHei", sans-serif; }
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
.layout { display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }
@media (max-width: 720px) { .layout { grid-template-columns: 1fr; } aside { border-right: none; border-bottom: 1px solid var(--border); } }
aside { border-right: 1px solid var(--border); padding: 1rem; overflow-y: auto; max-height: 100vh; position: sticky; top: 0; }
aside h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin: .25rem 0 .75rem; }
aside ul { list-style: none; margin: 0; padding: 0 0 0 .75rem; }
aside li { margin: .15rem 0; }
aside details > summary { cursor: pointer; user-select: none; }
aside details > summary::-webkit-details-marker { color: var(--muted); }
main { padding: 1.5rem 2rem; min-width: 0; max-width: 920px; }
main h1, main h2, main h3 { line-height: 1.25; }
main h1 { border-bottom: 1px solid var(--border); padding-bottom: .35em; }
main img, main video, main audio, main embed, main iframe { max-width: 100%; }
pre { background: var(--code-bg); padding: 12px 14px; border-radius: 6px; overflow-x: auto; }
code { background: var(--code-bg); padding: 1px 4px; border-radius: 3px; font-family: ui-monospace, "Cascadia Code", "JetBrains Mono", Consolas, monospace; font-size: .92em; }
pre code { background: transparent; padding: 0; }
blockquote { border-left: 3px solid var(--border); margin: 0; padding: .25em 1em; color: var(--muted); }
table { border-collapse: collapse; }
th, td { border: 1px solid var(--border); padding: 6px 10px; }
.crumbs { color: var(--muted); font-size: 13px; margin-bottom: .75rem; }
.broken-wiki { color: #b00; }
.meta { color: var(--muted); font-size: 13px; margin-top: 2rem; border-top: 1px solid var(--border); padding-top: .5rem; }
.dl { display: inline-block; padding: .5em 1em; border: 1px solid var(--border); border-radius: 6px; }
"""


def page_template(title: str, sidebar: str, body: str, breadcrumbs: str, root_href: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="layout">
<aside>
  <h2><a href="{root_href}">{html.escape(title)}</a></h2>
  {sidebar}
</aside>
<main>
  <div class="crumbs">{breadcrumbs}</div>
  {body}
  <div class="meta">Generated by <code>dir2html</code>.</div>
</main>
</div>
</body>
</html>
"""


def crumbs_for(rel: str, root_href: str) -> str:
    if rel in ("", "index.html"):
        return f'<a href="{root_href}">Home</a>'
    parts = PurePosixPath(rel).parts
    out = [f'<a href="{root_href}">Home</a>']
    acc = PurePosixPath()
    for i, p in enumerate(parts):
        acc = acc / p
        is_last = i == len(parts) - 1
        if is_last:
            out.append(html.escape(p))
        else:
            # find the directory's nearest index by linking up: but we don't generate per-dir indexes,
            # so just show as text for intermediate parts.
            out.append(html.escape(p))
    return " / ".join(out)


def build_sidebar(tree: dict, root_href: str, current_rel: str) -> str:
    """Render a collapsible <details>/<ul> tree.

    ``tree`` is a nested dict: dirname -> sub-tree, plus key ``__files__`` mapping
    display name -> output relpath.
    """

    def _render(node: dict, depth: int) -> str:
        chunks: list[str] = ["<ul>"]
        # dirs first
        for name in sorted(k for k in node if k != "__files__"):
            sub = node[name]
            inner = _render(sub, depth + 1)
            opened = " open" if depth < 1 else ""
            chunks.append(f"<li><details{opened}><summary>{html.escape(name)}/</summary>{inner}</details></li>")
        for fname in sorted(node.get("__files__", {})):
            target_rel = node["__files__"][fname]
            href = relative_url(target_rel, current_rel) if current_rel else url_quote(target_rel)
            active = ' style="font-weight:600"' if target_rel == current_rel else ""
            chunks.append(f'<li><a href="{href}"{active}>{html.escape(fname)}</a></li>')
        chunks.append("</ul>")
        return "".join(chunks)

    return _render(tree, 0)


def build_tree(files: list[Path], src_root: Path) -> dict:
    root: dict = {"__files__": {}}
    for f in files:
        rel = f.relative_to(src_root)
        page_rel = page_path_for(f, src_root)
        node = root
        for part in rel.parts[:-1]:
            node = node.setdefault(part, {"__files__": {}})
        node["__files__"][rel.parts[-1]] = page_rel
    return root


# ---------------------------------------------------------------------------
# Per-file body rendering
# ---------------------------------------------------------------------------
def file_kind(p: Path) -> str:
    s = p.suffix.lower()
    if s in MD_EXTS: return "markdown"
    if s in IMAGE_EXTS: return "image"
    if s in AUDIO_EXTS: return "audio"
    if s in VIDEO_EXTS: return "video"
    if s in PDF_EXTS: return "pdf"
    if s in HTML_EXTS: return "html"
    if s in CODE_EXTS: return "code"
    if s in TEXT_EXTS: return "text"
    return "binary"


def render_body(src_file: Path, src_root: Path, page_rel: str, args: Args, basename_index: dict[str, str]) -> str:
    kind = file_kind(src_file)
    asset_rel = asset_path_for(src_file, src_root)
    asset_href = relative_url(asset_rel, page_rel)
    rel_display = rel_posix(src_file, src_root)
    title = f"<h1>{html.escape(src_file.name)}</h1>"

    if kind == "markdown":
        try:
            text = src_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = src_file.read_text(encoding="utf-8", errors="replace")
        if args.wiki:
            text = resolve_wiki(text, basename_index, page_rel)
        return render_markdown(text)

    if kind == "image":
        return f'{title}<p><img alt="{html.escape(src_file.name)}" src="{asset_href}"></p>'

    if kind == "audio":
        return f'{title}<p><audio controls src="{asset_href}"></audio></p>'

    if kind == "video":
        return f'{title}<p><video controls src="{asset_href}" style="max-width:100%"></video></p>'

    if kind == "pdf":
        return f'{title}<p><embed src="{asset_href}" type="application/pdf" style="width:100%;height:80vh"></p><p><a class="dl" href="{asset_href}">Download</a></p>'

    if kind == "html":
        # iframe original
        return f'{title}<p><iframe src="{asset_href}" style="width:100%;height:80vh;border:1px solid var(--border)"></iframe></p>'

    if kind in ("code", "text"):
        try:
            content = src_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = src_file.read_text(encoding="utf-8", errors="replace")
        lang = src_file.suffix.lstrip(".").lower()
        cls = f' class="language-{html.escape(lang)}"' if lang else ""
        return f'{title}<pre><code{cls}>{html.escape(content)}</code></pre>'

    # binary fallback
    try:
        size = src_file.stat().st_size
    except OSError:
        size = -1
    return f'{title}<p>Binary file ({size} bytes). <a class="dl" href="{asset_href}">Download</a></p>'


# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------
def render_index(args: Args, files: list[Path], tree: dict) -> str:
    items: list[str] = []
    for f in files:
        if args.md_only_index and file_kind(f) != "markdown":
            continue
        page_rel = page_path_for(f, args.src)
        items.append(f'<li><a href="{url_quote(page_rel)}">{html.escape(rel_posix(f, args.src))}</a></li>')
    body = (
        f"<h1>{html.escape(args.title)}</h1>"
        f"<p>{len(files)} files indexed from <code>{html.escape(str(args.src))}</code>.</p>"
        f"<h2>{'Markdown' if args.md_only_index else 'All files'}</h2>"
        f"<ul>{''.join(items) if items else '<li><em>No matching files.</em></li>'}</ul>"
    )
    sidebar = build_sidebar(tree, root_href="index.html", current_rel="index.html")
    return page_template(
        title=args.title,
        sidebar=sidebar,
        body=body,
        breadcrumbs='<a href="index.html">Home</a>',
        root_href="index.html",
    )


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------
def build(args: Args) -> Path:
    if args.out.exists() and args.out == args.src:
        raise SystemExit("refusing to write into the source directory")
    args.out.mkdir(parents=True, exist_ok=True)

    files = walk_files(args.src, args.extra_ignores)
    if not files:
        print("warning: no files found in source", file=sys.stderr)

    tree = build_tree(files, args.src)

    # build basename index for wiki resolution (markdown only)
    basename_index: dict[str, str] = {}
    if args.wiki:
        for f in files:
            if file_kind(f) == "markdown":
                basename_index[f.stem.lower()] = page_path_for(f, args.src)

    # copy assets and emit pages
    for f in files:
        # copy original file (asset) preserving structure
        rel = f.relative_to(args.src)
        dest_asset = args.out / rel
        dest_asset.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(f, dest_asset)
        except Exception as e:  # pragma: no cover - keep going on individual failures
            print(f"warn: copy failed for {f}: {e}", file=sys.stderr)

        # build wrapper page
        page_rel = page_path_for(f, args.src)
        body = render_body(f, args.src, page_rel, args, basename_index)
        sidebar = build_sidebar(
            tree,
            root_href=relative_url("index.html", page_rel),
            current_rel=page_rel,
        )
        page = page_template(
            title=f"{f.name} — {args.title}",
            sidebar=sidebar,
            body=body,
            breadcrumbs=crumbs_for(page_rel, relative_url("index.html", page_rel)),
            root_href=relative_url("index.html", page_rel),
        )
        out_page = args.out / page_rel
        out_page.parent.mkdir(parents=True, exist_ok=True)
        out_page.write_text(page, encoding="utf-8")

    # index
    index_path = args.out / "index.html"
    index_path.write_text(render_index(args, files, tree), encoding="utf-8")

    print(f"built: {len(files)} files -> {args.out}")
    return index_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    index = build(args)
    if args.open_browser:
        webbrowser.open(index.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
