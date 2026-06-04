"""测试 planner 模板的 report_skeleton 字段。

RED 阶段 (Wave 1): 这些测试预期会失败，因为模板尚未包含 report_skeleton 字段。
将在 Wave 3 添加 report_skeleton 后变为 GREEN。

已知问题:
- 3 个模板 JSON 格式损坏: tpl_standard_analysis, tpl_breakeven_recovery, tpl_weekly_screening
  （Wave 3 Task 9 修复）
"""

import json
import glob
import os
import pytest

# ── 路径配置 ──────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(_BASE_DIR, "tradingagents", "templates")
TEMPLATE_PATTERN = os.path.join(TEMPLATES_DIR, "tpl_*.json")
EXPECTED_NUM_TEMPLATES = 6

# ── 辅助函数 ──────────────────────────────────────────────────────────────


def _all_template_paths():
    """返回所有 6 个 tpl_*.json 的绝对路径列表（按文件名排序）。"""
    return sorted(glob.glob(TEMPLATE_PATTERN))


def _template_ids():
    """从文件名推断 template_id（不含扩展名）。"""
    for path in _all_template_paths():
        yield os.path.splitext(os.path.basename(path))[0]


# ── 测试用例 ──────────────────────────────────────────────────────────────


class TestReportSkeleton:
    """TDD RED 阶段：验证所有模板和代码路径需要 report_skeleton。"""

    def test_all_templates_have_report_skeleton(self):
        """每个 tpl_*.json 必须包含 'report_skeleton' 键——RED 阶段必然失败。

        当前没有任何模板包含 report_skeleton，因此本测试一定会失败。
        另外已知 3 个模板 JSON 格式损坏（Wave 3 Task 9 修复）。
        """
        paths = _all_template_paths()
        assert len(paths) == EXPECTED_NUM_TEMPLATES, (
            f"找到 {len(paths)} 个模板，期望 {EXPECTED_NUM_TEMPLATES} 个"
        )

        for path in paths:
            name = os.path.basename(path)
            try:
                with open(path, encoding="utf-8") as f:
                    tpl = json.load(f)
            except json.JSONDecodeError as e:
                # 测试因 JSON 解析失败而 RED
                pytest.fail(
                    f"{name} JSON 解析失败（已知损坏，Wave 3 Task 9 修复）: {e}"
                )

            # 核心断言——此句在 RED 阶段必然失败
            assert "report_skeleton" in tpl, (
                f"{name} 缺少 'report_skeleton' 字段"
            )

    def test_report_skeleton_has_required_structure(self):
        """验证 report_skeleton 的结构：每个角色必须有 required_sections 和 section_order。

        当模板尚未包含 report_skeleton 时（RED 阶段），本测试静默通过。
        当模板开始添加 report_skeleton 后（GREEN 阶段），本测试验证结构完整性。
        """
        for path in _all_template_paths():
            name = os.path.basename(path)
            try:
                with open(path, encoding="utf-8") as f:
                    tpl = json.load(f)
            except json.JSONDecodeError:
                continue  # 跳过已知损坏的 JSON

            skel = tpl.get("report_skeleton")
            if skel is None:
                continue  # RED 阶段尚未存在 report_skeleton，跳过

            # 验证结构：report_skeleton 必须是 dict，key 为角色名
            assert isinstance(skel, dict), (
                f"{name}: report_skeleton 必须是 dict，"
                f"但实际为 {type(skel).__name__}"
            )
            assert len(skel) > 0, (
                f"{name}: report_skeleton 不能为空 dict"
            )

            for role, structure in skel.items():
                assert isinstance(structure, dict), (
                    f"{name}: report_skeleton['{role}'] 必须是 dict，"
                    f"但实际为 {type(structure).__name__}"
                )
                assert "required_sections" in structure, (
                    f"{name}: report_skeleton['{role}'] 缺少 'required_sections'"
                )
                assert isinstance(structure["required_sections"], list), (
                    f"{name}: report_skeleton['{role}']['required_sections'] 必须是 list，"
                    f"但实际为 {type(structure['required_sections']).__name__}"
                )
                assert "section_order" in structure, (
                    f"{name}: report_skeleton['{role}'] 缺少 'section_order'"
                )
                assert isinstance(structure["section_order"], list), (
                    f"{name}: report_skeleton['{role}']['section_order'] 必须是 list，"
                    f"但实际为 {type(structure['section_order']).__name__}"
                )

    def test_llm_full_mode_has_default_skeleton(self):
        """llm_full 或 llm_fallback 模式生成的计划必须包含默认 report_skeleton。

        当 _plan_internal 无法匹配任何模板（no_match）时，
        会调用 _generate_from_llm -> _fallback_plan（因 llm=None）。
        此路径目前不添加 report_skeleton——RED 阶段必然失败。
        """
        from tradingagents.planner.llm_planner import LLMPlanner
        from tradingagents.planner.schemas import Trigger, Context

        # 使用无 LLM 的 planner，确保走 _fallback_plan 路径
        planner = LLMPlanner(kb=None, llm=None)

        # 使用不可能匹配任何模板的随机消息
        trigger = Trigger(
            type="user",
            task="分析",
            message="__THIS_IS_A_UNIQUE_TEST_MESSAGE_THAT_WONT_MATCH_ANY_TEMPLATE__",
        )
        context = Context(ticker="600519", industry="白酒")

        plan = planner._plan_internal(trigger, context)
        mode = plan.get("_generation_mode", "unknown")

        # 关键断言——RED 阶段必然失败
        assert "report_skeleton" in plan, (
            f"'{mode}' 模式生成的计划缺少 'report_skeleton'；"
            f"现有 keys: {list(plan.keys())}"
        )

        assert isinstance(plan["report_skeleton"], dict), (
            "report_skeleton 必须是 dict 类型"
        )

    def test_json_valid_in_all_templates(self):
        """所有 6 个模板文件必须能解析为合法 JSON。

        已知 3 个模板有 JSON 损坏问题：
        - tpl_standard_analysis.json
        - tpl_breakeven_recovery.json
        - tpl_weekly_screening.json
        """
        errors = []
        for path in _all_template_paths():
            with open(path, encoding="utf-8") as f:
                content = f.read()
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                errors.append(f"  {os.path.basename(path)}: {e}")

        if errors:
            pytest.fail(
                f"以下 {len(errors)}/{EXPECTED_NUM_TEMPLATES} 个模板 JSON 解析失败：\n"
                + "\n".join(errors)
            )

    def test_template_matcher_score_has_report_skeleton_bonus(self):
        """template_matcher._score_template 应为 report_skeleton 添加权重加分。

        未来规划：_score_template 检测到模板有 report_skeleton 时加 +0.1 分。
        本测试验证当前方法签名和返回类型是否正确，并作为行为的文档参考。
        """
        from tradingagents.planner.template_matcher import TemplateMatcher

        matcher = TemplateMatcher()

        # 验证 _score_template 存在且可调用
        assert hasattr(matcher, "_score_template"), (
            "TemplateMatcher 缺少 _score_template 方法"
        )

        # 构造一个最小模板和特征，验证调用正常
        sample_template = {
            "template_id": "test",
            "match_patterns": {"keywords": ["测试"]},
            "use_count": 0,
            "success_rate": 0.5,
        }
        sample_features = {
            "message_text": "这是一条测试消息",
            "has_holdings": False,
            "has_watchlist": False,
            "has_ticker": True,
            "is_scheduled_morning": False,
            "is_scheduled_midday": False,
            "is_scheduled_closing": False,
            "is_scheduled_weekly": False,
            "industry": "",
        }

        # 验证无 report_skeleton 时的行为
        score_without = matcher._score_template(sample_template, sample_features)
        assert isinstance(score_without, float), (
            f"_score_template 应返回 float，实际返回 {type(score_without).__name__}"
        )
        assert 0.0 <= score_without <= 1.0, (
            f"_score_template 返回值应在 [0.0, 1.0] 范围内，实际为 {score_without}"
        )

        # 验证有 report_skeleton 时的行为（该功能尚未实现——非 TDD 断言，仅为文档）
        # TODO(Wave 3): 当 _score_template 为 report_skeleton 加分后，应断言
        #   score_with > score_without
