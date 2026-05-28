"""ContextManager 单元测试 —— 覆盖 token 估算 + prompt 组装 + pin 优先级 + FIFO 截断。"""
from app.domain.context_manager import ContextManager, PromptAssemblyInput


def make_msgs(*contents):
    return [{"role": "user", "content": c, "id": str(i)} for i, c in enumerate(contents)]


class TestEstimateTokens:
    def test_empty_list(self):
        cm = ContextManager()
        assert cm.estimate_tokens([]) == 0

    def test_single_message(self):
        cm = ContextManager()
        tokens = cm.estimate_tokens([{"role": "user", "content": "你好世界"}])
        assert tokens > 0

    def test_multiple_messages(self):
        cm = ContextManager()
        msgs = make_msgs("a" * 100, "b" * 200)
        tokens = cm.estimate_tokens(msgs)
        assert tokens > 0


class TestAssemble:
    def test_empty_messages_returns_system_only(self):
        cm = ContextManager()
        result = cm.assemble(PromptAssemblyInput(
            session_id="s1", system_prompt="你是助手", messages=[],
            max_tokens=10000,
        ))
        assert len(result.assembled_messages) == 1
        assert result.assembled_messages[0]["role"] == "system"

    def test_normal_messages_all_included(self):
        cm = ContextManager()
        msgs = make_msgs("hi", "hello")
        result = cm.assemble(PromptAssemblyInput(
            session_id="s1", system_prompt="sys", messages=msgs,
            max_tokens=100000,
        ))
        assert len(result.assembled_messages) == 3  # system + 2 messages
        assert not result.truncated

    def test_truncation_when_exceeding_budget(self):
        cm = ContextManager()
        msgs = make_msgs("x" * 10000)
        result = cm.assemble(PromptAssemblyInput(
            session_id="s1", system_prompt="sys", messages=msgs,
            max_tokens=100, reserve_tokens=0,
        ))
        assert result.truncated

    def test_pinned_messages_included(self):
        cm = ContextManager()
        msgs = [
            {"role": "user", "content": "normal1", "id": "1"},
            {"role": "user", "content": "important", "id": "2"},
            {"role": "user", "content": "normal2", "id": "3"},
        ]
        result = cm.assemble(PromptAssemblyInput(
            session_id="s1", system_prompt="sys", messages=msgs,
            pinned_message_ids=["2"], max_tokens=100000,
        ))
        assert "2" in result.pinned_included

    def test_pin_budget_limit(self):
        cm = ContextManager()
        msgs = [{"role": "user", "content": "x" * 5000, "id": str(i)} for i in range(10)]
        pin_ids = [str(i) for i in range(10)]
        result = cm.assemble(PromptAssemblyInput(
            session_id="s1", system_prompt="sys", messages=msgs,
            pinned_message_ids=pin_ids, max_tokens=10000, reserve_tokens=1000,
        ))
        # 不是所有 pin 都能放进去（token 预算有限）
        assert len(result.pinned_included) < 10


class TestEdgeCases:
    def test_zero_max_tokens(self):
        cm = ContextManager()
        result = cm.assemble(PromptAssemblyInput(
            session_id="s1", system_prompt="sys", messages=make_msgs("data"),
            max_tokens=0, reserve_tokens=0,
        ))
        assert result.truncated

    def test_very_long_content_estimation(self):
        cm = ContextManager()
        tokens = cm.estimate_tokens([{"role": "user", "content": "中" * 10000}])
        assert tokens > 0
