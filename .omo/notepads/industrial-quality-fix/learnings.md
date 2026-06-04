# Industrial Quality Fix — Learnings

## Task: 硬编码指标名改为从 indicator_registry 导入

**时间**: 2026-06-03

**修改文件**:
- `tradingagents/agents/analysts/market_analyst.py`
- `tradingagents/agents/utils/technical_indicators_tools.py`

**改动**:
1. `market_analyst.py`: 添加 `INDICATORS` 导入，构建 `indicator_list` 变量替换 system prompt 中硬编码的 12 个指标名分类（L47-53）
2. `technical_indicators_tools.py`: 添加 `INDICATORS` 导入，`indicator` 参数的 `Annotated` description 从静态文本改为动态拼接 `info.name for info in INDICATORS`
3. 两个文件中的 docstring 示例也从 `'rsi', 'macd'` 改为引用 registry

**效果**: 修改指标只需改 `indicator_registry.py` 一处，两文件自动同步。`INDICATORS` 顺序由 dict 插入顺序保证（与原来硬编码顺序一致）。


## Task 7: 创建 `scripts/verify_tool_alignment.py` — AST 解析工具对齐验证

**时间**: 2026-06-03

**创建文件**: `scripts/verify_tool_alignment.py`

**功能**:
1. 使用 Python `ast` 模块（stdlib）静态解析 `tradingagents/agents/analysts/*.py` 中各 analyst 函数的 `tools = [...]` 列表
2. 解析 `tradingagents/bootstrap.py` 中 `_create_tool_nodes()` 返回的 `ToolNode([...])` 注册表字典
3. 通过 `FILENAME_TO_AGENT_KEY` + `TOOL_KEY_MAP` 两层映射连接 analyst → bootstrap key
4. 比较两组工具名集合，输出不匹配详情
5. 退出码：0（完全对齐）/ 1（存在不匹配）

**设计要点**:
- `social_media_analyst.py` 在 `TOOL_KEY_MAP` 中的 key 是 `social_analyst`（不含 "media"），需要单独的 `FILENAME_TO_AGENT_KEY` 映射
- AST 节点处理：`ast.Name`（如 `get_news`）和 `ast.Attribute`（如 `module.func`）均通过 `extract_name()` 提取
- bootstrap 解析定位 `_create_tool_nodes` → `return {str: ToolNode([...])}` 结构，dict key 要求是 `ast.Constant`，value 要求是 `ast.Call(func=ast.Name('ToolNode'))`
- 不做硬编码工具名，全部动态 AST 提取

**当前验证结果**（exit 1，符合预期）:
| Analyst | bind_tools | ToolNode | 差值 |
|---------|-----------|----------|------|
| fundamentals_analyst | 1 (`get_fundamentals`) | 6 (+5) | 缺少 `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_margin_trading`, `get_institutional_holdings` |
| market_analyst | 4 | 4 | ✅ |
| news_analyst | 2 (`get_news`, `get_global_news`) | 3 (+1) | 缺少 `get_insider_transactions` |
| social_media_analyst | 4 | 4 | ✅ |

**教训**:
- AST 解析 `tools = [...]` 时需遍历所有 `ast.Assign` 节点（`tools` 可能在函数体内深处），不能只查顶层
- `ast.walk()` 比定向 child 搜索更鲁棒，尤其在函数嵌套深时
- `set()` 比较可自动忽略顺序差异，适合工具名比对
- 对比时优先用 `set` 而非排序列表，顺序变化不应算作不匹配

## 2026-06-03: Task 4 — LLM Client `_PASSTHROUGH_KWARGS` 添加 `temperature` / `max_tokens`

- 修改了 4 个 LLM 客户端文件，在各 `_PASSTHROUGH_KWARGS` 末尾追加了 `temperature` 和 `max_tokens`（Google 为内联 tuple）
- **anthropic_client.py** 的 `_PASSTHROUGH_KWARGS` 已含 `"max_tokens"`（第 2 条），故仅添加 `"temperature"`
- 所有 tuple 末尾追加，保持现有顺序不变
- `get_llm()` 方法无需修改——它已通过 `for key in _PASSTHROUGH_KWARGS: if key in self.kwargs:` 通用遍历支持新增字段
- `test_resilient_llm.py` 12 个测试全部通过（0.05s）
- Task 3（bootstrap.py 注入）完成后，temperature/max_tokens 即可从用户配置完整传递到 LLM 构造函数

## Task 3: 注入 temperature 到 bootstrap `_create_llms()`

**时间**: 2026-06-03

**修改文件**: `tradingagents/bootstrap.py` L95-98

**改动**: 将 `llm_kwargs = {}` 替换为包含 `temperature` 和 `max_tokens` 的字典，从 `config.get()` 读取：
```python
llm_kwargs = {
    "temperature": config.get("llm_temperature", 0.0),
    "max_tokens": config.get("llm_max_tokens", 4096),
}
```

**关键发现**:
1. `default_config.py` 中已有 `llm_temperature` (0.0) 和 `llm_max_tokens` (4096) 键（L29-30）
2. `_create_llms(config)` 已经接收 `config` 参数（`DEFAULT_CONFIG.copy()` + env overrides），使用 `config.get()` 比额外调用 `get_config()` 更干净且避免 import 依赖
3. `llm_kwargs` 字典随后被 provider-specific 参数（`thinking_level`, `reasoning_effort`, `effort`）补充，然后通过 `**llm_kwargs` 传递到 `create_llm_client()`
4. `create_llm_client` 的 `**kwargs` 直接透传到各 provider 的 client 构造函数（`OpenAIClient`, `AnthropicClient`, `GoogleClient`, `AzureOpenAIClient`）
5. ResilientLLM 包装逻辑（L145-152）完全不受影响

**验证**: `tests/test_resilient_llm.py` 12/12 通过

## Task 5: 删除 `macro_analyst` 死代码映射

**时间**: 2026-06-03

**修改文件**: `tradingagents/graph/dynamic_graph_builder.py`

**改动**: 删除文件中全部 9 处 `macro_analyst` 引用：
1. `TOOL_KEY_MAP` (L31) — `"macro_analyst": "market"`
2. `_STATE_KEYS` (L36) — `"macro_analyst": "market_report"`
3. `ANALYST_AGENTS` (L45) — `"macro_analyst"`
4. `_add_graph_structure` condition_map (L164) — `"macro_analyst": "should_continue_market"`
5. `_tool_route_keys` mapping (L252) — `"macro_analyst": ("tools_market", "Msg Clear Market")`
6. `_add_tool_cycle` condition_map (L266) — `"macro_analyst": "should_continue_market"`
7. `_known_agents()` (L348) — `"macro_analyst"`
8. `_agent_factory()` (L361) — `"macro_analyst": create_market_analyst`
9. `_ANALYST_STATE_KEY_MAP` (L380) — `"macro_analyst": "macro_report"`

**关键发现**:
- `macro_analyst` agent 在 `agents/analysts/` 目录无对应 `.py` 文件，`create_macro_analyst` 函数不存在
- 映射 `"macro_analyst": "market"` 与 `"market_analyst": "market"` 完全重复（TOOL_KEY_MAP 和 condition_map 中都是）
- 映射 `"macro_analyst": create_market_analyst` 在 `_agent_factory` 中实际指向 `create_market_analyst` 函数，纯冗余

**其他文件引用**:
- `tradingagents/planner/llm_planner.py` L21 有描述 `| macro_analyst | 宏观 |` — 仅 prompt 文档，非运行时依赖，未修改

**验证**: `tests/test_debate_routing.py` 21/21 通过

# 2026-06-03: PR-0 Task 1 — test_llm_config.py (RED phase discovery)

## Expected
创建 6 个 failing test 验证 temperature 注入链路 —— 标准的 RED 阶段 TDD。

## Actual
全部 6 个测试 **已经通过**。原因是 temperature 配置链路在文件创建前已经实现：

| 测试 | 结果 | 原因 |
|------|------|------|
| `test_default_config_has_temperature_key` | ✅ PASS | `default_config.py:29` 已有 `llm_temperature: 0.0` |
| `test_default_config_has_debate_temperature` | ✅ PASS | `default_config.py:32` 已有 `llm_debate_temperature: 0.3` |
| `test_bootstrap_injects_temperature` | ✅ PASS | `bootstrap.py:96` 已有 `"temperature": config.get("llm_temperature", 0.0)` |
| `test_openai_client_passes_temperature` | ✅ PASS | `openai_client.py:207` 的 `_PASSTHROUGH_KWARGS` 包含 `"temperature"` |
| `test_anthropic_client_passes_temperature` | ✅ PASS | `anthropic_client.py:11` 的 `_PASSTHROUGH_KWARGS` 包含 `"temperature"` |
| `test_google_client_passes_temperature` | ✅ PASS | `google_client.py:34` 的 inline list 包含 `"temperature"` |

## Key Takeaway
This entire feature was already implemented before PR-0 started. The tests
serve as a GREEN-phase validation suite rather than RED-phase failing specs.
When adding new LLM clients in the future, temperature must be in PASSTHROUGH_KWARGS.

## Files Created
- `tests/test_llm_config.py` — 6 个测试验证全链路 temperature 传递

## State
- 6/6 测试通过（GREEN 阶段，非原计划的 RED）
- 无生产代码需要修改

## 2026-06-03: 添加 LLM 温度配置键

### 变更
在 `tradingagents/default_config.py` 的 LLM 配置段末尾（`anthropic_effort` 之后）添加了 5 个新配置键：

- `llm_temperature`: 0.0 — 全局 LLM 温度，默认定向（工业级基线）
- `llm_max_tokens`: 4096 — 防止 LLM 输出无限长
- `llm_debate_temperature`: 0.3 — 辩论 agent 使用更高温度增加多样性
- `llm_risk_temperature`: 0.2 — 风控 agent 偏保守多样性
- `llm_decision_temperature`: 0.1 — 决策层接近确定性

### 要点
- `get_config()` 不在 `default_config.py` 中，而是在 `config_section.py` 中
- DEFAULT_CONFIG 添加新键后，下游 `get_config()` 和 `ConfigSection` 自动继承（基于 `DEFAULT_CONFIG.copy()` 或 `**DEFAULT_CONFIG` 机制）
- `test_default_config` 测试通过，确认无回归
- 配置键命名风格采用下划线分隔，与现有 `google_thinking_level`、`openai_reasoning_effort` 一致

### 注意
- 后续使用这些键的模块需处理 fallback：当 role-specific temperature 未设置时回退到 `llm_temperature`

## 2026-06-03: Task 6 — 确定性冒烟测试 `tests/test_determinism.py`

### 变更
创建 `tests/test_determinism.py`，包含 5 个 pytest 测试（`@pytest.mark.smoke` + `@pytest.mark.unit`）：

| 测试 | 验证内容 |
|------|---------|
| `test_three_identical_calls_same_md5` | 3 次相同输入 → 3 次 MD5 完全一致 |
| `test_mock_llm_receives_calls` | mock LLM 实际被调用了 3 次 |
| `test_state_isolation_between_calls` | 两次独立调用互不污染 |
| `test_output_contains_expected_fields` | 返回值包含所有必需字段 |
| `test_deterministic_across_mock_instances` | 不同 mock 实例 → 相同输出 |

### 关键设计决策

1. **Mock LLM 模式**：使用 `RunnableLambda` 而非 `MagicMock`，因为 analyst 节点使用 LangChain pipe 操作符（`prompt \| llm.bind_tools(tools)`）。`RunnableLambda` 是真正的 `Runnable`，与 LangChain `|` 操作符完全兼容。

2. **测试目标**：只测试最底层 `market_analyst`（最简 analyst 节点），不测试完整 graph 路径。符合 MUST NOT DO 的要求。

3. **温度验证**：Mock LLM 自身不是温度验证的目标（温度通过 Task 1-4 的 factory → bootstrap 链路注入）。本测试验证的是：**在温度 = 0 已生效的前提下，代码管线无随机因素**。

4. **禁止项严格遵循**：
   - ❌ 不调用真实 LLM API（全部 mock）
   - ❌ 不依赖外部数据源（无 akshare/guosen 调用）
   - ❌ 不测试复杂 graph 路径（仅测 `create_market_analyst` 单节点）

### _MockLLM vs MockDeterministicLLM

`test_causal_tracer.py:_MockLLM` 是简单 `invoke()` mock，适合直接调用的场景。

`test_determinism.py:MockDeterministicLLM` 需要 `bind_tools()` 返回 Runnable 以兼容：
```python
chain = prompt | llm.bind_tools(tools)  # LangChain pipe
chain.invoke(result_msgs)
```

### 验证
`tests/test_determinism.py` 5/5 通过（0.79s）

## 2026-06-03: Task — test_agent_tool_binding.py (RED phase)

**时间**: 2026-06-03

**修改文件**: `tests/test_agent_tool_binding.py`（新创建）

**改动**: 创建 5 个 pytest 测试验证 analyst bind_tools 与 bootstrap ToolNode 对齐：

| 测试 | 结果 | 说明 |
|------|------|------|
| `test_fundamentals_bind_tools_match_toolnode` | ❌ FAIL | 1 tool vs 6 — 预期 RED |
| `test_news_bind_tools_match_toolnode` | ❌ FAIL | 2 tools vs 3 — 预期 RED |
| `test_market_bind_tools_match_toolnode` | ✅ PASS | 4 tools vs 4 — 预期 GREEN |
| `test_social_bind_tools_match_toolnode` | ✅ PASS | 4 tools vs 4 — 预期 GREEN |
| `test_no_hallucinated_tool_calls` | ✅ PASS | filter_valid_tool_calls 正确过滤 |

**关键发现**:
1. `ToolNode` 在 langgraph 中的属性是 `tools_by_name`（dict），不是 `tools`（list）
2. 使用 AST 解析 `tools = [...]` 赋值语句提取工具名，避免调用 factory function（需要 mock state/config）
3. 比较时两边都做 `sorted()` 处理顺序差异——market/social 工具集匹配但顺序不同
4. `inspect.getsource()` 对 factory function 有效，函数体 AST 可解析

**缺失工具列表**:
- **fundamentals_analyst** 缺少 5 个工具: `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_margin_trading`, `get_institutional_holdings`
- **news_analyst** 缺少 1 个工具: `get_insider_transactions`

**验证**: 2 FAIL + 3 PASS = 5 测试全部按预期运行

## Task 8: 缩减 ToolNode 注册表与 bind_tools 完全一致（方案 A）

**时间**: 2026-06-03

**修改文件**: `tradingagents/bootstrap.py`

**改动**:
1. `agent_utils` import 删除 4 个函数：`get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_insider_transactions`
2. `a_stock_data_tools` import 删除 2 个函数：`get_margin_trading`, `get_institutional_holdings`
3. `news` ToolNode 从 `[get_news, get_global_news, get_insider_transactions]` 缩减为 `[get_news, get_global_news]`
4. `fundamentals` ToolNode 从 6 个工具缩减为仅 `[get_fundamentals]`

**结果**（全对齐）:
| Analyst | bind_tools | ToolNode | 状态 |
|---------|-----------|----------|------|
| fundamentals_analyst | 1 | 1 | ✅ |
| market_analyst | 4 | 4 | ✅ |
| news_analyst | 2 | 2 | ✅ |
| social_media_analyst | 4 | 4 | ✅ |

**验证**: `python3 scripts/verify_tool_alignment.py` exit 0

## Task: 将 akshare._INDICATOR_DESCRIPTIONS 和 a_stock_data.col_map 核心部分改为从 indicator_registry 导入

**时间**: 2026-06-03

**修改文件**:
1. `tradingagents/agents/utils/indicator_registry.py` — 补充缺失的 mfi 指标到 _INDICATOR_DESCRIPTIONS 和 _CATEGORIES（之前 akshare 有 mfi 但 registry 没有）
2. `tradingagents/dataflows/akshare.py` — 替换 13 个硬编码的 _INDICATOR_DESCRIPTIONS 为 `{info.name: info.description for info in INDICATORS}`
3. `tradingagents/dataflows/a_stock_data.py` — col_map 核心部分（12 个核心指标 + mfi）改为从 INDICATORS 生成，非核心别名（kdj_*, sma_*, boll 变体, rsi_14）保留硬编码

**关键发现**:
- `_CORE_STOCKSTATS` 映射是必要的：rsi 在 indicator_registry 中规范名为 "rsi"，但 stockstats 使用 "rsi_14" 作为列名。其他 12 个核心指标的 registry 键名与 stockstats 列名一致
- akshare._INDICATOR_DESCRIPTIONS 原先有 13 个指标（含 mfi），但 indicator_registry 只有 12 个（缺 mfi）。在替换之前需要先补齐 registry
- a_stock_data.col_map 中 5 个 boll 变体（boll_upper/boll_mid/boll_lower/boll_ub/boll_lb）中仅 boll_ub/boll_lb 是核心指标，其余是别名——用 dict spread 合并核心+非核心部分，非核心会自动覆盖同名冲突（本例中无冲突）

## 2026-06-03: Task — test_anti_hallucination.py (TDD RED phase)

**创建文件**: `tests/test_anti_hallucination.py`

**测试结果**: 4 PASS / 1 FAIL

| 测试 | 结果 | 说明 |
|------|------|------|
| `test_chinese_anti_hallucination_nonempty` | ✅ PASS | `prompt_constants.py` 已存在，中文内容正常 |
| `test_english_anti_hallucination_nonempty` | ✅ PASS | English 模式 mock 后返回英文内容 |
| `test_contains_keyword_data_unavailable` | ✅ PASS | 中/英文均含 `[数据不可用]` / `[Data Unavailable]` |
| `test_contains_tool_only_constraint` | ✅ PASS | 中/英文均含 `只使用` / `only use tools` |
| `test_degradation_english_nonempty` | ❌ FAIL | `get_degradation_instruction()` English 模式返回 `""` |

**关键发现**:
1. `prompt_constants.py` 已被其他并行任务创建，tests 1-4 无法做 ImportError RED，转而做功能验证（GREEN）
2. `get_anti_hallucination_instruction(agent_type: str = "analyst")` API 参数是 `agent_type` 而非 `lang`，语言由 `config.output_language` 控制
3. **Mock 路径陷阱**: `prompt_constants.py` 在模块级别做 `from X import get_config`，该本地引用在模块加载时已绑定，patch `X.get_config` 无效。必须同时 patch `prompt_constants.get_config` 和 `dataflows.config.get_config`
4. `agent_utils.get_degradation_instruction()` 在函数体内 import，运行时才绑定，因此只需 patch `dataflows.config.get_config`
5. 使用 `ExitStack` + 双 `patch` 的 `@contextmanager` 模式可以干净处理多站点 mock
