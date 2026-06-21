from app.domain.orchestrator_plan import (
    extract_json_object,
    normalize_plan,
    plan_to_collab_payload,
    validate_plan,
    visualize_mermaid,
)


def test_parse_normalize_validate_and_project_plan():
    raw = extract_json_object(
        """```json
        {
          "tasks": [
            {"task_id": "T1", "title": "设计数据模型", "required_skills": ["architect"], "depends_on": []},
            {"task_id": "T2", "title": "实现接口", "required_skills": ["backend"], "depends_on": ["T1"]}
          ]
        }
        ```"""
    )

    plan = normalize_plan(raw)
    validation = validate_plan(plan)
    tasks, dag = plan_to_collab_payload(plan)

    assert plan["status"] == "draft"
    assert validation["ok"] is True
    assert [task["name"] for task in tasks] == ["设计数据模型", "实现接口"]
    assert [phase["phase"] for phase in dag["phases"]] == [0, 1]
    assert "T1 --> T2" in visualize_mermaid(plan)


def test_extract_json_object_repairs_fenced_approve_action_with_cn_quotes():
    raw = '''```json
{
  "action": "approve_plan",
  "target_plan_id": "plan_home_assets_002",
  "reason": "用户明确回复"可以，执行"，表示对 draft plan plan_home_assets_002 无修改意见，批准开始执行"
}
```'''

    data = extract_json_object(raw)

    assert data["action"] == "approve_plan"
    assert data["target_plan_id"] == "plan_home_assets_002"
    assert "可以，执行" in data["reason"]


def test_validate_plan_rejects_missing_dependency_and_cycle():
    plan = normalize_plan({
        "tasks": [
            {"task_id": "T1", "depends_on": ["T2"], "required_skills": ["a"]},
            {"task_id": "T2", "depends_on": ["T1"], "required_skills": ["b"]},
            {"task_id": "T3", "depends_on": ["T9"], "required_skills": ["c"]},
        ],
    })

    validation = validate_plan(plan)

    assert validation["ok"] is False
    assert any("不存在" in error for error in validation["errors"])
    assert any("循环依赖" in error for error in validation["errors"])
