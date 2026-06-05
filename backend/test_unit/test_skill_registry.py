import json

from app.domain.skill_registry import SkillRegistry
from app.models import AgentConfig
from app.services.cli_agent_service import CliAgentService


FIXTURE_SKILL_ROOT = "test_fixtures/skills"


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
        agent_type="cli_wrapper",
        cli_tool="custom",
        executable="echo",
        init_args="[]",
        env_vars="{}",
        primary_skill="local-fixture-skill",
        auxiliary_skills=json.dumps(["workspace_editing"], ensure_ascii=False),
        context_policy="workspace_coding",
    )
    service = CliAgentService()
    service._skills = SkillRegistry(roots=[FIXTURE_SKILL_ROOT])

    prompt = service._assemble_system_prompt(agent, agent.system_prompt)

    assert "[Primary Skill: local-fixture-skill]" in prompt
    assert "Use fixture skill instructions." in prompt
    assert "[Auxiliary Skill: workspace_editing]" in prompt
    assert "Prefer small focused changes." in prompt
    assert "[Context Policy: workspace_coding]" in prompt
