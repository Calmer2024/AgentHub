"""Real browser smoke for AgentHub static preview URLs.

Requires the backend to be running on http://127.0.0.1:8000.
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
import json

from playwright.sync_api import sync_playwright


API = "http://127.0.0.1:8000/api"


def request_json(path: str, payload: dict | None = None, method: str | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        f"{API}{path}",
        data=data,
        method=method or ("POST" if payload is not None else "GET"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    project = request_json("/projects", {"name": f"preview-smoke-{int(time.time())}"})
    workspace = Path(project["workspacePath"])
    page_dir = workspace / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "demo.html").write_text(
        "<!doctype html><html><body><h1 id='marker'>AgentHub Preview OK</h1></body></html>",
        encoding="utf-8",
    )

    try:
        preview = request_json(
            f"/projects/{project['id']}/preview",
            {"type": "static", "filePath": "pages/demo.html"},
        )
        preview_url = f"http://127.0.0.1:8000{preview['previewUrl']}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(preview_url, wait_until="load", timeout=10000)
            text = page.locator("#marker").inner_text(timeout=5000)
            browser.close()

        assert text == "AgentHub Preview OK"
        print(f"preview browser smoke passed: {preview_url}")
        return 0
    finally:
        try:
            request_json(f"/projects/{project['id']}?deleteFiles=true", method="DELETE")
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
