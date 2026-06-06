"""Helpers for turning visible CLI text chunks into readable UI stream pieces."""

from __future__ import annotations

import re


def iter_stream_pieces(text: str, *, target_size: int = 48, max_size: int = 96):
    """Split a CLI text chunk into short, natural pieces for SSE rendering."""
    if not text:
        return

    buffer = ""
    for part in re.split(r"(\s+)", text):
        if not part:
            continue
        if not part.isspace() and len(part) > max_size:
            if buffer:
                yield buffer
                buffer = ""
            for index in range(0, len(part), max_size):
                yield part[index:index + max_size]
            continue
        buffer += part
        if _ready(buffer, target_size, max_size):
            yield buffer
            buffer = ""
    if buffer:
        yield buffer


def _ready(buffer: str, target_size: int, max_size: int) -> bool:
    if len(buffer) >= max_size:
        return True
    if len(buffer) < target_size:
        return False
    return bool(re.search(r"[\n。！？；.!?;]\s*$", buffer))
