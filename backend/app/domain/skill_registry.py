from __future__ import annotations

"""本机 Skill 注册表。

AgentHub 不再提供产品内置 Skill。这里仅扫描用户本机的 ``SKILL.md``，
并允许测试按需注入临时 SkillDefinition。
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
    source: str = "filesystem"
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


BUILTIN_SKILLS: tuple[SkillDefinition, ...] = ()


class SkillRegistry:
    def __init__(
        self,
        skills: tuple[SkillDefinition, ...] = BUILTIN_SKILLS,
        roots: list[str | Path] | None = None,
    ):
        self._skills = {skill.id: skill for skill in skills}
        for skill in load_filesystem_skills(roots):
            self._skills[skill.id] = skill

    def list(self) -> list[SkillDefinition]:
        return sorted(self._skills.values(), key=lambda skill: skill.name.lower())

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
    configured = os.environ.get("AGENTHUB_SKILL_ROOTS") or settings.agenthub_skill_roots
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
