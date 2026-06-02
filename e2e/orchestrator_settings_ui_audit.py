"""设置页 Orchestrator 模型配置 UI 审计。"""

import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000/api"
SCREENSHOT = "d:/Files/AI/AgentHub/e2e/screenshots/live-orchestrator/settings-orchestrator.png"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def get_settings() -> dict:
    with urllib.request.urlopen(f"{API}/settings", timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    console_errors: list[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.goto(FRONTEND, wait_until="networkidle")
    page.get_by_text("设置", exact=True).click()
    page.wait_for_timeout(1500)

    body = page.locator("body").inner_text()
    settings = get_settings()
    failures = []
    if "Orchestrator 中枢" not in body:
        failures.append("missing orchestrator model panel")
    if settings["orchestratorProvider"] not in body:
        failures.append("missing current orchestrator provider")
    if settings["orchestratorModel"] not in body:
        failures.append("missing current orchestrator model")
    if console_errors:
        failures.append(f"console errors: {console_errors[:3]}")

    page.screenshot(path=SCREENSHOT, full_page=True)
    browser.close()

    result = {
        "screenshot": SCREENSHOT,
        "orchestratorProvider": settings["orchestratorProvider"],
        "orchestratorModel": settings["orchestratorModel"],
        "failures": failures,
        "bodyExcerpt": body[:800],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert not failures, result
