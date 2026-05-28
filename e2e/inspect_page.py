"""Inspect the actual page structure of AgentHub."""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5173"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    errors = []
    page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)

    page.goto(BASE, timeout=15000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # Screenshot
    page.screenshot(path="/tmp/agenthub_inspect.png", full_page=True)
    print("Screenshot saved to /tmp/agenthub_inspect.png")

    # Get all buttons
    buttons = page.locator("button").all()
    print(f"\n=== Buttons ({len(buttons)}) ===")
    for b in buttons:
        try:
            print(f"  '{b.text_content()}' | disabled={b.is_disabled()} | visible={b.is_visible()}")
        except:
            pass

    # Get all input/textarea
    inputs = page.locator("input, textarea").all()
    print(f"\n=== Inputs ({len(inputs)}) ===")
    for inp in inputs:
        try:
            print(f"  type={inp.get_attribute('type')} | placeholder={inp.get_attribute('placeholder')} | role={inp.get_attribute('role')}")
        except:
            pass

    # Get page structure
    print(f"\n=== Page Title ===")
    print(f"  {page.title()}")

    # Get all text content in key areas
    print(f"\n=== Body Excerpt ===")
    body = page.text_content("body") or ""
    print(f"  {body[:1000]}")

    # Check for key elements
    print(f"\n=== Key Elements ===")
    for sel in ["text=会话", "text=Agent", "text=设置", "text=新建对话", "text=新建群聊",
                "button", "[role='textbox']", "[class*='sidebar']", "[class*='chat']"]:
        count = page.locator(sel).count()
        if count > 0:
            print(f"  '{sel}': {count} found")

    # Console errors
    print(f"\n=== Console Errors ({len(errors)}) ===")
    for e in errors[:10]:
        print(f"  {e[:200]}")

    browser.close()
