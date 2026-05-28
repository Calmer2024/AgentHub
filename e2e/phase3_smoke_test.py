"""Phase 3 Module 2 真实浏览器体验测试 —— 覆盖核心流程 + UI/UX 质量。"""
from playwright.sync_api import sync_playwright
import time

BASE = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000"

def test_all():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        errors = []

        # 捕获控制台错误
        page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"[PAGE ERROR] {e.message}"))

        try:
            # ===== 1. 页面加载 =====
            print("=" * 60)
            print("1. 基础启动和页面加载")
            print("=" * 60)

            page.goto(BASE, timeout=15000)
            page.wait_for_load_state("networkidle")

            # 截图
            page.screenshot(path="/tmp/agenthub_01_initial.png", full_page=True)

            # 检查页面标题/内容
            body_text = page.text_content("body") or ""
            has_sidebar = page.locator("text=会话").count() > 0
            has_agents_tab = page.locator("text=Agent").count() > 0
            has_settings_tab = page.locator("text=设置").count() > 0

            print(f"  页面加载: {'OK' if 'AgentHub' in body_text or has_sidebar else 'FAIL - 内容异常'}")
            print(f"  侧边栏 Tab: 会话={'OK' if has_sidebar else 'FAIL'}, Agent={'OK' if has_agents_tab else 'FAIL'}, 设置={'OK' if has_settings_tab else 'FAIL'}")
            print(f"  控制台错误: {len(errors)} 条")
            for e in errors[:5]:
                print(f"    - {e[:120]}")

            # 空状态引导文案
            empty_text = page.text_content("main") or page.text_content("body") or ""
            has_guide = "新建对话" in empty_text or "开始" in empty_text
            print(f"  空状态引导: {'OK - 有引导文案' if has_guide else 'WARN - 需检查'}")

            # ===== 2. 会话管理 =====
            print("=" * 60)
            print("2. 会话管理")
            print("=" * 60)

            # 新建单聊
            new_chat_btn = page.locator("button:has-text('新建对话')")
            if new_chat_btn.count() > 0:
                new_chat_btn.first.click()
                page.wait_for_timeout(500)
                print("  新建单聊: OK")
            else:
                print("  新建单聊: FAIL - 找不到按钮")

            # 检查会话出现在列表
            session_count = page.locator("text=/新对话|群聊/").count()
            print(f"  会话列表: 找到 {session_count} 个会话")

            # 再新建一个
            if new_chat_btn.count() > 0:
                new_chat_btn.first.click()
                page.wait_for_timeout(300)
                after = page.locator("text=/新对话|群聊/").count()
                print(f"  再建会话: 从 {session_count} → {after}")

            # ===== 3. Agent 管理 =====
            print("=" * 60)
            print("3. Agent 管理")
            print("=" * 60)

            # 切换到 Agent Tab
            agents_tab = page.locator("button:has-text('Agent')")
            if agents_tab.count() > 0:
                agents_tab.first.click()
                page.wait_for_timeout(500)
                page.screenshot(path="/tmp/agenthub_02_agents.png", full_page=True)

            agent_items = page.locator("text=/默认助手|测试/").count()
            has_default_agent = "默认助手" in page.text_content("body") or ""
            print(f"  Agent 列表: {'OK - 有默认Agent' if has_default_agent else 'WARN'}, items={agent_items}")

            # 新建 Agent
            add_agent_btn = page.locator("button:has-text('添加')")
            if add_agent_btn.count() == 0:
                add_agent_btn = page.locator("button:has-text('新建')")
            if add_agent_btn.count() == 0:
                add_agent_btn = page.locator("button:has-text('Add')")
            if add_agent_btn.count() > 0:
                print("  新建Agent按钮: OK")
            else:
                print("  新建Agent按钮: WARN - 未找到")

            # ===== 4. 单聊模式 =====
            print("=" * 60)
            print("4. 单聊模式 — 核心流程")
            print("=" * 60)

            # 切回会话 Tab
            sessions_tab = page.locator("button:has-text('会话')")
            if sessions_tab.count() > 0:
                sessions_tab.first.click()
                page.wait_for_timeout(300)

            # 新建对话并发送消息
            if new_chat_btn.count() > 0:
                new_chat_btn.first.click()
                page.wait_for_timeout(300)

            # 找输入框
            input_box = page.locator('[role="textbox"]')
            if input_box.count() == 0:
                input_box = page.locator("input[type='text']")
            if input_box.count() == 0:
                input_box = page.locator("textarea")

            if input_box.count() > 0:
                input_box.first.fill("你好，请介绍一下你自己")
                page.wait_for_timeout(200)
                print("  输入框: OK")

            # 找发送按钮
            send_btn = page.locator("button:has-text('发送')")
            if send_btn.count() == 0:
                send_btn = page.locator("button[type='submit']")
            if send_btn.count() > 0 and input_box.count() > 0:
                send_btn.first.click()
                page.wait_for_timeout(500)
                print("  发送消息: OK")

                # 等 SSE 流式响应
                page.wait_for_timeout(3000)
                page.screenshot(path="/tmp/agenthub_03_chat_after.png", full_page=True)

                # 检查消息气泡
                msg_count = page.locator(".message, [class*='bubble'], [class*='message']").count()
                ai_text = page.text_content("body") or ""
                has_response = len(ai_text) > 50 and ("Hello" in ai_text or "World" in ai_text or "你好" in ai_text)
                print(f"  AI 响应: {'OK - 有回复' if has_response else 'WARN - 可能无响应'}, 气泡数={msg_count}")

                # 检查打字指示器
                typing_indicator = page.locator(".typing-indicator, [class*='typing'], [class*='loading']").count()
                print(f"  打字指示器: {typing_indicator} 个可见")

                # 检查输入框在流式中的状态 (此时可能已完成)
                input_disabled = input_box.first.is_disabled() if input_box.count() > 0 else None
                print(f"  输入框禁用态: {input_disabled}")

                # 空消息测试
                input_box.first.fill("")
                page.wait_for_timeout(100)
                if send_btn.count() > 0:
                    send_btn.first.click()
                    page.wait_for_timeout(500)
                error_visible = "不能为空" in (page.text_content("body") or "") or "empty" in (page.text_content("body") or "").lower()
                print(f"  空消息拦截: {'OK' if error_visible else 'WARN'}")

                # 多轮对话
                input_box = page.locator('[role="textbox"]')
                if input_box.count() > 0:
                    input_box.first.fill("再给我讲个笑话")
                    page.wait_for_timeout(100)
                if send_btn.count() > 0:
                    send_btn.first.click()
                    page.wait_for_timeout(3000)
                msg_count_after = page.locator("[class*='message'], [class*='bubble']").count()
                print(f"  多轮对话: 气泡数 {msg_count} → {msg_count_after}")
            else:
                print("  发送: FAIL - 找不到输入框或发送按钮")
                page.screenshot(path="/tmp/agenthub_03_chat_debug.png", full_page=True)

            # ===== 5. 群聊模式 =====
            print("=" * 60)
            print("5. 群聊模式 — Phase 3 智能协作核心")
            print("=" * 60)

            # 新建群聊
            new_group_btn = page.locator("button:has-text('群聊')")
            if new_group_btn.count() == 0:
                new_group_btn = page.locator("button:has-text('Group')")
            if new_group_btn.count() == 0:
                new_group_btn = page.locator("text=新建群聊")

            if new_group_btn.count() > 0:
                new_group_btn.first.click()
                page.wait_for_timeout(800)
                page.screenshot(path="/tmp/agenthub_04_group_creator.png", full_page=True)

                # 检查链式协作配置
                chain_checkbox = page.locator("text=链式协作")
                chain_visible = chain_checkbox.count() > 0
                print(f"  链式协作配置: {'OK - 可配置' if chain_visible else 'WARN - 未显示'}")

                # 选择 Agent
                agent_checkboxes = page.locator("input[type='checkbox']")
                checked = 0
                for i in range(min(agent_checkboxes.count(), 3)):
                    cb = agent_checkboxes.nth(i)
                    if cb.is_visible():
                        cb.check()
                        checked += 1
                        page.wait_for_timeout(100)
                print(f"  选择Agent: {checked} 个")

                # 创建
                create_btn = page.locator("button:has-text('创建')")
                if create_btn.count() > 0:
                    if create_btn.first.is_enabled():
                        create_btn.first.click()
                        page.wait_for_timeout(800)
                        print("  创建群聊: OK")
                    else:
                        print(f"  创建群聊: WARN - 按钮禁用 (selected={checked})")
                        # 取消
                        cancel_btn = page.locator("button:has-text('取消')")
                        if cancel_btn.count() > 0:
                            cancel_btn.first.click()
                            page.wait_for_timeout(300)
                else:
                    print("  创建群聊: WARN - 无创建按钮")
            else:
                print("  新建群聊: WARN - 找不到按钮")

            # ===== 6. UI/UX 质量 =====
            print("=" * 60)
            print("6. UI/UX 质量检查")
            print("=" * 60)

            page.screenshot(path="/tmp/agenthub_05_final.png", full_page=True)

            # 空状态
            new_chat_btn_present = page.locator("button:has-text('新建对话')").count() > 0
            print(f"  空状态-行动入口: {'OK - 新建对话按钮可见' if new_chat_btn_present else 'FAIL'}")

            # 加载态
            loading_indicators = page.locator("[class*='loading'], [class*='spinner'], [class*='pulse'], [class*='typing']").count()
            print(f"  加载态-指示器: {loading_indicators} 个")

            # 错误态
            error_colors = page.locator("[class*='error'], [class*='red'], .text-red-700, .text-red-600").count()
            print(f"  错误态-红色提示: {error_colors} 处")

            # 边界: 检查是否有溢出/截断
            overflow_elements = page.locator("[class*='overflow'], [class*='truncate'], [class*='ellipsis']").count()
            print(f"  边界态-溢出处理: {overflow_elements} 个")

            # ===== 7. 综合评估 =====
            print("=" * 60)
            print("7. 综合评估")
            print("=" * 60)

            js_errors = [e for e in errors if "error" in e.lower()]
            print(f"  JS 错误: {len(js_errors)} 条")
            print(f"  总警告: {len(errors)} 条")

            # 检查 Spec 5.1 关键功能
            body = page.text_content("body") or ""
            features = {
                "GroupChatCreator": page.locator("button:has-text('群聊')").count() > 0,
                "Agent选择/复选框": agent_checkboxes.count() if 'agent_checkboxes' in dir() else False,
                "消息发送": send_btn.count() > 0 if 'send_btn' in dir() else False,
                "会话列表": session_count > 0 if 'session_count' in dir() else False,
            }
            print(f"\n  功能覆盖:")
            for k, v in features.items():
                print(f"    - {k}: {'OK' if v else 'MISSING'}")

        except Exception as e:
            print(f"\n!!! 测试异常: {e}")
            page.screenshot(path="/tmp/agenthub_error.png", full_page=True)

        browser.close()
        print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_all()
