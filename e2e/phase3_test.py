"""Phase 3 Module 2 Browser Test - Step by step with screenshots."""
from playwright.sync_api import sync_playwright
import os, sys
os.environ["PYTHONIOENCODING"] = "utf-8"

BASE = "http://127.0.0.1:5173"
OUT = "/tmp"

def log(msg):
    # Use ASCII-safe printing
    safe = msg.encode('ascii', errors='replace').decode('ascii')
    print(safe)

def run():
    issues = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        page.goto(BASE, timeout=15000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # === TEST 1: Initial Load ===
        log("=== 1. INITIAL LOAD ===")
        page.screenshot(path=f"{OUT}/01_initial.png", full_page=True)

        has_session_tab = page.locator("button:has-text('会话')").count() > 0 or page.locator("button").filter(has_text="会话").count() > 0
        buttons = page.locator("button").all_text_contents()
        log(f"Buttons: {buttons}")

        if console_errors:
            log(f"CONSOLE ERRORS: {console_errors}")
            issues.append("P0: JavaScript errors on initial load")

        # === TEST 2: Click 'New Chat' ===
        log("=== 2. NEW CHAT ===")
        new_chat = page.locator("button:has-text('新建对话')")
        if new_chat.count() > 0:
            new_chat.first.click()
            page.wait_for_timeout(1500)
            page.screenshot(path=f"{OUT}/02_new_chat.png", full_page=True)

            # Check if ChatInput appears
            textboxes = page.locator('[role="textbox"]').count()
            text_inputs = page.locator('input[type="text"]').count()
            textareas = page.locator('textarea').count()
            log(f"Text inputs: role=textbox:{textboxes}, input:{text_inputs}, textarea:{textareas}")

            if textboxes == 0 and text_inputs == 0:
                issues.append("P0: ChatInput not visible after creating new chat - users cannot send messages")
                # Try to find what's in the main area
                main_html = page.locator(".flex-1").first.inner_html() if page.locator(".flex-1").count() > 0 else "N/A"
                log(f"Main area HTML (first 500): {main_html[:500]}")
        else:
            issues.append("P0: 'New Chat' button not found")

        # === TEST 3: Agent Panel ===
        log("=== 3. AGENTS ===")
        agent_tab = page.locator("button:has-text('Agent')")
        if agent_tab.count() > 0:
            agent_tab.first.click()
            page.wait_for_timeout(1000)
            page.screenshot(path=f"{OUT}/03_agents.png", full_page=True)
            body = page.content()
            has_default = "默认助手" in body or "default" in body.lower()
            log(f"Default agent visible: {has_default}")
            if not has_default:
                issues.append("P1: Default agent not visible in Agent panel")
        else:
            issues.append("P1: Agent tab not found")

        # === TEST 4: Settings ===
        log("=== 4. SETTINGS ===")
        settings_tab = page.locator("button:has-text('设置')")
        if settings_tab.count() > 0:
            settings_tab.first.click()
            page.wait_for_timeout(500)
            page.screenshot(path=f"{OUT}/04_settings.png", full_page=True)
        else:
            issues.append("P2: Settings tab not found")

        # === TEST 5: Session → Chat flow ===
        log("=== 5. CHAT FLOW ===")
        session_tab = page.locator("button:has-text('会话')")
        if session_tab.count() > 0:
            session_tab.first.click()
            page.wait_for_timeout(300)

        # Click on an existing session if any
        session_items = page.locator("button").filter(has_text="新对话")
        if session_items.count() > 0:
            session_items.first.click()
            page.wait_for_timeout(1500)
            page.screenshot(path=f"{OUT}/05_session_selected.png", full_page=True)

            # Look for chat input
            textbox = page.locator('[role="textbox"]')
            text_input = page.locator('input[type="text"]')
            if textbox.count() > 0:
                textbox.first.fill("你好")
                page.wait_for_timeout(200)
                log("Textbox filled OK")

                # Find send button
                send = page.locator("button:has-text('发送')")
                if send.count() > 0:
                    send.first.click()
                    page.wait_for_timeout(3000)
                    page.screenshot(path=f"{OUT}/06_after_send.png", full_page=True)

                    # Check for response
                    content = page.content()
                    has_response = "Hello" in content
                    log(f"Got response: {has_response}")
                    if not has_response:
                        issues.append("P1: No AI response after sending message")
                else:
                    issues.append("P0: Send button not found")
                    log(f"Available buttons: {page.locator('button').all_text_contents()}")
            elif text_input.count() > 0:
                log("Found plain text input instead of role=textbox")
            else:
                issues.append("P0: No text input found after selecting session")
                # Dump the HTML to debug
                main_content = page.content()
                with open(f"{OUT}/debug_main.html", "w", encoding="utf-8") as f:
                    f.write(main_content)
                log(f"Saved debug HTML to {OUT}/debug_main.html")
        else:
            log("No session items found")

        # === TEST 6: Group Chat ===
        log("=== 6. GROUP CHAT ===")
        new_group = page.locator("button:has-text('新建群聊')")
        if new_group.count() > 0:
            new_group.first.click()
            page.wait_for_timeout(1500)
            page.screenshot(path=f"{OUT}/07_group_creator.png", full_page=True)

            # Check for chain config
            has_chain = "链式" in page.content()
            log(f"Chain config visible: {has_chain}")
            if not has_chain:
                issues.append("P2: Chain collaboration config not visible in GroupChatCreator")

            # Select agents
            checkboxes = page.locator("input[type='checkbox']")
            cb_count = checkboxes.count()
            log(f"Agent checkboxes: {cb_count}")
            selected = 0
            for i in range(min(cb_count, 3)):
                cb = checkboxes.nth(i)
                if cb.is_visible():
                    cb.check()
                    selected += 1
                    page.wait_for_timeout(100)
            log(f"Selected {selected} agents")

            # Try to create
            create_btn = page.locator("button:has-text('创建')").filter(has_not_text="取消")
            if create_btn.count() > 0:
                enabled = create_btn.first.is_enabled()
                log(f"Create button enabled: {enabled}")
                if enabled:
                    create_btn.first.click()
                    page.wait_for_timeout(1500)
                    page.screenshot(path=f"{OUT}/08_group_created.png", full_page=True)

                    # Send message in group
                    textbox = page.locator('[role="textbox"]')
                    if textbox.count() > 0:
                        textbox.first.fill("帮我写一个登录页面")
                        page.wait_for_timeout(100)
                        send = page.locator("button:has-text('发送')")
                        if send.count() > 0:
                            send.first.click()
                            page.wait_for_timeout(5000)
                            page.screenshot(path=f"{OUT}/09_group_chat.png", full_page=True)

                            # Check for Orchestrator route banner
                            has_route = "Orchestrator" in page.content() or "路由" in page.content()
                            log(f"Orchestrator banner visible: {has_route}")
                            if not has_route:
                                issues.append("P1: Orchestrator route banner not shown in group chat")
                else:
                    issues.append(f"P1: Create group button disabled with {selected} agents")
            else:
                issues.append("P1: Create button not found in group creator")
                # Cancel
                cancel = page.locator("button:has-text('取消')")
                if cancel.count() > 0:
                    cancel.first.click()
        else:
            issues.append("P1: 'New Group Chat' button not found")

        # === SUMMARY ===
        log("=" * 60)
        log(f"ISSUES FOUND: {len(issues)}")
        for i, iss in enumerate(issues):
            log(f"  {i+1}. {iss}")

        if not issues:
            log("ALL CHECKS PASSED")

        page.screenshot(path=f"{OUT}/10_final.png", full_page=True)
        browser.close()

if __name__ == "__main__":
    run()
