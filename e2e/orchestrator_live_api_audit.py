"""真实 Orchestrator API 验收脚本。

运行本地 dev server，覆盖两条产品边界:
- DAG/chain 等结构化多 Agent 协作: 必须生成 Orchestrator 中枢总结。
- 普通 parallel 多 Agent 回复: 只展示各 Agent 产出，不自动生成中枢总结。
"""

from __future__ import annotations

import json
import time
import urllib.request
from urllib.error import HTTPError

BASE = "http://127.0.0.1:8000/api"


def post(path: str, payload: dict, timeout: int = 120) -> tuple[int, dict | list | str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else ""
    except HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, json.loads(body) if body else ""


def get(path: str, timeout: int = 30) -> tuple[int, dict | list | str]:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body) if body else ""


def delete(path: str, timeout: int = 30) -> None:
    req = urllib.request.Request(f"{BASE}{path}", method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            pass
    except Exception:
        pass


def read_sse(path: str, payload: dict, timeout: int = 180) -> list[dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    events: list[dict] = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            events.append(event)
            if event.get("type") == "orchestrator.task_completed":
                break
    return events


def create_agent(name: str, description: str, prompt: str, ts: int) -> str:
    status, data = post("/agents", {
        "name": f"{name}-{ts}",
        "description": description,
        "systemPrompt": prompt,
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "temperature": 0.2,
    })
    assert status == 201, (status, data)
    return data["id"]


def create_group_session(title: str, agent_ids: list[str]) -> str:
    status, session = post("/sessions", {
        "title": title,
        "mode": "group",
        "agentConfigIds": agent_ids,
    })
    assert status == 201, (status, session)
    return session["id"]


def event_types(events: list[dict]) -> list[str]:
    return [
        e.get("type") or ("agent.done" if e.get("done") and e.get("agentId") else "token")
        for e in events
    ]


def run_dag_audit() -> dict:
    ts = int(time.time())
    specs = [
        ("QA架构师", "架构 设计 方案", "你是架构师。只输出2句中文方案，必须提到“方案”。"),
        ("QA前端", "React 前端 UI 组件", "你是前端工程师。只输出2句中文，必须提到“前端”。"),
        ("QA后端", "Python 后端 API 数据库", "你是后端工程师。只输出2句中文，必须提到“后端”。"),
        ("QA审查员", "审查 测试 安全", "你是审查员。只输出2句中文，必须提到“审查”。"),
    ]
    agent_ids: list[str] = []
    sid: str | None = None
    try:
        for name, description, prompt in specs:
            agent_ids.append(create_agent(name, description, prompt, ts))
        sid = create_group_session(f"真实Orchestrator验收-{ts}", agent_ids)

        events = read_sse(f"/sessions/{sid}/chat", {
            "content": "帮我做一个登录系统，先设计方案，再前后端分别实现，最后审查。每个Agent只输出两句。",
        })
        task_started = next(e for e in events if e.get("type") == "orchestrator.task_started")
        phases = task_started["dag"]["phases"]
        phase_events = [e for e in events if e.get("type") == "orchestrator.phase_change"]
        summary_events = [e for e in events if e.get("type", "").startswith("orchestrator.summary_")]
        token_events = [e for e in events if e.get("agentId") and e.get("token") and not e.get("done")]

        assert [p["phase"] for p in phases] == [0, 1, 2], phases
        assert phases[1]["mode"] == "parallel", phases
        assert any(e["phase"] == 1 and e["status"] == "running" for e in phase_events), phase_events
        assert any(e["phase"] == 2 and e["status"] == "completed" for e in phase_events), phase_events
        assert token_events, "没有收到真实 token 流"
        assert all("messageId" in e and "role" in e and "phase" in e for e in token_events[:5])
        assert any(e.get("type") == "orchestrator.summary_started" for e in summary_events)
        assert any(e.get("type") == "orchestrator.summary_delta" for e in summary_events)
        assert any(e.get("type") == "orchestrator.summary_completed" for e in summary_events)
        summary_started = next(e for e in summary_events if e.get("type") == "orchestrator.summary_started")
        assert summary_started["metadata"]["orchestrator_provider"], summary_started
        assert summary_started["metadata"]["orchestrator_model"], summary_started
        assert events[-1].get("type") == "orchestrator.task_completed", events[-1]

        status, messages = get(f"/sessions/{sid}/messages")
        assert status == 200
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) >= 5, messages
        assert any(m.get("sourceType") == "orchestrator" for m in assistant_msgs), messages
        assert any(m.get("contentType") == "orchestrator_summary" for m in assistant_msgs), messages

        return {
            "sessionId": sid,
            "events": len(events),
            "eventTypesSample": event_types(events)[:20],
            "phases": phases,
            "phaseEvents": phase_events,
            "summaryEventCount": len(summary_events),
            "summaryEventTypes": [e.get("type") for e in summary_events[:5]],
            "assistantMessages": len(assistant_msgs),
            "taskCompleted": events[-1],
        }
    finally:
        if sid:
            delete(f"/sessions/{sid}")
        for aid in agent_ids:
            delete(f"/agents/{aid}")


def run_simple_parallel_audit() -> dict:
    ts = int(time.time())
    agent_ids: list[str] = []
    sid: str | None = None
    try:
        for idx in (1, 2):
            agent_ids.append(create_agent(
                f"QAParallel{idx}",
                "general assistant concise answer",
                "Answer in one short English sentence.",
                ts,
            ))
        sid = create_group_session(f"普通parallel验收-{ts}", agent_ids)

        events = read_sse(
            f"/sessions/{sid}/chat",
            {"content": "Hello. Each agent reply with one short sentence."},
        )
        task_started = next(e for e in events if e.get("type") == "orchestrator.task_started")
        summary_events = [e for e in events if e.get("type", "").startswith("orchestrator.summary_")]

        assert "dag" not in task_started, task_started
        assert not summary_events, summary_events[:3]
        assert events[-1].get("type") == "orchestrator.task_completed", events[-1]

        status, messages = get(f"/sessions/{sid}/messages")
        assert status == 200
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 2, messages
        assert not any(m.get("sourceType") == "orchestrator" for m in assistant_msgs), messages
        assert not any(m.get("contentType") == "orchestrator_summary" for m in assistant_msgs), messages

        return {
            "sessionId": sid,
            "events": len(events),
            "eventTypes": event_types(events),
            "summaryEventCount": len(summary_events),
            "assistantMessages": len(assistant_msgs),
            "taskCompleted": events[-1],
        }
    finally:
        if sid:
            delete(f"/sessions/{sid}")
        for aid in agent_ids:
            delete(f"/agents/{aid}")


def main() -> None:
    print(json.dumps({
        "dag": run_dag_audit(),
        "simpleParallel": run_simple_parallel_audit(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
