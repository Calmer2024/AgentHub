"""意图分析器 —— 关键词规则匹配 + 能力标签提取。

Domain 层纯逻辑，零框架依赖。
Phase 3: 关键词规则。Phase 4: 升级为 LLM-based 分类。
"""

from dataclasses import dataclass, field


# ===== 意图关键词 + 能力标签映射 =====

INTENT_RULES: dict[str, dict] = {
    "code_gen": {
        "keywords": ["写代码", "实现", "开发", "修复bug", "重构", "API", "前端", "后端",
                     "组件", "函数", "接口", "数据库", "写一个", "帮我写", "code", "bug",
                     "前后端", "登录页面", "注册", "CRUD", "写个", "实现一个", "代码"],
        "tags": ["开发", "代码", "编程"],
    },
    "research": {
        "keywords": ["调研", "分析", "比较", "推荐", "优缺点", "最新", "技术选型",
                     "什么是最好的", "有什么区别", "research", "对比", "调查"],
        "tags": ["调研", "分析", "比较"],
    },
    "design_ui": {
        "keywords": ["UI", "界面", "设计", "样式", "CSS", "布局", "颜色", "好看",
                     "美化", "页面", "组件样式", "UX", "交互", "视觉效果"],
        "tags": ["UI", "设计", "前端", "样式"],
    },
    "general_qa": {
        "keywords": [],
        "tags": ["通用"],
    },
}

# 从内容中提取技术标签的补充映射
TECH_TAG_PATTERNS: dict[str, list[str]] = {
    "React": ["react", "react.js", "jsx", "tsx", "hooks", "component"],
    "Python": ["python", "flask", "fastapi", "django", "后端"],
    "TypeScript": ["typescript", "ts", "类型", "type"],
    "API": ["api", "接口", "rest", "graphql", "端点"],
    "数据库": ["数据库", "database", "sql", "mysql", "postgresql", "sqlite"],
    "认证": ["登录", "注册", "auth", "jwt", "token", "权限", "认证"],
    "前端": ["前端", "frontend", "页面", "界面", "组件"],
    "后端": ["后端", "backend", "服务端", "server"],
    "测试": ["测试", "test", "单元测试", "集成测试"],
    "部署": ["部署", "deploy", "docker", "ci/cd", "发布"],
    "安全": ["安全", "security", "加密", "xss", "csrf"],
    "审查": ["审查", "评审", "review", "reviewer"],
    "性能": ["性能", "performance", "优化", "缓存", "cache"],
    "架构": ["架构", "architecture", "设计模式", "微服务"],
    "算法": ["算法", "algorithm", "数据结构", "复杂度"],
}


@dataclass
class IntentAnalysis:
    """意图分析结果。"""
    intent: str = "general_qa"      # "code_gen" | "research" | "design_ui" | "general_qa"
    required_tags: list[str] = field(default_factory=list)  # 能力需求标签
    confidence: float = 0.3         # 关键词匹配 = 1.0, 降级 = 0.3
    evidence: str = ""              # 匹配到的关键词，用于调试


class IntentAnalyzer:
    """意图分析器 —— 关键词规则匹配，输出意图类型 + 能力需求标签。

    Phase 3: 基于 INTENT_RULES 的规则匹配。
    Phase 4: 可替换为 LLM-based 实现（轻量模型做意图分类）。

    用法:
        analyzer = IntentAnalyzer()
        result = analyzer.analyze("帮我写一个 React 登录组件")
        # → IntentAnalysis(intent="code_gen", tags=["React", "认证", "前端"], ...)
    """

    def analyze(self, content: str) -> IntentAnalysis:
        """分析用户消息，返回意图 + 能力标签。"""
        if not content or not content.strip():
            return IntentAnalysis(intent="general_qa", required_tags=[], confidence=0.0,
                                  evidence="empty content")

        content_lower = content.lower()

        # Step 1: 检测意图类型
        intent = "general_qa"
        matched_kw = ""
        for intent_name, rules in INTENT_RULES.items():
            if intent_name == "general_qa":
                continue
            for kw in rules["keywords"]:
                if kw.lower() in content_lower:
                    intent = intent_name
                    matched_kw = kw
                    break
            if intent != "general_qa":
                break

        # Step 2: 提取能力标签
        tags = self._extract_tags(content_lower, intent)

        # Step 3: 计算置信度
        confidence = 1.0 if intent != "general_qa" else 0.3

        return IntentAnalysis(
            intent=intent,
            required_tags=tags,
            confidence=confidence,
            evidence=f"matched keyword: '{matched_kw}'" if matched_kw else "fallback",
        )

    def _extract_tags(self, content_lower: str, intent: str) -> list[str]:
        """从内容中提取技术能力标签。"""
        tags: list[str] = []

        # 基础意图标签
        base_tags = INTENT_RULES.get(intent, {}).get("tags", [])
        tags.extend(base_tags)

        # 技术关键词标签
        for tag_name, patterns in TECH_TAG_PATTERNS.items():
            for pat in patterns:
                if pat.lower() in content_lower:
                    if tag_name not in tags:
                        tags.append(tag_name)
                    break

        return tags
