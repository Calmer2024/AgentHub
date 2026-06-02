"""移动端 UI 快速审计：检查固定侧栏是否挤压主聊天区。"""

import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000/api"
SC = "d:/Files/AI/AgentHub/e2e/screenshots/live-orchestrator/mobile.png"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def request(path: str, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if payload else {},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


agents = request("/agents")
agent_id = agents[0]["id"]
title = f"移动端验收-{int(time.time())}"
session = request("/sessions", "POST", {
    "title": title,
    "mode": "single",
    "agentConfigId": agent_id,
})

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
    page.goto(FRONTEND, wait_until="networkidle")
    page.wait_for_timeout(1500)
    first_session = page.locator("button").filter(has_text=title).first
    if first_session.count() > 0:
        first_session.click()
        page.wait_for_timeout(1200)
    page.screenshot(path=SC, full_page=True)
    body_width = page.locator("body").bounding_box()["width"]
    main_visible = page.locator("h1").count() > 0 and page.locator("h1").first.is_visible()
    input_visible = page.locator("input[type='text']").count() > 0
    print({
        "screenshot": SC,
        "bodyWidth": body_width,
        "mainHeaderVisible": main_visible,
        "inputVisible": input_visible,
        "bodyText": (page.locator("body").inner_text() or "")[:500],
    })
    browser.close()

request(f"/sessions/{session['id']}", "DELETE")
