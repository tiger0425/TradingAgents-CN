# 三层行业检测架构改进

## TL;DR

> **核心目标**: 在 TradingAgents 13-Agent 分析管线中注入行业感知，使 LLM 自动匹配正确的行业分析框架。解决"分析卡车制造商时用 SaaS 指标（续约率、LTV/CAC）"的框架错配问题。
>
> **产出**: IndustryClassifier 服务 → AgentState 行业字段 → Agent 提示词注入 → 运行时一致性校验
>
> **预估规模**: Medium
> **并行执行**: YES — 4 waves
> **关键路径**: Task 1 → 3 → 4 → 11 → 13 (行业字段必须最先建立)

---

## Context

### 原始需求
600418（江淮汽车，商用卡车制造商）被 deepseek-v4-flash 用 SaaS 行业框架分析：
- 输出指标：TOP100 客户续约率 99%、ACV 增长 34%、LTV/CAC 4.7 倍
- 这些全是 SaaS/科技公司指标，不是卡车制造商的指标
- 根因：LLM 默认套用 SaaS 模板分析任何标的

预期的三层改进：
- **L1 行业检测**：自动识别公司所属行业
- **L2 框架匹配**：根据行业注入正确的分析指标和提示词
- **L3 一致性校验**：分析完成后验证结果与行业是否匹配

### 访谈总结
**关键发现**:
- `get_industry(ticker)` 已存在（3-level fallback），已在 api_server.py 调用
- `Context.industry` 已存在，已流入 Planner 级别
- **核心 gap**: `Context.industry` 在 `executor.py:_build_init_state()` 处丢失 —— 从未进入 `AgentState`
- 13 个 Agent 的 system prompt 全部硬编码，无行业感知
- `build_instrument_context()` 仅提供 ticker 格式提示，不含行业
- 模板 `{industry}` 替换是死代码 —— DynamicGraphBuilder 忽略 context 字段
- `test_e2e_600418.py` 已有幻觉关键词检测基础
- `TemplateMatcher._extract_features()` 已包含 industry 但未被评分使用

**研究共识**:
- 行业注入应跟随 `state["market_context"]` 模式 —— 作为 AgentState 字段，Agent 自行读取
- 不应改动辩论 Agent（bull/bear/risk debators）的核心提示词 —— 它们消费分析师报告
- 一致性校验应从规则出发（扩展现有关键词检测），再升级到 LLM
- 行业框架定义应外部化（JSON 配置文件）

### Metis 评审
**已处理的 gap**:
- 行业分类体系规模：锁定为 5 个试点行业，非完整 taxonomy
- 框架映射范围：每个行业 5-8 个反模式规则 + 该行业的正确指标集
- 注入目标 Agent 数量：聚焦 7 个 Agent（4 analysts + trader + PM + research_mgr）
- 一致性检查策略：单次 quick_llm 调用，结构化 JSON 输出
- 空行业回退：industry="" 时行为完全不变

---

## Work Objectives

### 核心目标
构建三层行业感知架构：自动检测 A 股公司行业 → 将行业上下文注入分析 Agent → 运行时验证分析输出与行业的一致性。

### 具体产出
- `tradingagents/industry/classifier.py` — IndustryClassifier 服务
- `tradingagents/industry/frameworks.json` — 行业 → 框架/指标映射
- `tradingagents/industry/verifier.py` — 运行时一致性校验函数
- `tradingagents/agents/utils/agent_states.py` — 添加 industry 字段
- `tradingagents/graph/executor.py` — `_build_init_state()` 传递 industry
- `tradingagents/agents/utils/agent_utils.py` — `build_instrument_context()` 扩展
- 7 个 Agent 文件 — 行业提示词注入

### Definition of Done
- [ ] `pytest tests/test_industry_classifier.py tests/test_industry_e2e.py` → ALL PASS
- [ ] `pytest` 全部 857+ 测试保持通过，0 failures
- [ ] `test_e2e_600418.py::test_no_ai_hallucination` 继续通过
- [ ] 对 600418 的 curl 分析返回汽车行业指标（非 SaaS 指标）

### Must Have
- AgentState 包含 `industry` 字段，从 api_server 一路传递到所有 Agent
- `build_instrument_context()` 输出包含行业信息
- 4 个分析师 Agent 的系统提示词注入行业背景
- runtime 一致性校验函数，返回 `{consistent: bool, mismatches: [str]}`
- 当 industry="" 或 "未知" 时，所有 Agent 行为与当前完全一致

### Must NOT Have
- 不修改辩论 Agent（bull/bear/risk）的核心提示词结构
- 不修改 DynamicGraphBuilder、ConditionalLogic、图拓扑
- 不创建与 get_industry() 并行的第二分类器
- 不修改模板 JSON 文件
- 不增加新的数据源或工具
- Layer 3 不超过 1 次额外 quick_llm 调用
- 行业框架配置不硬编码在 Agent 文件中

---

## Verification Strategy

> **零人工干预** — 所有验证均由 Agent 执行。

### 测试决策
- **测试基础设施**: YES — pytest, 857 tests
- **自动化测试**: TDD（先写测试，再实现）
- **框架**: pytest
- **每任务遵循**: RED（失败测试）→ GREEN（最小实现）→ REFACTOR

### QA 策略
每任务包含 Agent 执行的 QA 场景。证据保存在 `.omo/evidence/`。

- 单元测试: `pytest tests/test_industry_*.py`
- E2E: `pytest tests/test_e2e_600418.py -v --run-slow`
- API 验证: `curl -X POST http://localhost:8000/analyze ...`

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1（立即可开始 - 基础 + 类型定义）:
├── Task 1: AgentState 添加 industry 字段 [quick]
├── Task 2: _build_init_state() 传递 industry [quick]
├── Task 3: IndustryClassifier 服务 [quick]
└── Task 4: 行业框架配置文件 [quick]

Wave 2（After Wave 1 - 注入核心，MAX PARALLEL）:
├── Task 5: build_instrument_context() 扩展 [quick]
├── Task 6: market_analyst 提示词注入 [quick]
├── Task 7: fundamentals_analyst 提示词注入 [quick]
├── Task 8: news_analyst 提示词注入 [quick]
├── Task 9: social_analyst 提示词注入 [quick]
└── Task 10: trader / PM / research_mgr 提示词注入 [quick]

Wave 3（After Wave 2 - 校验 + 集成）:
├── Task 11: Layer 3 一致性校验器 [unspecified-high]
├── Task 12: 行业注入 E2E 测试 [unspecified-high]
└── Task 13: 回归测试验证 [quick]

Wave FINAL（After ALL tasks - 4 并行审查）:
├── Task F1: Plan Compliance Audit (oracle)
├── Task F2: Code Quality Review (unspecified-high)
├── Task F3: Real Manual QA (unspecified-high)
└── Task F4: Scope Fidelity Check (deep)
```

关键路径: Task 1 → 3 → 4 → 11 → 13
并行加速: ~65% faster than sequential
最大并发: 6 (Wave 2)

---

## TODOs

- [x] 1. **IndustryClassifier 服务 + TDD 测试**

  **What to do**:
  - CREATE `tradingagents/industry/` package (__init__.py, classifier.py, frameworks.py, verifier.py)
  - CREATE `tradingagents/industry/config/` dir + `industry_frameworks.json`
  - CREATE `tests/test_industry_classifier.py`
  - IMPLEMENT `IndustryClassifier.classify(code)` → returns `IndustryResult` dataclass wrapping `get_industry()`
  - TDD: RED (failing test) → GREEN (minimal impl) → REFACTOR

  **Must NOT do**: Don't create parallel detection to `get_industry()`, don't implement full taxonomy (L1/L2/L3)

  **Agent**: `quick`, Skills: `[]` | **Parallel**: Wave 1 (with Task 2) | **Blocks**: Task 4

  **References**:
  - `tradingagents/dataflows/a_stock_data.py:1467` — `get_industry()` function
  - `tradingagents/planner/schemas.py:13-20` — `Context` dataclass pattern
  - Existing package patterns: `tradingagents/planner/`, `tradingagents/knowledge/`, `tradingagents/collector/`

  **Acceptance Criteria**:
  - [x] `IndustryClassifier().classify("600418")` returns `primary` containing "汽车" or "商用载货"
  - [x] `IndustryClassifier().classify("999999")` returns degraded result, no exception

  **QA Scenarios**:
  ```
  Scenario: classify 600418 → automotive industry
    Tool: Bash (pytest)
    Steps: python -c "from tradingagents.industry.classifier import IndustryClassifier; r = IndustryClassifier().classify('600418'); print(r.primary); assert '载货' in r.primary or '汽车' in r.primary"
    Expected: primary contains automotive term
    Evidence: .omo/evidence/task-1-classify-600418.txt

  Scenario: classify 999999 → graceful degradation
    Tool: Bash (pytest)
    Steps: python -c "from tradingagents.industry.classifier import IndustryClassifier; r = IndustryClassifier().classify('999999'); print('DEGRADED' if r.primary=='未知' else r.primary)"
    Expected: returns "未知" or empty, no crash
    Evidence: .omo/evidence/task-1-classify-unknown.txt
  ```

  **Commit**: `feat(industry): add IndustryClassifier service` — `tradingagents/industry/classifier.py`, `tests/test_industry_classifier.py`

- [x] 2. **行业框架配置文件 + frameworks.py**

  **What to do**:
  - CREATE `tradingagents/industry/config/industry_frameworks.json`
  - 5 industries (automotive, banking, tech, consumer, pharma), each with `correct_metrics`, `anti_patterns`, `peer_companies`
  - IMPLEMENT `IndustryFramework.lookup(industry_name)` → returns framework dict or None
  - Add fuzzy matching (e.g., "商用载货车" → automotive, "白酒" → consumer)

  **Must NOT do**: Don't build comprehensive taxonomy (all 800+ industries), don't hardcode metrics in agent code

  **Agent**: `quick`, Skills: `[]` | **Parallel**: Wave 1 (with Task 1) | **Blocks**: Task 5-9

  **References**:
  - `tradingagents/templates/tpl_standard_analysis.json` — task/agent structure
  - Automotive metrics: inventory turnover, capacity utilization, monthly sales YoY, NEV penetration
  - Banking metrics: NIM, NPL ratio, CAR, provision coverage ratio

  **Acceptance Criteria**:
  - [x] `IndustryFramework.lookup("汽车")` returns framework with `anti_patterns` containing "LTV/CAC"
  - [x] `IndustryFramework.lookup("不存在的行业")` returns None

  **QA Scenarios**:
  ```
  Scenario: automotive framework lookup
    Tool: Bash
    Steps: python -c "from tradingagents.industry.frameworks import IndustryFramework; f = IndustryFramework(); r = f.lookup('汽车'); print('FOUND' if r else 'NONE'); print(r.get('anti_patterns',[])[:3])"
    Expected: prints FOUND + anti-patterns including 'LTV/CAC'
    Evidence: .omo/evidence/task-2-framework.txt

  Scenario: unknown industry returns None
    Tool: Bash
    Steps: python -c "from tradingagents.industry.frameworks import IndustryFramework; f = IndustryFramework(); r = f.lookup('不存在'); print('None' if r is None else 'FOUND')"
    Expected: prints 'None'
    Evidence: .omo/evidence/task-2-none.txt
  ```

  **Commit**: grouped with Task 1

- [x] 3. **AgentState + industry 字段 + executor pipeline 穿透**

  **What to do**:
  - EDIT `tradingagents/agents/utils/agent_states.py`: add `industry: Annotated[str, "Detected industry classification"] = ""`
  - EDIT `tradingagents/graph/executor.py:_build_init_state()`: add `"industry": context.industry or ""` to returned dict
  - CREATE test: verify `_build_init_state()` produces state with `"industry"` key
  - TDD: RED → GREEN

  **Must NOT do**: Don't change other AgentState fields, don't alter `_build_init_state()` logic

  **Agent**: `quick`, Skills: `[]` | **Parallel**: Wave 1 (with Task 4) | **Blocks**: Task 5-9 | **Blocked By**: Task 1

  **References**:
  - `tradingagents/agents/utils/agent_states.py:85-89` — existing field pattern near `market_type`
  - `tradingagents/graph/executor.py:220-246` — `_build_init_state()` return dict
  - `tradingagents/graph/executor.py:229` — `market_context` injection pattern to follow

  **Acceptance Criteria**:
  - [x] `AgentState` has `industry` field (empty string default)
  - [x] `_build_init_state()` returns `"industry": "商用载货车"` when context has industry
  - [x] `_build_init_state()` returns `"industry": ""` when context has empty industry

  **QA Scenarios**:
  ```
  Scenario: industry flows into AgentState
    Tool: Bash
    Steps: python -c "from tradingagents.planner.schemas import Context, Trigger; from tradingagents.planner.llm_planner import LLMPlanner
  # verify context.industry survives
  c = Context(ticker='600418', industry='商用载货车')
  print(f'industry={c.industry}')"
    Expected: prints 'industry=商用载货车'
    Evidence: .omo/evidence/task-3-agentstate.txt
  ```

  **Commit**: `feat(industry): add AgentState.industry field and executor pipeline` — `agent_states.py`, `executor.py`

- [x] 4. **build_instrument_context() 扩展 + context_manager 行业注入**

  **What to do**:
  - EDIT `tradingagents/agents/utils/agent_utils.py:build_instrument_context()`: add optional `industry: str = ""` param
  - When industry non-empty, append: `f"\n**行业背景：** {ticker} 属于 {industry} 行业。请关注该行业的核心指标和竞争格局。"`
  - When empty: behavior unchanged (no "行业" text appended)
  - EDIT `tradingagents/graph/context_manager.py:inject_context()`: add `"industry": state.get("industry", "")` to returned ctx dict
  - CREATE test: verify industry appears in output / empty maintenance

  **Must NOT do**: Don't change function signature (add optional param), don't modify debate agent core prompts

  **Agent**: `quick`, Skills: `[]` | **Parallel**: Wave 1 (with Task 3) | **Blocks**: Task 5-9 | **Blocked By**: Task 1

  **References**:
  - `tradingagents/agents/utils/agent_utils.py:69-87` — `build_instrument_context()` current impl
  - `tradingagents/graph/context_manager.py:142-217` — `inject_context()` return dict
  - `lsp_find_references` on `build_instrument_context` — 7 call sites to update

  **Acceptance Criteria**:
  - [x] `build_instrument_context("600418", "商用载货车")` output contains "商用载货车"
  - [x] `build_instrument_context("600418", "")` output does NOT contain "行业" keyword
  - [x] `inject_context()` returns dict with `"industry"` key

  **QA Scenarios**:
  ```
  Scenario: industry injected into instrument context
    Tool: Bash
    Steps: python -c "from tradingagents.agents.utils.agent_utils import build_instrument_context; ctx = build_instrument_context('600418', '商用载货车'); print('PASS' if '商用载货车' in ctx else 'FAIL')"
    Expected: prints PASS
    Evidence: .omo/evidence/task-4-context.txt

  Scenario: empty industry preserves original behavior
    Tool: Bash
    Steps: python -c "from tradingagents.agents.utils.agent_utils import build_instrument_context; ctx = build_instrument_context('600418'); print('PASS' if '行业背景' not in ctx else 'FAIL')"
    Expected: prints PASS (no industry text added)
    Evidence: .omo/evidence/task-4-context-empty.txt
  ```

  **Commit**: grouped with Task 3

- [ ] 5. **fundamentals_analyst 行业提示词注入**

  **What to do**:
  - `agents/analysts/fundamentals_analyst.py`: 读 `state["industry"]`，调用 `lookup_industry()` 获取框架
  - 在 system_message 末尾追加行业背景（估值方法、关键财务指标、同行对比建议）
  - 当 industry="" 时跳过注入

  **Must NOT do**: 不修改现有 A-Share fundamentals context 块（lines 35-47）

  **Agent**: `quick`, Skills: `[]` | **Parallel**: Wave 2 (with Tasks 6-9) | **Blocked By**: Task 3, 4

  **References**: `agents/analysts/fundamentals_analyst.py:31-51` — 现有 system_message 模式

  **QA Scenarios**:
  ```
  Scenario: fundamentals prompt includes industry context when industry set
    Tool: Bash (pytest)
    Steps: pytest tests/test_industry_prompt.py::test_fundamentals_industry -v
    Expected: captured system_message contains "行业背景" + industry-specific terms
    Evidence: .omo/evidence/task-5-fundamentals.txt
  ```

  **Commit**: YES | `feat(industry): inject industry into fundamentals_analyst` | `agents/analysts/fundamentals_analyst.py`

- [x] 6. **market_analyst 行业提示词注入**

  **What to do**:
  - `agents/analysts/market_analyst.py`: 读 `state["industry"]`，注入行业技术分析特征（行业轮动、典型交易模式）
  - 当 industry="" 时跳过注入

  **Must NOT do**: 不修改现有 A-Share Technical Focus 块（lines 41-52）

  **Agent**: `quick`, Skills: `[]` | **Parallel**: Wave 2 | **Blocked By**: Task 3, 4

  **References**: `agents/analysts/market_analyst.py:28-56` — system_message template pattern

  **QA Scenarios**:
  ```
  Scenario: market analyst prompt includes industry context
    Tool: Bash (pytest)
    Steps: pytest tests/test_industry_prompt.py::test_market_industry -v
    Expected Result: captured prompt contains industry-specific technical guidance
    Evidence: .omo/evidence/task-6-market.txt
  ```

  **Commit**: YES | `feat(industry): inject industry into market_analyst` | `agents/analysts/market_analyst.py`

- [x] 7. **news_analyst 行业提示词注入**

  **What to do**: `agents/analysts/news_analyst.py` → 注入行业政策关注点、行业新闻筛选规则 | 当 industry="" 时跳过

  **Agent**: `quick`, Skills: `[]` | **Parallel**: Wave 2 | **Blocked By**: Task 3, 4 | **Commit**: YES

- [x] 8. **social_analyst + portfolio_manager 行业提示词注入**

  **What to do**:
  - `agents/analysts/social_media_analyst.py` → 注入行业情绪解读指导
  - `agents/managers/portfolio_manager.py` → 读 `state["industry"]` 注入行业基准参考

  **Agent**: `quick`, Skills: `[]` | **Parallel**: Wave 2 | **Blocked By**: Task 3, 4 | **Commit**: YES

- [x] 9. **trader + research_manager 行业提示词注入**

  **What to do**:
  - `agents/trader/trader.py` → 注入行业风险偏好、典型持仓周期
  - `agents/managers/research_manager.py` → 注入行业对比框架
  - 所有 Agent 注入当 industry="" 时跳过

  **Agent**: `quick`, Skills: `[]` | **Parallel**: Wave 2 | **Blocked By**: Task 3, 4 | **Commit**: YES

- [x] 10. **Layer 3 — 一致性校验器（规则层 + LLM 层）**

  **What to do**:
  - CREATE `tradingagents/industry/verifier.py`
  - IMPLEMENT `verify_industry_consistency(industry: str, report: str) -> dict`
  - 规则层（优先）：从 `industry_frameworks.json` 加载 anti_patterns → 检查 report 中是否出现禁止指标
  - LLM 层（fallback）：规则层无法判断时，单次 `quick_llm` 调用 → 结构化 JSON `{"consistent": bool, "issues": list, "severity": "warning"|"error"}`
  - CREATE `tests/test_industry_verifier.py` 包含 4 个测试

  **Must NOT do**: 不超过 1 次额外 quick_llm 调用 | 不进行递归自检

  **Agent**: `deep`, Skills: `[]` | **Parallel**: Wave 3 (with Task 11, 12) | **Blocked By**: Task 2, 5-9

  **References**: `tests/test_e2e_600418.py:63-67` — `_HALLUCINATION_KWS` 模式可扩展

  **QA Scenarios**:
  ```
  Scenario: auto report with SaaS metrics → flagged
    Tool: Bash (pytest)
    Steps: pytest tests/test_industry_verifier.py::test_auto_with_saas -v
    Expected: consistent=false, issues contains "LTV/CAC not applicable to automotive"
    Evidence: .omo/evidence/task-10-verifier-fail.txt

  Scenario: auto report with auto metrics → passes
    Tool: Bash (pytest)
    Steps: pytest tests/test_industry_verifier.py::test_auto_with_auto -v
    Expected: consistent=true, issues=[]
    Evidence: .omo/evidence/task-10-verifier-pass.txt
  ```

  **Commit**: YES | `feat(industry): add consistency verifier` | `industry/verifier.py`, `tests/test_industry_verifier.py`

- [x] 11. **TemplateMatcher industry 特征修复**

  **What to do**:
  - `planner/template_matcher.py:_score_template()`: 让已有 `industry` 特征参与评分（加 `0.15` 当行业匹配时）
  - 修复废弃代码：`_extract_features()` 已有 `industry` 但从未被使用

  **Agent**: `quick`, Skills: `[]` | **Parallel**: Wave 3 | **Blocked By**: Task 2 | **Commit**: YES

- [x] 12. **E2E 集成测试 + 全量回归**

  **What to do**:
  - 运行 `test_e2e_600418.py` 全部 3 个测试（需要 DEEPSEEK_API_KEY）
  - 运行 `pytest tests/ -x --tb=short -q` 验证 857+ passes, 0 fails
  - 补充 `test_e2e_600418.py` 新增 `test_industry_terms_in_report()` 验证报告包含正确的行业术语
  - 补充 `test_consistency_verification_integration()` 端到端验证校验器

  **Agent**: `unspecified-high`, Skills: `[]` | **Parallel**: Wave 3 | **Blocked By**: Task 10, 11 | **Commit**: YES

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  验证 Must Have/Must NOT Have 合规性，evidence 文件存在性

- [ ] F2. **Code Quality Review** — `unspecified-high`
  运行 pytest 全量 + lint，检查 AI slop 模式

- [ ] F3. **Real Manual QA** — `unspecified-high`
  执行所有 QA 场景，交叉任务集成测试，边界情况测试

- [ ] F4. **Scope Fidelity Check** — `deep`
  逐任务验证 diff，检测范围蔓延和跨任务污染

---

## Commit Strategy

- Wave 1: `feat(industry): add industry field to AgentState and _build_init_state()` — agent_states.py, executor.py
- Wave 1: `feat(industry): add IndustryClassifier service and framework config` — industry/
- Wave 2: `feat(industry): inject industry context into analyst and manager agents` — 7 agent files, agent_utils.py
- Wave 3: `feat(industry): add consistency verifier and e2e tests` — industry/verifier.py, tests/

---

## Success Criteria

### Verification Commands
```bash
pytest tests/test_industry_classifier.py -v          # Layer 1 tests
pytest tests/test_industry_e2e.py -v                 # Layer 2 + 3 tests
pytest tests/test_e2e_600418.py -v --run-slow        # Regression anchor
pytest                                                 # Full 857+ suite
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] 857+ tests pass
- [ ] 600418 E2E passes (no AI/keyword hallucination)
- [ ] Industry field flows end-to-end: api_server → AgentState → Agent prompts → report
