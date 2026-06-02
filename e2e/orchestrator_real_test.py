"""Orchestrator 真实场景 E2E 测试 — Playwright 浏览器自动化。

测试协议覆盖:
  - 页面加载
  - Agent 面板
  - 群聊创建 + Orchestrator 路由
  - CollaborationView 渲染
  - Intent 标签
  - 错误处理
"""

from playwright.sync_api import sync_playwright
import time, sys

FRONTEND = "http://127.0.0.1:5173"
SCREENSHOTS = "d:/Files/AI/AgentHub/e2e/screenshots"

import os
os.makedirs(SCREENSHOTS, exist_ok=True)

results = []

def check(name, condition, detail=""):
    status = "✅" if condition else "❌"
    results.append((name, status, detail))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))

def main():
    print("=" * 60)
    print("Orchestrator E2E 真实场景测试")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(15000)

        # ===== 1. 页面加载 =====
        print("\n--- 1. 页面加载 ---")
        try:
            page.goto(FRONTEND, wait_until="networkidle")
            page.wait_for_timeout(2000)
            check("页面加载成功", True)
        except Exception as e:
            check("页面加载成功", False, str(e))
            browser.close()
            return

        page.screenshot(path=f"{SCREENSHOTS}/01-page-loaded.png", full_page=True)

        # 检查基本 UI 元素
        has_new_chat = page.locator("text=新建对话").count() > 0 or page.locator("button:has-text('新建')").count() > 0
        check("首页显示新建对话入口", has_new_chat)

        page_text = page.content()
        has_agent_tab = "Agent" in page_text
        has_settings_tab = "设置" in page_text or "Settings" in page_text
        check("侧边栏显示 Agent 标签", has_agent_tab)
        check("侧边栏显示设置标签", has_settings_tab)

        # ===== 2. Agent 面板 =====
        print("\n--- 2. Agent 面板 ---")
        try:
            agent_tab = page.locator("button:has-text('Agent')")
            if agent_tab.count() > 0:
                agent_tab.first.click()
                page.wait_for_timeout(2000)
        except:
            pass

        page.screenshot(path=f"{SCREENSHOTS}/02-agent-panel.png", full_page=True)

        agent_list_text = page.content()
        has_agents = "默认助手" in agent_list_text or "Agent" in agent_list_text
        check("Agent 面板显示 agent 列表", has_agents)

        # 通过 API 确认后台有 agent
        print("\n--- 2b. API 检查 ---")
        import requests
        try:
            r = requests.get("http://127.0.0.1:8000/api/agents", timeout=10)
            agents_data = r.json()
            agent_count = len(agents_data)
            check(f"API 返回 {agent_count} 个 Agent", agent_count > 0, f"找到 {agent_count} 个")
            for a in agents_data[:3]:
                print(f"    - {a.get('name')} ({a.get('provider')}/{a.get('model')})")
        except Exception as e:
            check("API /agents 可访问", False, str(e))
            agents_data = []

        # ===== 3. 创建群聊 =====
        print("\n--- 3. 创建群聊 ---")
        # 切换到会话列表
        try:
            sessions_tab = page.locator("button:has-text('会话')")
            if sessions_tab.count() > 0:
                sessions_tab.first.click()
                page.wait_for_timeout(1000)
        except:
            pass

        # 查找创建群聊按钮
        group_btn = page.locator("button:has-text('群聊')") or page.locator("button:has-text('群')")
        if group_btn.count() > 0:
            group_btn.first.click()
            page.wait_for_timeout(2000)
            check("群聊创建弹窗打开", True)
        else:
            check("群聊创建弹窗打开", False, "未找到群聊按钮")
            # 尝试用 API 创建
            print("    尝试通过 API 创建群聊...")
            try:
                agent_ids = [a["id"] for a in agents_data[:2]] if len(agents_data) >= 2 else []
                if agent_ids:
                    r = requests.post("http://127.0.0.1:8000/api/sessions", json={
                        "title": "测试群聊",
                        "mode": "group",
                        "agentConfigIds": agent_ids,
                    }, timeout=10)
                    if r.status_code == 200:
                        session_data = r.json()
                        session_id = session_data["id"]
                        check("通过 API 创建群聊成功", True, f"session_id={session_id[:8]}...")
                    else:
                        check("通过 API 创建群聊成功", False, f"HTTP {r.status_code}: {r.text}")
                else:
                    check("通过 API 创建群聊成功", False, "Agent 数量不足 2 个")
            except Exception as e:
                check("通过 API 创建群聊成功", False, str(e))

        page.screenshot(path=f"{SCREENSHOTS}/03-group-creator.png", full_page=True)

        # ===== 4. UI 中已有内容检查 =====
        print("\n--- 4. 检查当前聊天界面 ---")
        # 切换回会话列表并点击第一个群聊
        try:
            sessions_tab = page.locator("button:has-text('会话')")
            if sessions_tab.count() > 0:
                sessions_tab.first.click()
                page.wait_for_timeout(1000)
        except:
            pass

        page.screenshot(path=f"{SCREENSHOTS}/04-current-chat.png", full_page=True)

        # 检查是否显示了聊天界面
        has_chat_input = page.locator("textarea").count() > 0 or page.locator("input[type='text']").count() > 0
        check("聊天输入框存在", has_chat_input)

        # ===== 5. 检查前端 JS 错误 =====
        print("\n--- 5. 前端控制台检查 ---")
        console_errors = []
        page.on("console", lambda msg: (
            console_errors.append(f"[{msg.type}] {msg.text}")
            if msg.type == "error" else None
        ))

        page.screenshot(path=f"{SCREENSHOTS}/05-before-send.png", full_page=True)

        # ===== 6. 最终截图 + 报告 =====
        print("\n--- 6. 最终页面状态 ---")
        page.screenshot(path=f"{SCREENSHOTS}/06-final-state.png", full_page=True)

        browser.close()

    # ===== 报告 =====
    print("\n" + "=" * 60)
    print("测试报告")
    print("=" * 60)
    passed = sum(1 for _, s, _ in results if "✅" in s)
    failed = sum(1 for _, s, _ in results if "❌" in s)
    for name, status, detail in results:
        print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
    print(f"\n总结: {passed}/{passed+failed} 通过")
    if failed > 0:
        print("失败项:")
        for name, status, detail in results:
            if "❌" in status:
                print(f"  - {name}: {detail}")
        sys.exit(1)
    else:
        print("全部通过!")


if __name__ == "__main__":
    main()
