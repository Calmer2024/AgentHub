from __future__ import annotations

"""Skill registry for Agent Profiles.

AgentHub keeps a small built-in baseline, then extends it from the user's local
Skill Pool. A skill directory is expected to contain a ``SKILL.md`` file with
optional YAML-style front matter:

---
name: frontend-design
description: Build polished frontend interfaces.
---

The full markdown body becomes the prompt injected into an Agent Profile.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import re

from ..config import settings

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    description: str
    tags: tuple[str, ...]
    prompt: str
    source: str = "builtin"
    path: str | None = None

    def to_api(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
            "source": self.source,
            "path": self.path,
        }


BUILTIN_SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        id="general_coding",
        name="通用工程师",
        description="处理常规代码实现、修复和项目内工程任务。",
        tags=("code", "workspace", "implementation", "工程", "代码"),
        prompt=(
            "你是通用工程师 Agent。你负责理解用户需求，在当前项目工作区中"
            "进行必要的代码实现、修复、说明和验证。"
        ),
    ),
    SkillDefinition(
        id="frontend_engineer",
        name="前端工程师",
        description="负责前端界面、交互、组件和样式实现。",
        tags=("frontend", "react", "ui", "css", "前端", "组件", "界面"),
        prompt=(
            "你是前端工程师 Agent。你专注于 UI、交互、组件结构、样式系统、"
            "前端状态管理和浏览器端体验。"
        ),
    ),
    SkillDefinition(
        id="backend_engineer",
        name="后端工程师",
        description="负责 API、数据库、服务端逻辑和后端集成。",
        tags=("backend", "api", "database", "python", "后端", "数据库", "接口"),
        prompt=(
            "你是后端工程师 Agent。你专注于 API 设计、数据库模型、服务端逻辑、"
            "数据一致性、错误处理和后端测试。"
        ),
    ),
    SkillDefinition(
        id="product_manager",
        name="产品经理",
        description="负责业务目标、用户角色、流程边界、优先级和验收口径。",
        tags=("product", "prd", "requirements", "scope", "acceptance", "产品", "需求", "验收"),
        prompt=(
            "你是产品经理 Agent。你负责把模糊想法收敛成可执行产品需求：明确目标用户、"
            "业务流程、权限边界、功能优先级、非目标、验收标准和风险。你不直接做技术实现，"
            "输出应服务于后续架构、设计、开发和测试。"
        ),
    ),
    SkillDefinition(
        id="requirements_analyst",
        name="需求分析",
        description="负责需求澄清、业务规则、异常流程、权限矩阵和用例。",
        tags=("requirements", "analysis", "use_case", "permission", "需求", "业务规则", "权限"),
        prompt=(
            "你是需求分析 Agent。你专注识别隐藏规则、异常流程、角色权限、状态流转、"
            "业务术语和边界条件。遇到不明确处先列出澄清问题；若必须推进，明确写出假设。"
        ),
    ),
    SkillDefinition(
        id="architect",
        name="架构师",
        description="负责方案、架构、数据模型、边界和技术决策。",
        tags=("architecture", "design", "schema", "plan", "架构", "设计", "方案"),
        prompt=(
            "你是架构师 Agent。你负责拆解需求、识别边界、设计模块关系、"
            "定义数据模型和接口契约。除非明确要求，不直接写具体业务代码。"
        ),
    ),
    SkillDefinition(
        id="api_designer",
        name="API 设计",
        description="负责接口契约、请求响应结构、错误码、权限和兼容性。",
        tags=("api", "openapi", "contract", "rest", "接口", "契约", "错误码"),
        prompt=(
            "你是 API 设计 Agent。你负责定义稳定清晰的接口契约，包括资源模型、请求响应、"
            "错误码、分页筛选、鉴权权限、幂等性和向后兼容。优先输出 OpenAPI/Markdown 契约。"
        ),
    ),
    SkillDefinition(
        id="database_designer",
        name="数据库设计",
        description="负责实体关系、表结构、索引、约束、迁移和数据一致性。",
        tags=("database", "schema", "sql", "migration", "数据模型", "表结构", "索引"),
        prompt=(
            "你是数据库设计 Agent。你负责实体关系、表结构、字段约束、索引、迁移策略、"
            "审计字段和数据一致性。输出要能支撑 API 契约和业务状态流转。"
        ),
    ),
    SkillDefinition(
        id="code_reviewer",
        name="代码审查",
        description="负责审查、测试、安全、质量和回归风险。",
        tags=("review", "test", "security", "quality", "审查", "测试", "安全"),
        prompt=(
            "你是代码审查 Agent。你优先发现 bug、回归风险、缺失测试、"
            "安全隐患和架构不一致，输出清晰可执行的审查意见。"
        ),
    ),
    SkillDefinition(
        id="test_engineer",
        name="测试工程师",
        description="负责测试策略、用例设计、集成测试、回归测试和验收报告。",
        tags=("test", "qa", "e2e", "integration", "regression", "测试", "验收", "回归"),
        prompt=(
            "你是测试工程师 Agent。你负责制定测试策略、识别高风险路径、设计正常/异常/权限/"
            "并发用例，推动单元测试、集成测试、端到端测试和回归验证。输出应包含可执行测试清单。"
        ),
    ),
    SkillDefinition(
        id="technical_writer",
        name="技术文档",
        description="负责 PRD、接口文档、架构说明、用户指南和交接文档。",
        tags=("docs", "documentation", "prd", "handoff", "readme", "文档", "说明", "交接"),
        prompt=(
            "你是技术文档 Agent。你负责把产品、架构、接口、测试和交付信息整理成清晰文档。"
            "优先结构化输出，区分事实、假设、决策和待办，避免把未确认内容写成定论。"
        ),
    ),
    SkillDefinition(
        id="ux_designer",
        name="UX 设计",
        description="负责用户流程、信息架构、交互状态、可用性和界面验收口径。",
        tags=("ux", "ui", "interaction", "flow", "prototype", "交互", "用户体验", "流程"),
        prompt=(
            "你是 UX 设计 Agent。你负责用户流程、信息架构、页面状态、交互反馈、空状态/"
            "错误状态和可用性验收。你可以给前端 Agent 提供页面结构和交互规格。"
        ),
    ),
    SkillDefinition(
        id="workspace_editing",
        name="Workspace 编辑",
        description="负责在项目工作区中读写文件、生成 diff 和维护文件结构。",
        tags=("file", "diff", "workspace", "文件", "工作区"),
        prompt=(
            "你可以在项目 workspace 中读写文件。修改前理解现有结构，"
            "保持变更聚焦，并优先使用项目已有约定。"
        ),
    ),
    SkillDefinition(
        id="web_preview",
        name="Web 预览",
        description="负责 HTML/Vite/Web 预览相关产物和验证。",
        tags=("preview", "html", "vite", "web", "预览", "网页"),
        prompt=(
            "你关注 Web 产物可预览性。实现前端或静态页面时，注意项目启动、"
            "预览路径、构建输出和用户可验证的页面状态。"
        ),
    ),
    SkillDefinition(
        id="orchestrator_planner",
        name="调度器规划",
        description="只负责需求拆解、DAG 计划和 Agent 分配建议。",
        tags=("orchestrator", "dag", "plan", "assignment", "调度", "计划", "分配"),
        prompt=(
            "你是 AgentHub 的 Orchestrator Planner Agent。你的唯一职责是把用户需求拆解为"
            "plan-only DAG 调度计划，不直接改文件、不执行任务、不调用子 Agent。\n\n"
            "工作原则：\n"
            "1. 任务拆到模块/交付物级，不拆到创建文件、安装依赖、写函数这类代码步骤级。\n"
            "2. 每个任务必须同时保留 required_skills、assigned_agent_id/assigned_agent_name、assignment_reason。\n"
            "3. required_skills 用于说明任务需要什么能力；assigned_agent_id 用于推荐最终执行 Agent；"
            "assignment_reason 用于解释为什么这么分。\n"
            "4. depends_on 必须引用已有 task_id，整体必须是 DAG。\n"
            "5. status 固定为 draft；execution_policy.mode 固定为 plan_only；"
            "requires_approval_before_execution 固定为 true。\n"
            "6. 如果当前上下文没有候选 Agent 列表，可以把 assigned_agent_id 设为 null，"
            "assigned_agent_name 设为 null，并在 assignment_reason 中写明需要后续匹配。\n\n"
            "输出要求：默认只输出一个 JSON 对象，不要写 Markdown 解释。JSON 最小结构如下：\n"
            "{\n"
            "  \"plan_id\": \"plan_xxx\",\n"
            "  \"status\": \"draft\",\n"
            "  \"execution_policy\": {\n"
            "    \"mode\": \"plan_only\",\n"
            "    \"requires_approval_before_execution\": true\n"
            "  },\n"
            "  \"tasks\": [\n"
            "    {\n"
            "      \"task_id\": \"T1\",\n"
            "      \"title\": \"任务标题\",\n"
            "      \"goal\": \"任务目标\",\n"
            "      \"required_skills\": [\"architecture\"],\n"
            "      \"assigned_agent_id\": null,\n"
            "      \"assigned_agent_name\": null,\n"
            "      \"assignment_reason\": \"为什么这样分配\",\n"
            "      \"depends_on\": [],\n"
            "      \"expected_outputs\": [\"document\"],\n"
            "      \"acceptance_criteria\": [\"验收标准\"],\n"
            "      \"needs_approval\": true,\n"
            "      \"is_blocking\": true\n"
            "    }\n"
            "  ],\n"
            "  \"execution_strategy\": {\n"
            "    \"parallelizable_groups\": [[\"T2\", \"T3\"]],\n"
            "    \"critical_path\": [\"T1\"]\n"
            "  }\n"
            "}"
        ),
    ),
)


class SkillRegistry:
    def __init__(
        self,
        skills: tuple[SkillDefinition, ...] = BUILTIN_SKILLS,
        roots: list[str | Path] | None = None,
    ):
        self._skills = {skill.id: skill for skill in skills}
        for skill in load_filesystem_skills(roots):
            # Filesystem skills extend the pool. If a user intentionally creates
            # the same id as a built-in skill, the local skill wins.
            self._skills[skill.id] = skill

    def list(self) -> list[SkillDefinition]:
        return sorted(self._skills.values(), key=lambda skill: (skill.source != "builtin", skill.name.lower()))

    def get(self, skill_id: str | None) -> SkillDefinition | None:
        if not skill_id:
            return None
        return self._skills.get(skill_id)

    def tags_for(self, skill_ids: list[str]) -> set[str]:
        tags: set[str] = set()
        for skill_id in skill_ids:
            skill = self.get(skill_id)
            if skill:
                tags.update(skill.tags)
        return tags


def default_skill_roots() -> list[Path]:
    configured = settings.agenthub_skill_roots or os.environ.get("AGENTHUB_SKILL_ROOTS", "")
    roots: list[Path] = []
    for item in re.split(r"[;,]", configured):
        value = item.strip().strip('"')
        if value:
            roots.append(_resolve_skill_root(value))
    if not roots:
        roots.append(Path.home() / ".agents" / "skills")
    return roots


def load_filesystem_skills(roots: list[str | Path] | None = None) -> list[SkillDefinition]:
    skill_roots = [_resolve_skill_root(root) for root in roots] if roots is not None else default_skill_roots()
    skills: list[SkillDefinition] = []
    for root in skill_roots:
        if not root.exists() or not root.is_dir():
            continue
        for skill_dir in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name.lower()):
            skill = _load_skill_dir(skill_dir)
            if skill:
                skills.append(skill)
    return skills


def _resolve_skill_root(root: str | Path) -> Path:
    path = Path(root).expanduser()
    if path.is_absolute() or path.exists():
        return path
    backend_relative = BACKEND_ROOT / path
    return backend_relative if backend_relative.exists() else path


def _load_skill_dir(skill_dir: Path) -> SkillDefinition | None:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists() or not skill_file.is_file():
        return None
    try:
        raw = skill_file.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raw = skill_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    metadata, body = _split_frontmatter(raw)
    skill_id = _normalize_id(metadata.get("name") or skill_dir.name)
    if not skill_id:
        return None
    description = metadata.get("description") or _first_non_empty_line(body) or f"Local skill: {skill_id}"
    name = metadata.get("name") or skill_id
    tags = _derive_tags(skill_id, name, metadata.get("tags", ""))
    prompt = body.strip() or raw.strip()
    return SkillDefinition(
        id=skill_id,
        name=name,
        description=description.strip(),
        tags=tags,
        prompt=prompt,
        source="filesystem",
        path=str(skill_file),
    )


def _split_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---"):
        return {}, raw
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw
    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}, raw

    metadata: dict[str, str] = {}
    for line in lines[1:end_index]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip().lower()] = value.strip().strip('"').strip("'")
    body = "\n".join(lines[end_index + 1 :])
    return metadata, body


def _normalize_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower())
    return normalized.strip("-_")


def _derive_tags(skill_id: str, name: str, raw_tags: str) -> tuple[str, ...]:
    tags: list[str] = []
    if raw_tags:
        cleaned = raw_tags.strip().strip("[]")
        tags.extend(part.strip().strip('"').strip("'") for part in re.split(r"[,，]", cleaned) if part.strip())
    tags.extend(part for part in re.split(r"[-_\s]+", skill_id) if part)
    tags.extend(part.lower() for part in re.split(r"[-_\s]+", name) if part and part.isascii())
    deduped: list[str] = []
    for tag in tags:
        if tag and tag not in deduped:
            deduped.append(tag)
    return tuple(deduped)


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip("# \t")
        if stripped:
            return stripped[:160]
    return ""
