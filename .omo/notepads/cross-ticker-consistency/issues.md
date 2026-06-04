# Cross-Ticker Consistency — 问题记录

## 启动状态
(无障碍)

## 已知坑点
- 3 个源模板 JSON 损坏 (tpl_standard_analysis, tpl_breakeven_recovery, tpl_weekly_screening)
- ReportRenderer 存在但 executor.py 未调用
- build_instrument_context() 注入点在 agent_utils.py:134

## 2026-06-04 — test_injection_contract.py 已创建 (RED)
- 文件: tests/test_injection_contract.py
- 5 个测试函数全部 RED 失败 (ModuleNotFoundError — injection_contract.py 不存在)
- 覆盖范围: anti_patterns 截断 ≤5、长行截断 ≤30 字符、空输入返回 ""、##INDUSTRY_GUIDE## 头部、correct_metrics 截断 ≤8

## 2026-06-04 — test_whitelist.py 已创建 (RED, 4 FAILED)
- 文件: `tests/test_whitelist.py` (201 行, 6 个测试)
- RED 失败: `test_whitelist_file_exists`, `test_whitelist_has_all_six_industries`,
  `test_agent_utils_injects_whitelist`, `test_whitelist_does_not_erase_anti_patterns`
- 回归通过: `test_missing_industry_no_exception`, `test_missing_industry_still_has_basic_context`
- **发现的问题**: `build_instrument_context(industry="banking")` 不触发 anti_patterns 注入
  - IndustryFramework.lookup("banking") 因为 keywords 全是中文（"银行"、"金融"……）而不匹配
  - 结果只输出 `**行业背景：** 该股票属于 banking 行业。` — 无框架内容
  - GREEN 实现 whitelist 集成时需要决定：用中文 industry 名 vs 扩展 lookup 支持英文 key
  - `test_whitelist_does_not_erase_anti_patterns` 已覆盖此边界情况
