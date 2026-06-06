"""Detailed test - send messages, check group chat, verify chain config."""
from playwright.sync_api import sync_playwright
import json

BASE = "http://127.0.0.1:5173"

def log(msg):
    print(msg.encode('ascii', errors='replace').decode('ascii'))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    console_errs = []
    page.on("console", lambda m: console_errs.append(m.text) if m.type == "error" else None)

    page.goto(BASE, timeout=15000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    # === SINGLE CHAT: Send message ===
    log("=== SINGLE CHAT TEST ===")

    # Click new chat
    page.locator("button:has-text('新建对话')").first.click()
    page.wait_for_timeout(1000)

    # Find input - it's input[type="text"]
    inp = page.locator('input[type="text"]')
    if inp.count() > 0:
        log(f"Input placeholder: {inp.first.get_attribute('placeholder')}")
        log(f"Input disabled: {inp.first.is_disabled()}")

        # Type message
        inp.first.fill("Hello, please introduce yourself briefly")
        page.wait_for_timeout(200)

        # Find and click send button
        send = page.locator("button:has-text('发送')")
        log(f"Send button count: {send.count()}")

        if send.count() > 0:
            send.first.click()
            # Wait for streaming
            page.wait_for_timeout(5000)

            # Check what's in the page
            page.screenshot(path="/tmp/chat_after_send.png", full_page=True)

            # Check for message content
            msg_area = page.locator(".flex-1.overflow-y-auto")
            if msg_area.count() > 0:
                text = msg_area.first.text_content() or ""
                log(f"Chat area text length: {len(text)}")
                log(f"Chat area preview: {text[:200]}")
            else:
                log("Chat area not found")

            # Check for typing indicator
            has_typing = "typing" in (page.content() or "").lower()
            log(f"Typing indicator in DOM: {has_typing}")

    # === GROUP CHAT: Test chain config visibility ===
    log("\n=== GROUP CHAT: CHAIN CONFIG ===")

    # Need to go back to session list first
    # Click on a session item or tab to refocus
    page.locator("button:has-text('新建群聊')").first.click()
    page.wait_for_timeout(1500)

    # Dump the group creator HTML to debug chain config
    html = page.content()
    has_chain = "链式" in html
    has_pipeline = "pipeline" in html.lower()
    has_producer = "producer" in html.lower() or "产出" in html

    log(f"Chain keywords in HTML: chain={has_chain}, pipeline={has_pipeline}, producer={has_producer}")

    # Check if the checkboxes section has the chain section after it
    # The chain config should appear below the agent list
    page.screenshot(path="/tmp/group_creator.png", full_page=True)

    # Select agents first
    checkboxes = page.locator("input[type='checkbox']")
    for i in range(min(checkboxes.count(), 3)):
        checkboxes.nth(i).check()
        page.wait_for_timeout(100)

    page.wait_for_timeout(500)
    page.screenshot(path="/tmp/group_creator_after_select.png", full_page=True)

    # Check again after selecting agents
    html2 = page.content()
    has_chain2 = "链式" in html2
    log(f"Chain config visible after selecting 3 agents: {has_chain2}")

    # Close group creator
    cancel = page.locator("button:has-text('取消')")
    if cancel.count() > 0:
        cancel.first.click()
        page.wait_for_timeout(300)

    # === API TEST: Verify backend responses ===
    log("\n=== API INTEGRATION CHECK ===")
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8000/api/agents")
        agents = json.loads(resp.read())
        log(f"API /api/agents: {len(agents)} agents")
        for a in agents[:3]:
            log(f"  - {a.get('name', '?')} ({a.get('cliTool', '?')}/{a.get('executable', '?')})")
    except Exception as e:
        log(f"API error: {e}")

    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8000/api/sessions")
        sessions = json.loads(resp.read())
        log(f"API /api/sessions: {len(sessions)} sessions")
        for s in sessions[:3]:
            log(f"  - {s.get('title', '?')} mode={s.get('mode', '?')}")
    except Exception as e:
        log(f"API sessions error: {e}")

    # === JS CONSOLE ERRORS ===
    log(f"\n=== CONSOLE ERRORS: {len(console_errs)} ===")
    for e in console_errs[:10]:
        log(f"  {e[:200]}")

    log("\n=== DONE ===")
    browser.close()
