"""真实前端 Orchestrator UI/UX 验收脚本。"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000/api"
SC = "d:/Files/AI/AgentHub/e2e/screenshots/live-orchestrator"
os.makedirs(SC, exist_ok=True)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def post(path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def delete(path: str) -> None:
    req = urllib.request.Request(f"{API}{path}", method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=20):
            pass
    except Exception:
        pass


def prep_case() -> tuple[str, str, list[str]]:
    ts = int(time.time())
    specs = [
        ("UI架构师", "架构 设计 方案", "你是架构师，只输出1句方案。"),
        ("UI前端", "React 前端 UI 组件", "你是前端工程师，只输出1句前端实现。"),
        ("UI后端", "Python 后端 API 数据库", "你是后端工程师，只输出1句后端实现。"),
        ("UI审查员", "审查 测试 安全", "你是审查员，只输出1句审查意见。"),
    ]
    ids = []
    for name, desc, prompt in specs:
        agent = post("/agents", {
            "name": f"{name}-{ts}",
            "description": desc,
            "systemPrompt": prompt,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "temperature": 0.2,
        })
        ids.append(agent["id"])
    session = post("/sessions", {
        "title": f"UI真实DAG验收-{ts}",
        "mode": "group",
        "agentConfigIds": ids,
    })
    return session["title"], session["id"], ids


def main() -> None:
    title, session_id, agent_ids = prep_case()
    failures: list[str] = []
    console: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda msg: console.append(f"[{msg.type}] {msg.text}"))

        page.goto(FRONTEND, wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.screenshot(path=f"{SC}/01-home.png", full_page=True)

        page.get_by_text(title).first.click()
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SC}/02-empty-group.png", full_page=True)

        textbox = page.locator("input[type='text']").first
        textbox.fill("帮我做一个登录系统，先设计方案，再前后端分别实现，最后审查。每个Agent只输出一句。")
        page.get_by_role("button", name="发送").click()

        page.wait_for_selector("text=Orchestrator", timeout=20000)
        page.wait_for_selector("text=Phase 1", timeout=20000)
        page.wait_for_selector("text=并行", timeout=20000)
        page.screenshot(path=f"{SC}/03-running-dag.png", full_page=True)

        page.wait_for_function(
            "() => document.body.innerText.includes('4 agents completed') "
            "|| document.body.innerText.includes('请求失败') "
            "|| document.body.innerText.includes('连接中断') "
            "|| document.body.innerText.includes('Stream ended unexpectedly')",
            timeout=90000,
        )
        page.wait_for_timeout(1500)
        page.screenshot(path=f"{SC}/04-completed-dag.png", full_page=True)

        html = page.content()
        body_text = page.locator("body").inner_text(timeout=5000)
        if "请求失败" in body_text or "连接中断" in body_text or "Stream ended unexpectedly" in body_text:
            failures.append("成功群聊被前端误报为请求失败或 Stream ended unexpectedly")
        for needle in ["Phase 0", "Phase 1", "Phase 2", "规划者", "执行者", "审查者", "系统整理"]:
            if needle not in body_text:
                failures.append(f"UI 缺少关键协作标识: {needle}")

        msg_boxes = page.locator("text=/Phase [0-2]/").count()
        if msg_boxes < 3:
            failures.append(f"Phase 标记数量过少: {msg_boxes}")

        input_box = textbox.bounding_box()
        panel_box = page.locator("text=Orchestrator").first.bounding_box()
        if input_box and panel_box and panel_box["y"] + panel_box["height"] > input_box["y"]:
            failures.append("Orchestrator 面板疑似遮挡输入框")

        js_errors = [m for m in console if "[error]" in m.lower() and "favicon" not in m.lower()]
        if js_errors:
            failures.append("控制台错误: " + "; ".join(js_errors[:3]))

        print(json.dumps({
            "title": title,
            "screenshots": SC,
            "phaseLabelCount": msg_boxes,
            "hasErrorBanner": bool(re.search(r"请求失败|连接中断|Stream ended unexpectedly", body_text)),
            "consoleSample": console[:10],
            "failures": failures,
            "bodyExcerpt": body_text[:1000],
            "htmlSize": len(html),
        }, ensure_ascii=False, indent=2))
        browser.close()

    if failures:
        raise SystemExit(1)

    delete(f"/sessions/{session_id}")
    for aid in agent_ids:
        delete(f"/agents/{aid}")


if __name__ == "__main__":
    main()
