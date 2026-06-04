"""Orchestrator dry-run debugger.

This module is intentionally outside ``OrchestratorV2.run`` so the production
pipeline stays stable while debug tooling can expose richer intermediate state.
"""

from dataclasses import dataclass, field

from ..models import AgentConfig
from .agent_selector import AgentSelector, ScoredAgent
from .context_manager import ContextManager, PromptAssemblyInput
from .execution_planner import AgentCall, DAGPhase, ExecutionPlanner
from .intent_analyzer import IntentAnalysis, IntentAnalyzer
from .plan_summary import build_plan_summary
from .task_decomposer import TaskDecomposer


@dataclass
class OrchestratorDebugRequest:
    """Input for an Orchestrator dry-run."""

    content: str
    agents: list[AgentConfig]
    mentions: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    session_id: str = "debug-session"
    system_prompt: str = ""
    context_budget: int = 100_000
    reserve_tokens: int = 4096
    supplemental: bool = False


class OrchestratorDebugRunner:
    """Runs the scheduling pipeline and returns all inspectable decisions."""

    def __init__(self, context_manager: ContextManager | None = None):
        self.context_manager = context_manager
        self.intent_analyzer = IntentAnalyzer()
        self.agent_selector = AgentSelector()
        self.task_decomposer = TaskDecomposer()
        self.execution_planner = ExecutionPlanner(self.task_decomposer)

    def run(self, req: OrchestratorDebugRequest) -> dict:
        """Run a dry scheduling pass without invoking any agent adapter."""
        intent = self.intent_analyzer.analyze(req.content)
        assembled, truncated = self._assemble_context(req)
        scored = self.agent_selector.select(
            required_tags=intent.required_tags,
            candidates=req.agents,
            mentions=req.mentions,
        )
        selected_agents = self._selected_agents(scored, req.supplemental, req.mentions)
        plan = self.execution_planner.plan(
            agents=selected_agents,
            content=req.content,
            messages=assembled,
            supplemental=req.supplemental,
        )
        plan_summary = build_plan_summary(plan.mode, plan.calls, plan.dag_phases)

        return {
            "input": {
                "content": req.content,
                "mentions": list(req.mentions),
                "supplemental": req.supplemental,
                "agentCount": len(req.agents),
            },
            "intent": self._intent_payload(intent),
            "context": {
                "messageCount": len(assembled),
                "assembledMessages": assembled,
                "truncated": truncated,
                "estimatedTokens": sum(len(m.get("content", "")) for m in assembled) // 3,
            },
            "agentSelection": [self._scored_agent_payload(s) for s in scored],
            "selectedAgents": [self._agent_payload(a) for a in selected_agents],
            "executionPlan": {
                "mode": plan.mode,
                "planSummary": plan_summary,
                "decomposerUsed": plan.decomposer_used,
                "chainAutoTriggered": plan.chain_auto_triggered,
                "calls": [self._call_payload(c) for c in plan.calls],
                "dagPhases": [self._phase_payload(p) for p in plan.dag_phases],
            },
            "visualization": {
                "mermaid": self._mermaid(plan.dag_phases, plan.calls, plan.mode),
            },
        }

    def _assemble_context(self, req: OrchestratorDebugRequest) -> tuple[list[dict], bool]:
        messages = list(req.messages) if req.messages else [
            {"role": "user", "content": req.content},
        ]
        if not self.context_manager:
            if req.system_prompt:
                messages.insert(0, {"role": "system", "content": req.system_prompt})
            return messages, False

        result = self.context_manager.assemble(PromptAssemblyInput(
            session_id=req.session_id,
            system_prompt=req.system_prompt,
            messages=messages,
            pinned_message_ids=[],
            max_tokens=req.context_budget,
            reserve_tokens=req.reserve_tokens,
        ))
        return result.assembled_messages, result.truncated

    @staticmethod
    def _selected_agents(
        scored: list[ScoredAgent], supplemental: bool, mentions: list[str],
    ) -> list[AgentConfig]:
        if supplemental and not mentions:
            matched = [s for s in scored if s.reason == "tag_match"]
            return [s.agent for s in matched[:2]]
        return [s.agent for s in scored]

    @staticmethod
    def _intent_payload(intent: IntentAnalysis) -> dict:
        return {
            "type": intent.intent,
            "requiredTags": list(intent.required_tags),
            "confidence": intent.confidence,
            "evidence": intent.evidence,
        }

    @staticmethod
    def _agent_payload(agent: AgentConfig) -> dict:
        return {
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "provider": agent.provider,
            "model": agent.model,
        }

    def _scored_agent_payload(self, scored: ScoredAgent) -> dict:
        return {
            **self._agent_payload(scored.agent),
            "score": scored.score,
            "matchTags": list(scored.match_tags),
            "reason": scored.reason,
        }

    def _call_payload(self, call: AgentCall) -> dict:
        return {
            "agent": self._agent_payload(call.agent),
            "task": call.task,
            "role": call.role,
            "phase": call.phase,
            "dependsOn": list(call.depends_on),
            "rolePromptOverride": call.role_prompt_override,
            "inputMessageCount": len(call.input_messages),
        }

    def _phase_payload(self, phase: DAGPhase) -> dict:
        return {
            "phase": phase.phase,
            "mode": phase.mode,
            "calls": [self._call_payload(c) for c in phase.calls],
        }

    def _mermaid(self, phases: list[DAGPhase], calls: list[AgentCall], mode: str) -> str:
        if not calls:
            return "flowchart LR\n  empty[No agent selected]"

        lines = ["flowchart LR"]
        by_task = {c.task: c for c in calls}
        for call in calls:
            node_id = self._node_id(call)
            label = f"P{call.phase} · {call.task}\\n@{call.agent.name}\\n{call.role}"
            lines.append(f"  {node_id}[\"{label}\"]")

        has_edges = False
        for call in calls:
            for dep in call.depends_on:
                dep_call = by_task.get(dep)
                if dep_call:
                    lines.append(f"  {self._node_id(dep_call)} --> {self._node_id(call)}")
                    has_edges = True

        if not has_edges and mode in {"chain", "parallel"}:
            for prev, current in zip(calls, calls[1:]):
                arrow = "-->" if mode == "chain" else "-.-"
                lines.append(f"  {self._node_id(prev)} {arrow} {self._node_id(current)}")

        for phase in phases:
            ids = " ".join(self._node_id(c) for c in phase.calls)
            if ids:
                lines.append(f"  subgraph phase_{phase.phase}[Phase {phase.phase} · {phase.mode}]")
                for call in phase.calls:
                    lines.append(f"    {self._node_id(call)}")
                lines.append("  end")

        return "\n".join(lines)

    @staticmethod
    def _node_id(call: AgentCall) -> str:
        safe_task = "".join(ch if ch.isalnum() else "_" for ch in call.task)
        return f"p{call.phase}_{safe_task}"
