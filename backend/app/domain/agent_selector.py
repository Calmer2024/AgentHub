"""Agent 选择器 —— 基于 Agent Skill Profile 和元数据标签匹配。

Domain 层纯逻辑，零框架依赖。

核心原则: Agent 是 CLI 好友。
  - Agent 是用户接入的本机 CLI 工具实例（名称、描述、system_prompt 自定义）
  - 评分依据: Agent.description + Agent.system_prompt 与需求标签的匹配度
  - 执行能力来自 CLI 配置，调度评分只看 Agent 元数据
"""

import json
from dataclasses import dataclass, field

from ..models import AgentConfig
from .skill_registry import SkillRegistry


@dataclass
class ScoredAgent:
    """评分后的 Agent 条目。"""
    agent: AgentConfig
    score: int
    match_tags: list[str] = field(default_factory=list)
    reason: str = "fallback"  # "exact_mention" | "tag_match" | "fallback"


class AgentSelector:
    """Agent 选择器 —— 匹配需求标签与 Agent 元数据。

    选择策略 (优先级):
      1. @mention → 精确匹配 Agent.name (用户自定义名称)，score = MAX
      2. 标签匹配 → required_tags 在 Agent.description + Agent.system_prompt 中的命中数
      3. Fallback → 全部 Agent 得分相同

    用法:
        selector = AgentSelector()
        scored = selector.select(["React", "前端"], agents)
        # → [ScoredAgent(agent=前端专家, score=2, ...), ...]
    """

    MAX_MENTION_SCORE = 9999
    FALLBACK_SCORE = 1

    def __init__(self, skill_registry: SkillRegistry | None = None):
        self._skills = skill_registry or SkillRegistry()

    def select(
        self,
        required_tags: list[str],
        candidates: list[AgentConfig],
        mentions: list[str] | None = None,
    ) -> list[ScoredAgent]:
        """根据能力标签和 @mention 从候选中选择 Agent。"""
        if not candidates:
            return []

        mention_ids: set[str] = set(mentions) if mentions else set()

        scored: list[ScoredAgent] = []

        for agent in candidates:
            # 优先级 1: @mention 精确匹配
            if mention_ids and agent.id in mention_ids:
                scored.append(ScoredAgent(
                    agent=agent,
                    score=self.MAX_MENTION_SCORE,
                    match_tags=[],
                    reason="exact_mention",
                ))
                continue

            # 如果存在 @mention 但不匹配此 Agent，跳过
            if mention_ids:
                continue

            # 优先级 2: Skill 显式匹配
            tag_score, matched = self._match_tags(required_tags, agent)
            if tag_score > 0:
                scored.append(ScoredAgent(
                    agent=agent,
                    score=tag_score,
                    match_tags=matched,
                    reason="tag_match",
                ))
            else:
                # 优先级 3: Fallback
                scored.append(ScoredAgent(
                    agent=agent,
                    score=self.FALLBACK_SCORE,
                    match_tags=[],
                    reason="fallback",
                ))

        # 按得分降序排列
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored

    def _match_tags(self, tags: list[str], agent: AgentConfig) -> tuple[int, list[str]]:
        """匹配 required tags 与 Agent Skill Profile，返回 (得分, 命中标签列表)。"""
        if not tags:
            return (self.FALLBACK_SCORE, [])

        skill_score, skill_matched = self._match_skill_tags(tags, agent)
        search_text = self._build_search_text(agent).lower()
        matched: list[str] = list(skill_matched)
        score = skill_score

        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower in search_text:
                if tag not in matched:
                    matched.append(tag)
                # 权重: name 命中 > description 命中 > system_prompt 命中
                if tag_lower in agent.name.lower():
                    score += 5
                elif tag_lower in (agent.description or "").lower():
                    score += 5
                else:
                    score += 5

        return (score, matched)

    def _match_skill_tags(self, tags: list[str], agent: AgentConfig) -> tuple[int, list[str]]:
        matched: list[str] = []
        score = 0
        normalized_tags = [(tag, tag.lower()) for tag in tags]

        primary_id = agent.primary_skill or "general_coding"
        primary = self._skills.get(primary_id)
        primary_terms = {primary_id.lower()}
        if primary:
            primary_terms.update(tag.lower() for tag in primary.tags)

        auxiliary_ids = _decode_json_list(agent.auxiliary_skills)
        auxiliary_terms: dict[str, set[str]] = {}
        for skill_id in auxiliary_ids:
            skill = self._skills.get(skill_id)
            terms = {skill_id.lower()}
            if skill:
                terms.update(tag.lower() for tag in skill.tags)
            auxiliary_terms[skill_id] = terms

        for original, lower in normalized_tags:
            if lower in primary_terms:
                matched.append(original)
                score += 100 if lower == primary_id.lower() else 50
                continue
            for skill_id, terms in auxiliary_terms.items():
                if lower in terms:
                    matched.append(original)
                    score += 30 if lower == skill_id.lower() else 15
                    break

        return score, matched

    def _build_search_text(self, agent: AgentConfig) -> str:
        """构建用于标签匹配的搜索文本。"""
        parts = [
            agent.name or "",
            agent.description or "",
            agent.system_prompt or "",
            agent.primary_skill or "",
            " ".join(_decode_json_list(agent.auxiliary_skills)),
        ]
        return " ".join(parts)


def _decode_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
