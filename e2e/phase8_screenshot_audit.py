"""Phase 8 browser screenshot audit.

Requires frontend on http://127.0.0.1:5173 and backend on
http://127.0.0.1:8000. Screenshots are written to
e2e/screenshots/phase8-release-candidate.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


FRONTEND = os.environ.get("AGENTHUB_FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")
BACKEND = os.environ.get("AGENTHUB_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots" / "phase8-release-candidate"


def assert_service_ready() -> None:
    with urllib.request.urlopen(f"{BACKEND}/openapi.json", timeout=10) as resp:
        assert resp.status == 200
    with urllib.request.urlopen(FRONTEND, timeout=10) as resp:
        assert resp.status == 200


def audit_viewport(name: str, width: int, height: int) -> list[str]:
    errors: list[str] = []
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(FRONTEND, wait_until="networkidle", timeout=30000)
        page.screenshot(path=str(SCREENSHOT_DIR / f"{name}.png"), full_page=True)
        body_text = page.locator("body").inner_text(timeout=5000).strip()
        if not body_text:
            errors.append(f"{name}: body text is empty")
        if "NaN" in body_text or "undefined" in body_text:
            errors.append(f"{name}: visible placeholder text detected")
        browser.close()
    return errors


def main() -> int:
    assert_service_ready()
    errors = [
        *audit_viewport("desktop-1440x900", 1440, 900),
        *audit_viewport("mobile-390x844", 390, 844),
    ]
    if errors:
        print("phase8 screenshot audit failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"phase8 screenshot audit passed: {SCREENSHOT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
