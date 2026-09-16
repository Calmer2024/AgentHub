import asyncio

import pytest

from app.services.orchestrator_execution import OrchestratorExecutionRegistry, cli_runtime_registry


def _plan() -> dict:
    return {
        "plan_id": "plan_unit",
        "tasks": [
            {
                "task_id": "T1",
                "title": "上游",
                "assigned_agent_id": "worker_a",
                "assignment_reason": "负责上游",
                "depends_on": [],
                "max_attempts": 3,
            },
            {
                "task_id": "T2",
                "title": "下游",
                "assigned_agent_id": "worker_b",
                "assignment_reason": "负责下游",
                "depends_on": ["T1"],
                "max_attempts": 3,
            },
        ],
    }


class RecordingRunner:
    def __init__(self):
        self.calls: list[tuple[str, str | None]] = []

    async def run(self, task, execution, upstream_results):
        self.calls.append((task["taskId"], task.get("retryFeedback")))
        return f"{task['taskId']} 第 {int(task.get('attempt') or 0) + 1} 次提交"


class RetryOnceReviewer:
    def __init__(self):
        self.t1_reviews = 0

    async def review(self, execution, phase, tasks):
        decisions = []
        for task in tasks:
            if task["taskId"] == "T1":
                self.t1_reviews += 1
                if self.t1_reviews == 1:
                    decisions.append({"taskId": "T1", "decision": "retry", "feedback": "补充验证证据"})
                    continue
            decisions.append({"taskId": task["taskId"], "decision": "accepted", "feedback": "通过"})
        return {"phaseSummary": "验收完成", "tasks": decisions}


def _without_persistence(registry: OrchestratorExecutionRegistry) -> None:
    async def no_message(*args, **kwargs):
        return "test_message"

    registry._persist_task_result = no_message
    registry._persist_phase_review = no_message
    registry._persist_completion_summary = no_message
    registry._persist_execution_snapshot = no_message


@pytest.mark.asyncio
async def test_retry_keeps_static_phase_and_releases_downstream_after_acceptance():
    runner = RecordingRunner()
    reviewer = RetryOnceReviewer()
    registry = OrchestratorExecutionRegistry(task_runner=runner)
    _without_persistence(registry)
    execution = registry.create_execution(
        session_id="session",
        plan=_plan(),
        active_agent_ids={"worker_a", "worker_b"},
        task_runner=runner,
        phase_reviewer=reviewer,
        auto_start=False,
    )
    registry._executions[execution["executionId"]]["runnerType"] = "mock"
    await registry._run_scheduler(execution["executionId"])
    completed = registry.get_execution(execution["executionId"])
    assert completed is not None
    assert completed["status"] == "completed"
    assert [(task["phase"], task["attempt"]) for task in completed["tasks"]] == [(0, 2), (1, 1)]
    assert runner.calls == [("T1", None), ("T1", "补充验证证据"), ("T2", None)]


@pytest.mark.asyncio
async def test_user_revision_resets_target_and_transitive_descendants():
    registry = OrchestratorExecutionRegistry()
    _without_persistence(registry)
    execution = registry.create_execution(
        session_id="session",
        plan=_plan(),
        active_agent_ids={"worker_a", "worker_b"},
        auto_start=False,
    )
    stored = registry._executions[execution["executionId"]]
    stored["status"] = "completed"
    for task in stored["tasks"]:
        task.update({
            "status": "accepted",
            "attempt": 1,
            "summary": "旧结果",
            "completedAt": "now",
            "attempts": [{"attempt": 1, "status": "accepted", "summary": "旧结果"}],
        })
    registry.start_execution = lambda execution_id: None

    revised = await registry.request_worker_revision(
        session_id="session",
        agent_id="worker_a",
        feedback="请调整实现",
    )
    assert revised is not None
    assert revised["status"] == "running"
    assert [task["status"] for task in revised["tasks"]] == ["pending", "pending"]
    assert revised["tasks"][0]["retryFeedback"] == "请调整实现"
    assert "上游任务 T1" in revised["tasks"][1]["retryFeedback"]
    assert [task["attempt"] for task in revised["tasks"]] == [1, 1]
    assert [task["attempts"][-1]["status"] for task in revised["tasks"]] == [
        "superseded",
        "superseded",
    ]
    assert all(task["attempts"][-1]["summary"] == "旧结果" for task in revised["tasks"])


class ConcurrencyRunner:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.calls: list[str] = []

    async def run(self, task, execution, upstream_results):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.calls.append(task["taskId"])
        await asyncio.sleep(0)
        self.active -= 1
        return f"{task['taskId']} 完成"


@pytest.mark.asyncio
async def test_same_agent_tasks_in_same_phase_run_serially():
    runner = ConcurrencyRunner()
    registry = OrchestratorExecutionRegistry(task_runner=runner)
    _without_persistence(registry)
    plan = {
        "plan_id": "same_agent",
        "tasks": [
            {"task_id": "T1", "title": "一", "goal": "完成一", "assigned_agent_id": "worker_a", "assignment_reason": "同一 Agent 串行执行", "depends_on": [], "acceptance_criteria": ["完成"]},
            {"task_id": "T2", "title": "二", "goal": "完成二", "assigned_agent_id": "worker_a", "assignment_reason": "同一 Agent 串行执行", "depends_on": [], "acceptance_criteria": ["完成"]},
        ],
    }
    execution = registry.create_execution(
        session_id="session",
        plan=plan,
        active_agent_ids={"worker_a"},
        task_runner=runner,
        auto_start=False,
    )
    registry._executions[execution["executionId"]]["runnerType"] = "mock"

    await registry._run_scheduler(execution["executionId"])

    completed = registry.get_execution(execution["executionId"])
    assert completed is not None
    assert completed["status"] == "completed"
    assert runner.calls == ["T1", "T2"]
    assert runner.max_active == 1
    assert [task["phase"] for task in completed["tasks"]] == [0, 0]


@pytest.mark.asyncio
async def test_running_revision_invalidates_current_scheduler_generation(monkeypatch):
    registry = OrchestratorExecutionRegistry()
    _without_persistence(registry)
    execution = registry.create_execution(
        session_id="session",
        plan=_plan(),
        active_agent_ids={"worker_a", "worker_b"},
        auto_start=False,
    )
    stored = registry._executions[execution["executionId"]]
    stored["status"] = "running"
    stored["tasks"][0]["status"] = "running"
    registry.start_execution = lambda execution_id: None
    terminated: list[str] = []

    async def terminate(session_id):
        terminated.append(session_id)
        return 1

    monkeypatch.setattr(cli_runtime_registry, "terminate_session", terminate)
    revised = await registry.request_worker_revision(
        session_id="session",
        agent_id="worker_a",
        feedback="运行中调整",
    )

    assert revised is not None
    assert revised["revisionGeneration"] == 1
    assert [task["status"] for task in revised["tasks"]] == ["pending", "pending"]
    assert terminated == ["session"]
