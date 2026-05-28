"""Orchestrator —— 智能路由 + 意图识别 + 任务拆解 + 链式协作。

Phase 3 升级：从简单 @mention 路由 → 意图驱动协作大脑。
"""

import asyncio
import logging
from ..models import AgentConfig

logger = logging.getLogger(__name__)

# 意图类型映射
INTENT_KEYWORDS: dict[str, list[str]] = {
    "code_gen": ["写代码", "实现", "开发", "修复bug", "重构", "API", "前端", "后端",
                 "组件", "函数", "接口", "数据库", "写一个", "帮我写", "code", "bug",
                 "前后端", "登录页面", "注册", "CRUD"],
    "research": ["调研", "分析", "比较", "推荐", "优缺点", "最新", "技术选型",
                 "什么是最好的", "有什么区别", "research", "对比"],
    "design_ui": ["UI", "界面", "设计", "样式", "CSS", "布局", "颜色", "好看",
                  "美化", "页面", "组件样式", "UX", "交互", "视觉效果"],
    "general_qa": [],  # fallback
}

# Agent 与意图的匹配权重
AGENT_INTENT_SCORES: dict[str, dict[str, int]] = {
    "claude": {"code_gen": 10, "research": 8, "design_ui": 7, "general_qa": 8},
    "deepseek": {"code_gen": 9, "research": 7, "design_ui": 5, "general_qa": 7},
    "openai": {"code_gen": 9, "research": 7, "design_ui": 6, "general_qa": 8},
    "gemini": {"code_gen": 7, "research": 10, "design_ui": 5, "general_qa": 7},
    "glm": {"code_gen": 6, "research": 5, "design_ui": 4, "general_qa": 6},
    "minimax": {"code_gen": 5, "research": 4, "design_ui": 4, "general_qa": 5},
}

# L2: 复杂请求的子任务模板
TASK_TEMPLATES: dict[str, list[dict]] = {
    "code_gen": [
        {"task": "frontend", "tags": ["code", "UI", "frontend", "React"]},
        {"task": "backend", "tags": ["code", "API", "backend", "Python"]},
    ],
    "research": [
        {"task": "search", "tags": ["research", "search", "analysis"]},
        {"task": "summary", "tags": ["writing", "general", "summary"]},
    ],
}

# 链式协作管线
CHAIN_TEMPLATES: dict[str, list[str]] = {
    "code_review": ["claude", "deepseek"],
    "design_to_code": ["gemini", "claude"],
}


class Orchestrator:
    def __init__(self, event_bus=None):
        self._event_bus = event_bus

    # ===== L1: 意图识别 =====

    def detect_intent(self, content: str) -> str:
        for intent, keywords in INTENT_KEYWORDS.items():
            if intent == "general_qa":
                continue
            for kw in keywords:
                if kw.lower() in content.lower():
                    return intent
        return "general_qa"

    def score_agents(self, intent: str, agents: list[AgentConfig]) -> list[AgentConfig]:
        if not agents:
            return []
        scored = []
        for a in agents:
            provider = (a.provider or "").lower()
            score = AGENT_INTENT_SCORES.get(provider, {}).get(intent, 5)
            scored.append((score, a))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored]

    # ===== L2: 任务拆解 =====

    def is_complex(self, content: str) -> bool:
        complex_markers = ["前后端", "API+", "全栈", "前端和后端", "都要",
                           "同时", "一起", "以及", "还有", "并且", "both", "and also"]
        return any(m in content for m in complex_markers)

    def decompose(self, intent: str, agents: list[AgentConfig]) -> list[tuple[str, AgentConfig | None]]:
        templates = TASK_TEMPLATES.get(intent, [])
        if not templates or len(agents) < 2:
            return [("primary", agents[0] if agents else None)]

        tasks: list[tuple[str, AgentConfig | None]] = []
        available = list(agents)
        for tmpl in templates:
            matched = None
            for a in available:
                a_tags = a.system_prompt or ""
                tag_match = any(t.lower() in a_tags.lower() for t in tmpl.get("tags", []))
                if tag_match:
                    matched = a
                    break
            if matched:
                available.remove(matched)
            else:
                matched = available.pop(0) if available else None
            tasks.append((tmpl["task"], matched))
        return tasks

    # ===== L3: 链式协作 =====

    def get_chain(self, chain_name: str, member_agents: list[AgentConfig]) -> list[AgentConfig]:
        provider_order = CHAIN_TEMPLATES.get(chain_name, [])
        ordered = []
        for provider in provider_order:
            for a in member_agents:
                if (a.provider or "").lower() == provider:
                    ordered.append(a)
                    break
        return ordered

    # ===== Routing =====

    async def route(
        self,
        mentions: list[str] | None,
        member_agents: list[AgentConfig],
        content: str | None = None,
    ) -> list[AgentConfig]:
        """决定消息路由到哪些 Agent。Phase 3 升级：支持意图驱动选择。"""
        if mentions:
            mention_set = set(mentions)
            return [a for a in member_agents if a.id in mention_set]

        if content and len(member_agents) > 1:
            intent = self.detect_intent(content)
            scored = self.score_agents(intent, member_agents)
            # 单聊模式下只选最匹配的 1 个；群聊模式下可由 coordinate 控制
            return scored

        return member_agents

    async def coordinate(
        self,
        agents: list[AgentConfig],
        messages: list[dict],
        adapter_factory,
        content: str | None = None,
    ) -> list[dict]:
        if not agents:
            return []

        # L2: 检查是否需要任务拆解
        if content and self.is_complex(content) and len(agents) >= 2:
            intent = self.detect_intent(content)
            tasks = self.decompose(intent, agents)
            if len(tasks) > 1 and self._event_bus:
                await self._event_bus.publish(
                    type(self)._event_type("ORCHESTRATOR_TASK_STARTED"),
                    {"intent": intent, "tasks": [t[0] for t in tasks],
                     "agents": [t[1].name if t[1] else "unknown" for t in tasks]},
                )

        async def invoke(agent: AgentConfig) -> dict | None:
            try:
                adapter = adapter_factory(agent.provider)
                if not adapter or not hasattr(adapter, "chat_stream"):
                    return {"agent_id": agent.id, "agent_name": agent.name,
                            "content": f"[{agent.name} 不可用]", "error": True}
                if self._event_bus:
                    await self._event_bus.publish(
                        type(self)._event_type("AGENT_CALL_STARTED"),
                        {"agent_name": agent.name, "agent_id": agent.id},
                    )
                full = ""
                async for token in adapter.chat_stream(
                    messages=messages,
                    system_prompt=agent.system_prompt,
                    model=agent.model or None,
                ):
                    full += token
                if self._event_bus:
                    await self._event_bus.publish(
                        type(self)._event_type("AGENT_CALL_COMPLETED"),
                        {"agent_name": agent.name, "agent_id": agent.id, "status": "ok"},
                    )
                return {"agent_id": agent.id, "agent_name": agent.name,
                        "content": full, "error": False}
            except asyncio.TimeoutError:
                return {"agent_id": agent.id, "agent_name": agent.name,
                        "content": f"[{agent.name} 响应超时]", "error": True}
            except Exception as e:
                logger.exception("Agent call failed: %s", agent.name)
                return {"agent_id": agent.id, "agent_name": agent.name,
                        "content": f"[{agent.name} 错误: {e}]", "error": True}

        tasks = [asyncio.create_task(invoke(agent)) for agent in agents[:5]]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    @staticmethod
    def _event_type(name: str):
        from ..event_bus import EventType
        return EventType[name]


orchestrator = Orchestrator()
