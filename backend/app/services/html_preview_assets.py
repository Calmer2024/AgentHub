"""HTML 预览资源内联工具。"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlsplit


MAX_INLINE_ASSET_BYTES = 1024 * 1024

_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*(['\"])(?P<src>[^'\"]+)\1[^>]*>\s*</script>", re.IGNORECASE)
_ATTR_RE = re.compile(r"\b(?P<name>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(['\"])(?P<value>.*?)\2", re.DOTALL)


def inline_local_html_assets(content: str, resolve_asset: Callable[[str], Path]) -> str:
    """把同工作区内的 CSS/JS 内联到 HTML，保证沙箱 iframe 可独立渲染。"""

    content = _LINK_TAG_RE.sub(lambda match: _replace_stylesheet(match.group(0), resolve_asset), content)
    return _SCRIPT_TAG_RE.sub(lambda match: _replace_script(match, resolve_asset), content)


def _replace_stylesheet(tag: str, resolve_asset: Callable[[str], Path]) -> str:
    attrs = _tag_attrs(tag)
    rel = attrs.get("rel", "").lower()
    href = attrs.get("href", "")
    if "stylesheet" not in rel or not _is_local_asset_url(href):
        return tag
    asset = _read_inline_asset(href, resolve_asset)
    if asset is None:
        return tag
    safe_href = escape(_display_url(href), quote=True)
    body = asset.replace("</style", "<\\/style")
    media = attrs.get("media")
    media_attr = f' media="{escape(media, quote=True)}"' if media else ""
    return f'<style data-agenthub-inline-asset="{safe_href}"{media_attr}>\n{body}\n</style>'


def _replace_script(match: re.Match[str], resolve_asset: Callable[[str], Path]) -> str:
    tag = match.group(0)
    src = match.group("src")
    if not _is_local_asset_url(src):
        return tag
    asset = _read_inline_asset(src, resolve_asset)
    if asset is None:
        return tag
    safe_src = escape(_display_url(src), quote=True)
    body = asset.replace("</script", "<\\/script")
    return f'<script {_script_inline_attrs(tag, safe_src)}>\n{body}\n</script>'


def _tag_attrs(tag: str) -> dict[str, str]:
    return {match.group("name").lower(): match.group("value") for match in _ATTR_RE.finditer(tag)}


def _script_inline_attrs(tag: str, safe_src: str) -> str:
    attrs = _tag_attrs(tag)
    parts = [f'data-agenthub-inline-asset="{safe_src}"']
    for name in ("type", "crossorigin", "referrerpolicy"):
        value = attrs.get(name)
        if value:
            parts.append(f'{name}="{escape(value, quote=True)}"')
    for name in ("defer", "async", "nomodule"):
        if re.search(rf"\b{name}\b", tag, flags=re.IGNORECASE):
            parts.append(name)
    return " ".join(parts)


def _is_local_asset_url(url: str) -> bool:
    value = url.strip()
    if not value:
        return False
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return False
    path = unquote(parsed.path).replace("\\", "/").strip()
    if not path or path.startswith(("/", "~", "#")):
        return False
    return not any(part == ".." for part in path.split("/"))


def _display_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    return unquote(parsed.path)


def _read_inline_asset(url: str, resolve_asset: Callable[[str], Path]) -> str | None:
    try:
        asset = resolve_asset(_display_url(url))
    except Exception:
        return None
    if not asset.exists() or not asset.is_file():
        return None
    if asset.stat().st_size > MAX_INLINE_ASSET_BYTES:
        return None
    return asset.read_text(encoding="utf-8", errors="replace")
