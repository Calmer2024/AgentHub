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
            "你是 Orchestrator Planner Agent。你只产出计划和 DAG，不直接改文件。"
            "每个任务必须包含 required_skills，可以推荐 assigned_agent_id，并解释分配原因。"
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
            roots.append(Path(value).expanduser())
    if not roots:
        roots.append(Path.home() / ".agents" / "skills")
    return roots


def load_filesystem_skills(roots: list[str | Path] | None = None) -> list[SkillDefinition]:
    skill_roots = [Path(root).expanduser() for root in roots] if roots is not None else default_skill_roots()
    skills: list[SkillDefinition] = []
    for root in skill_roots:
        if not root.exists() or not root.is_dir():
            continue
        for skill_dir in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name.lower()):
            skill = _load_skill_dir(skill_dir)
            if skill:
                skills.append(skill)
    return skills


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
