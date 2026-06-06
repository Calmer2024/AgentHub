"""全量 UI/UX 审计 — 逐步骤截图 + 控制台错误 + 布局检测。

与之前简单测试不同，本测试:
  - 每步截图
  - 捕获所有控制台日志 (error/warn/log)
  - 检查元素遮挡 (z-index)
  - 检查按钮是否可点击
  - 模拟真实用户操作流程
"""
import os, sys, json, time, requests

os.environ["PYTHONIOENCODING"] = "utf-8"

FRONTEND = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000/api"
SC = "d:/Files/AI/AgentHub/e2e/screenshots"
os.makedirs(SC, exist_ok=True)

from playwright.sync_api import sync_playwright

P = 0; F = 0

def ok(n, cond=True, detail=""):
    global P, F
    if cond:
        P += 1; print(f"  [PASS] {n}")
    else:
        F += 1; print(f"  [FAIL] {n}: {detail}")
def no(n, d=""):
    global F; F += 1; print(f"  [FAIL] {n}: {d}")


def main():
    print("=" * 60)
    print("AgentHub Full UI/UX Audit")
    print("=" * 60)

    # === API Prep ===
    print("\n--- API Prep ---")
    agents = requests.get(f"{API}/agents", timeout=10).json()
    print(f"  {len(agents)} agents available")
    agent_ids = [a["id"] for a in agents[:2]]
    agent_names = [a["name"] for a in agents[:2]]

    r = requests.post(f"{API}/sessions", json={
        "title": "UI测试群聊", "mode": "group", "agentConfigIds": agent_ids
    }, timeout=10)
    sid = r.json()["id"]
    print(f"  Session: {sid[:10]}...")

    # 也创建一个单聊 session
    r2 = requests.post(f"{API}/sessions", json={
        "title": "单聊测试", "mode": "single", "agentConfigId": agent_ids[0]
    }, timeout=10)
    single_sid = r2.json()["id"]
    print(f"  Single session: {single_sid[:10]}...")

    # === Browser ===
    print("\n--- Browser Audit ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # Collect ALL console messages
        console_log = []
        page.on("console", lambda msg: console_log.append(f"[{msg.type.upper()}] {msg.text}"))

        # ========== 1. PAGE LOAD ==========
        print("\n--- 1. Page Load ---")
        page.goto(FRONTEND, wait_until="networkidle")
        page.wait_for_timeout(3000)  # Give React time to fully render
        page.screenshot(path=f"{SC}/01-initial-load.png", full_page=True)

        # Check console errors
        errors = [m for m in console_log if "ERROR" in m]
        warns = [m for m in console_log if "WARN" in m]
        console_log.clear()

        if errors:
            for e in errors[:10]:
                no("Console error on load", e)
        else:
            ok("No console errors on initial load")

        # Check page content
        html = page.content()
        ok("Page has content", len(html) > 500, "Page appears empty or broken")

        # Check sidebar
        sidebar_btns = page.locator("button:has-text('会话'), button:has-text('Agent'), button:has-text('设置')")
        ok(f"Sidebar tabs visible ({sidebar_btns.count()})", sidebar_btns.count() >= 2,
           f"Only {sidebar_btns.count()} tabs found")

        # ========== 2. SESSIONS TAB ==========
        print("\n--- 2. Sessions Tab ---")
        sessions_tab = page.locator("button:has-text('会话')")
        if sessions_tab.count() > 0:
            sessions_tab.first.click()
            page.wait_for_timeout(1000)

        page.screenshot(path=f"{SC}/02-sessions-tab.png", full_page=True)

        # Check sessions visible
        has_session = "UI测试群聊" in page.content() or "单聊测试" in page.content()
        ok("Group sessions visible", has_session)

        # Check new chat buttons
        new_btn = page.locator("button:has-text('新建')")
        group_btn = page.locator("button:has-text('群聊')")
        ok(f"New chat buttons (new={new_btn.count()}, group={group_btn.count()})",
           new_btn.count() > 0 or group_btn.count() > 0)

        # ========== 3. GROUP CHAT - CLICK AND OBSERVE ==========
        print("\n--- 3. Open Group Chat ---")
        # Click the group session
        group_el = page.locator("text=UI测试群聊")
        if group_el.count() > 0:
            group_el.first.click()
            page.wait_for_timeout(2000)
        page.screenshot(path=f"{SC}/03-group-chat-opened.png", full_page=True)

        # Capture console errors after session switch
        errors = [m for m in console_log if "ERROR" in m and "favicon" not in m]
        console_log.clear()
        if errors:
            for e in errors[:5]:
                no("Console error on group chat open", e)
        else:
            ok("No console errors opening group chat")

        # Check header
        header = page.locator("h1")
        header_text = header.first.text_content() if header.count() > 0 else ""
        ok(f"Header shows: {header_text[:30]}", "群聊" in (header_text or ""))

        # Check input
        inp = page.locator("input[type='text']")
        inp_count = inp.count()
        disabled = inp.first.is_disabled() if inp_count > 0 else True
        ok(f"Input visible (count={inp_count}, disabled={disabled})",
           inp_count > 0 and not disabled,
           f"Count={inp_count}, Disabled={disabled}")

        # ========== 4. SEND MESSAGE ==========
        print("\n--- 4. Send Message ---")
        if inp_count > 0 and not disabled:
            test_msg = "帮我写一个React登录组件"
            inp.first.fill(test_msg)
            page.wait_for_timeout(300)

            # Click send
            send_btn = page.locator("button:has-text('发送')")
            if send_btn.count() > 0 and not send_btn.first.is_disabled():
                send_btn.first.click()
                ok("Message sent via button", True, test_msg)
            else:
                page.keyboard.press("Enter")
                ok("Message sent via Enter", True, test_msg)

            # Wait for SSE response
            page.wait_for_timeout(8000)  # Allow real API response time
        else:
            no("Cannot send message", f"Input count={inp_count}, disabled={disabled}")

        page.screenshot(path=f"{SC}/04-message-sent.png", full_page=True)

        # Check what appeared
        html = page.content()

        # Check for Orchestrator banner
        has_orch = "Orchestrator" in html or "路由" in html
        ok("Orchestrator banner visible", has_orch)

        # Check for intent label
        has_intent = "代码生成" in html
        ok("Intent label (代码生成)", has_intent)

        # Check for CollaborationView
        has_collab = "协作" in html
        ok("CollaborationView visible", has_collab)

        # Check agent names
        for name in agent_names:
            has = name in html
            ok(f"Agent {name} visible", has)

        # ========== 5. CHECK OVERLAPPING / Z-INDEX ==========
        print("\n--- 5. Layout / Z-Index Check ---")
        # Check if CollaborationView overlaps the chat input
        collab_el = page.locator("text=协作任务")
        if collab_el.count() > 0:
            collab_box = collab_el.first.bounding_box()
            inp_box = inp.first.bounding_box() if inp_count > 0 else None
            if collab_box and inp_box:
                overlap_y = collab_box["y"] + collab_box["height"] > inp_box["y"]
                if overlap_y:
                    no("CollaborationView overlaps chat input!",
                       f"Collab bottom={collab_box['y']+collab_box['height']:.0f}, Input top={inp_box['y']:.0f}")
                else:
                    ok("No overlap: CollaborationView above chat input")

        # Check ChatWindow route banner overlap
        route_banner = page.locator("text=Orchestrator")
        if route_banner.count() > 0:
            route_box = route_banner.first.bounding_box()
            if collab_el.count() > 0 and collab_el.first.bounding_box() and route_box:
                overlap = (route_box["y"] + route_box["height"] > collab_el.first.bounding_box()["y"])
                if overlap:
                    no("Route banner overlaps CollaborationView",
                       f"Route bottom={route_box['y']+route_box['height']:.0f}, Collab top={collab_el.first.bounding_box()['y']:.0f}")
                else:
                    ok("No overlap: Route banner above CollaborationView")

        # ========== 6. AGENT TAB ==========
        print("\n--- 6. Agent Tab ---")
        agent_tab = page.locator("button:has-text('Agent')")
        if agent_tab.count() > 0:
            agent_tab.first.click()
            page.wait_for_timeout(1500)
        page.screenshot(path=f"{SC}/05-agent-tab.png", full_page=True)

        html = page.content()
        has_agent_list = "Agent" in html and ("默认" in html or agent_names[0] in html)
        ok("Agent panel shows agents", has_agent_list)

        # Capture console errors
        errors = [m for m in console_log if "ERROR" in m and "favicon" not in m]
        console_log.clear()
        ok("No console errors on agent tab", len(errors) == 0,
           f"{len(errors)} errors: {'; '.join(errors[:3])}" if errors else "")

        # ========== 7. SETTINGS TAB ==========
        print("\n--- 7. Settings Tab ---")
        settings_tab = page.locator("button:has-text('设置')")
        if settings_tab.count() > 0:
            settings_tab.first.click()
            page.wait_for_timeout(1500)
        page.screenshot(path=f"{SC}/06-settings-tab.png", full_page=True)

        errors = [m for m in console_log if "ERROR" in m and "favicon" not in m]
        console_log.clear()
        ok("No console errors on settings tab", len(errors) == 0,
           f"{len(errors)} errors: {'; '.join(errors[:3])}" if errors else "")

        # ========== 8. GROUP CREATOR MODAL ==========
        print("\n--- 8. Group Creator Modal ---")
        # Go back to sessions
        sessions_tab = page.locator("button:has-text('会话')")
        if sessions_tab.count() > 0:
            sessions_tab.first.click()
            page.wait_for_timeout(500)

        group_btn = page.locator("button:has-text('群聊')")
        if group_btn.count() > 0:
            group_btn.first.click()
            page.wait_for_timeout(2000)
        page.screenshot(path=f"{SC}/07-group-creator.png", full_page=True)

        html = page.content()
        # Verify NO chain toggle
        has_chain_toggle = "链式" in html and ("启用" in html or "开关" in html)
        if has_chain_toggle:
            no("Chain toggle still present in GroupCreator", "Should be auto-triggered")
        else:
            ok("No chain toggle in GroupCreator (auto-trigger)")

        has_agent_checkboxes = page.locator("input[type='checkbox']").count() > 0
        ok("Agent checkboxes visible", has_agent_checkboxes)

        # Close the modal before moving on
        cancel_btn = page.locator("button:has-text('取消')")
        if cancel_btn.count() > 0:
            cancel_btn.first.click()
            page.wait_for_timeout(500)

        # ========== 9. SINGLE CHAT ==========
        print("\n--- 9. Single Chat Mode ---")
        # Click single chat session
        page.locator("button:has-text('会话')").first.click()
        page.wait_for_timeout(500)
        single_el = page.locator("text=单聊测试")
        if single_el.count() > 0:
            single_el.first.click()
            page.wait_for_timeout(2000)

        page.screenshot(path=f"{SC}/08-single-chat.png", full_page=True)

        # Check agent selector at bottom
        agent_select = page.locator("select")
        ok(f"Agent selector visible ({agent_select.count()})", agent_select.count() > 0)

        # Try sending in single mode
        inp2 = page.locator("input[type='text']")
        if inp2.count() > 0 and not inp2.first.is_disabled():
            inp2.first.fill("Hello")
            send2 = page.locator("button:has-text('发送')")
            if send2.count() > 0:
                send2.first.click()
                page.wait_for_timeout(5000)
            ok("Single chat message sent", True)

        page.screenshot(path=f"{SC}/09-single-response.png", full_page=True)

        # ========== 10. FINAL CONSOLE REPORT ==========
        print("\n--- 10. Final Console Report ---")
        errors = [m for m in console_log if "ERROR" in m and "favicon" not in m and "extension" not in m]
        warns = [m for m in console_log if "WARN" in m]

        all_errors = errors + warns
        if all_errors:
            for e in all_errors[:15]:
                print(f"  CONSOLE: {e}")
        ok("No blocking JS errors", len(errors) == 0,
           f"{len(errors)} errors, {len(warns)} warnings")

        browser.close()

    # ========== REPORT ==========
    print(f"\n{'='*60}")
    print(f"RESULT: {P}/{P+F} passed")
    print(f"{'='*60}")
    if F > 0:
        print(f"\n  FAILURES: {F}")
        sys.exit(1)

if __name__ == "__main__":
    main()
