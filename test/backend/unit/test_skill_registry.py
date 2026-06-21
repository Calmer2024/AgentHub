import json
from pathlib import Path

from app.domain.skill_registry import SkillRegistry
from app.models import AgentConfig
from app.services.cli_agent_service import CliAgentService


TEST_BACKEND_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SKILL_ROOT = str(TEST_BACKEND_ROOT / "fixtures" / "skills")


def test_skill_registry_loads_filesystem_skill():
    registry = SkillRegistry(roots=[FIXTURE_SKILL_ROOT])
    skill = registry.get("local-fixture-skill")

    assert skill is not None
    assert skill.source == "filesystem"
    assert skill.path and skill.path.endswith("SKILL.md")
    assert "Use fixture skill instructions" in skill.prompt
    assert "fixture" in skill.tags


def test_cli_agent_service_injects_filesystem_skill_prompts():
    agent = AgentConfig(
        id="agent-1",
        name="本机前端专家",
        description="",
        system_prompt="Prefer small focused changes.",
        rules="回答先给结论，再列风险。",
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable="echo",
        init_args="[]",
        env_vars="{}",
        primary_skill="local-fixture-skill",
        auxiliary_skills=json.dumps(["workspace_editing"], ensure_ascii=False),
        toolset=json.dumps(["local-fixture-skill", "workspace_editing"], ensure_ascii=False),
        context_policy="workspace_coding",
        avatar="preset:blue",
    )
    service = CliAgentService()
    service._skills = SkillRegistry(roots=[FIXTURE_SKILL_ROOT])

    prompt = service._assemble_system_prompt(agent, agent.system_prompt)

    assert "[Local Tool: local-fixture-skill]" in prompt
    assert "Use fixture skill instructions." in prompt
    assert "[Agent Toolset]\nworkspace_editing" in prompt
    assert "[Language Policy]" in prompt
    assert "用户用中文提出需求时" in prompt
    assert "[Agent System Prompt]\nPrefer small focused changes." in prompt
    assert "[Agent Rules]\n回答先给结论，再列风险。" in prompt
    assert "[Context Policy: workspace_coding]" in prompt
    assert prompt.index("[AgentHub Agent Profile]") < prompt.index("[Language Policy]")
    assert prompt.index("[Language Policy]") < prompt.index("[Agent System Prompt]")
    assert prompt.index("[Agent System Prompt]") < prompt.index("[Agent Rules]")
    assert prompt.index("[Agent Rules]") < prompt.index("[Local Tool: local-fixture-skill]")
    assert prompt.index("[Local Tool: local-fixture-skill]") < prompt.index("[Agent Toolset]")
