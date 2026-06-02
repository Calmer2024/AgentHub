"""Orchestrator 精确交互测试 — 使用正确的 DOM 选择器。"""
import os, sys, time, json, requests
os.environ["PYTHONIOENCODING"] = "utf-8"

FRONTEND = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000/api"
SCREENSHOTS = "d:/Files/AI/AgentHub/e2e/screenshots"
os.makedirs(SCREENSHOTS, exist_ok=True)

from playwright.sync_api import sync_playwright

pass_c = 0; fail_c = 0
def ck(n, v, d=""):
    global pass_c, fail_c
    if v: pass_c += 1; print(f"  [OK] {n}")
    else: fail_c += 1; print(f"  [XX] {n}: {d}")

def main():
    print("=== AgentHub 真实场景测试 ===\n")

    # 1. API: 获取 Agent + 创建群聊
    print("--- API 准备 ---")
    try:
        agents = requests.get(f"{API}/agents", timeout=10).json()
        ck("获取 Agent 列表", len(agents) >= 2, f"{len(agents)} agents")
        agent_ids = [a["id"] for a in agents[:2]]
        agent_names = [a["name"] for a in agents[:2]]
    except Exception as e:
        ck("获取 Agent 列表", False, str(e))
        return

    try:
        r = requests.post(f"{API}/sessions", json={
            "title": "实时测试群聊",
            "mode": "group",
            "agentConfigIds": agent_ids,
        }, timeout=10)
        session = r.json()
        sid = session["id"]
        ck(f"创建群聊", "id" in session, f"{sid[:10]}...")
    except Exception as e:
        ck("创建群聊", False, str(e))
        return

    # 2. 浏览器
    print("\n--- 浏览器交互 ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(10000)

        js_errs = []
        page.on("console", lambda m: js_errs.append(m.text) if m.type == "error" else None)

        page.goto(FRONTEND, wait_until="networkidle")
        page.wait_for_timeout(2000)

        # 点击群聊会话
        try:
            el = page.locator("text=实时测试群聊")
            if el.count() > 0:
                el.first.click()
                page.wait_for_timeout(2000)
                ck("选择群聊", True)
        except:
            ck("选择群聊", False)

        page.screenshot(path=f"{SCREENSHOTS}/t01-loaded.png", full_page=True)

        # 查找聊天输入 - 是 <input type="text"> 而不是 textarea
        input_el = page.locator("input[type='text']")
        has_inp = input_el.count() > 0
        ck(f"输入框可见 ({input_el.count()} 个)", has_inp)

        if not has_inp:
            # 打印页面上的所有 input 元素
            all_inputs = page.locator("input")
            all_textareas = page.locator("textarea")
            all_btns = page.locator("button")
            print(f"    页面元素: input={all_inputs.count()}, textarea={all_textareas.count()}, button={all_btns.count()}")
            for i, inp in enumerate(all_inputs.all()[:5]):
                print(f"    input[{i}]: type={inp.get_attribute('type')}, placeholder={inp.get_attribute('placeholder')}, disabled={inp.is_disabled()}")
            browser.close()
            return

        # 检查是否被禁用
        first_input = input_el.first
        is_disabled = first_input.is_disabled()
        ck("输入框可用", not is_disabled, f"disabled={is_disabled}")

        if not is_disabled:
            # 发送消息
            test_msg = "帮我写一个React登录组件"
            first_input.fill(test_msg)
            page.wait_for_timeout(300)

            # 按 Enter 或点击发送
            send_btn = page.locator("button[type='submit']")
            if send_btn.count() > 0 and not send_btn.first.is_disabled():
                send_btn.first.click()
                ck("消息发送", True, test_msg)
            else:
                first_input.press("Enter")
                ck("消息发送(Enter)", True, test_msg)

            # 等待 SSE 响应
            page.wait_for_timeout(8000)
        else:
            ck("消息发送", False, "输入框被禁用")
            page.screenshot(path=f"{SCREENSHOTS}/t02-disabled.png", full_page=True)
            browser.close()
            return

        page.screenshot(path=f"{SCREENSHOTS}/t02-sent.png", full_page=True)

        # 检查响应
        html = page.content()

        # Orchestrator 横幅
        has_route = "路由" in html or "Orchestrator" in html
        ck("Orchestrator 横幅", has_route)

        # Intent 标签
        has_intent = "代码生成" in html
        ck("Intent 标签", has_intent, "期望: 代码生成")

        # CollaborationView / Agent 卡片
        has_collab = "协作任务" in html or "协作" in html
        ck("协作面板", has_collab)

        for name in agent_names:
            has_name = name in html
            ck(f"Agent: {name}", has_name)

        page.screenshot(path=f"{SCREENSHOTS}/t03-response.png", full_page=True)

        # 检查 JS 错误（排除 favicon）
        real_errs = [e for e in js_errs if "favicon" not in e.lower() and "extension" not in e.lower()]
        ck("JS 无错误", len(real_errs) == 0, f"{len(real_errs)} errors: {'; '.join(real_errs[:3])}" if real_errs else "")

        browser.close()

    # 3. SSE 事件验证
    print("\n--- SSE 事件协议验证 ---")
    try:
        r = requests.post(f"{API}/sessions/{sid}/chat", json={
            "content": "分析一下React的优缺点",
            "mentions": None,
        }, timeout=30, stream=True)

        event_types = set()
        agent_start = 0
        chain_steps = 0
        task_started = False
        task_completed = False

        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                try:
                    d = json.loads(line[6:])
                    t = d.get("type", "")
                    if t:
                        event_types.add(t)
                    if t == "orchestrator.task_started":
                        task_started = True
                        ck("SSE: task_started", "tasks" in d, f"tasks={len(d.get('tasks',[]))}")
                    if t == "orchestrator.task_completed":
                        task_completed = True
                        ck("SSE: task_completed", True, d.get("summary", ""))
                    if t == "orchestrator.chain_step":
                        chain_steps += 1
                    if t == "orchestrator.route":
                        ck("SSE: route", "agents" in d, f"agents={len(d.get('agents',[]))}")
                    if t == "agent.start":
                        agent_start += 1
                    if d.get("done") and d.get("agentId"):
                        pass  # per-agent done (should not stop stream in client)
                except:
                    pass

        ck("SSE 有 route 事件", "orchestrator.route" in event_types)
        ck("SSE 有 task_started", task_started)
        ck("SSE 有 task_completed", task_completed)
        ck(f"SSE 有 agent.start ({agent_start})", agent_start > 0)

    except Exception as e:
        ck("SSE 事件验证", False, str(e))

    # 报告
    print(f"\n=== {pass_c}/{pass_c+fail_c} 通过 ===")
    if fail_c > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
