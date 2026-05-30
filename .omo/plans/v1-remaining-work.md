# V1.3 遗留工作 + V1.4 前瞻计划

> 基于 2026-05-30 分析对照（对比代码库实际状态）
> 原计划于 2026-05-30 17:02，本次对照于同日 21:45 更新

## 摘要

V1.3 核心架构修复（FIX-0~FIX-10）已完成并通过 847/858 测试。原计划声称的"test_quote.py 12 测试失败"和"eastmoney API 网络兼容性"实际已修复。剩余真正需要处理的是：10 个新增测试失败（a_stock_data 迁移副作用）、FIX-1 并行化重设计、FIX-3 检查点启用、Planner 行业上下文注入、数据源 fallback 全链路验证。

---

## 计划文档勘误

以下原计划中的错误数据已被本次对照修正：

| 原计划声称 | 修正后实际 | 说明 |
|---|---|---|
| 测试 849/851 通过 | **847/858 通过**（10 失败，1 跳过） | 总测试数从 851 增至 858 |
| test_quote.py 12 个测试失败 | **8/8 已通过**（commit `ad5a0ec` 已修复） | 该文件仅有 8 个测试，不是 12 个 |
| executor.py 随 FIX-1 "连带回滚" | **未回滚**。checkpoint 代码完整保留 | 仅 `fan_out_enabled` 默认值被调整 |
| eastmoney API 网络兼容性未修复 | **已修复**（commit `cdabde0`） | TLS adapter 绕过 urllib3 指纹封锁 |

---

## 待办事项（按新优先级排序）

### ✅ 已完成（可从列表中移除）

- [x] **test_quote.py 8 个测试修复** — commit `ad5a0ec`。mock 数据已从 akShare DataFrame 适配为 push2 JSON 格式，8/8 通过。
- [x] **eastmoney API 网络兼容性** — commit `cdabde0`。TLS adapter 绕过 urllib3 指纹封锁。

---

### P0-A — 新增测试失败修复（阻塞 CI，先行处理）

- [x] **test_notice.py 7 个失败修复**
  - **根因**：`get_individual_notices()` / `get_research_reports()` 已委托给 `a_stock_data` 模块（cninfo/reportapi），但测试仍 mock 旧的 `ak.stock_individual_notice_report()` / `ak.stock_research_report_em()`，mock 从未被调用
  - **还需要**：断言更新——新 API 返回英文字段（`announcementTitle` / `orgSName`），旧断言期望中文（`"公告标题"` / `"机构"` / `"中信证券"`）
  - **预估**：0.5 天
  - **参考文件**：`tests/test_notice.py`、`tradingagents/dataflows/a_stock_data.py`（`get_cninfo_announcements`、`get_research_reports`）

- [x] **test_a_share.py 2 个失败修复**
  - `test_default_config`：断言 `"akshare"`，现已是 `"a_stock_data"`
  - `test_get_fundamentals`：断言 "ROE" / "Revenue"，现腾讯财经返回 PE/PB/换手率
  - **预估**：0.5 天
  - **参考文件**：`tests/test_a_share.py`、`tradingagents/default_config.py`

- [x] **test_macro_context.py 2 个失败排查**
  - `test_us_indices_format` / `test_bond_yield_format`：返回 "——"（无数据）
  - 可能是宏数据 API 可达性问题或 akshare 端点变更
  - **预估**：0.5 天
  - **参考文件**：`tests/test_macro_context.py`、`tradingagents/dataflows/akshare.py`

---

### P0-B — FIX-3 检查点启用（最低风险，代码已就绪）

- [x] **FIX-3：V1.2 动态图检查点启用**
  - **当前状态**：`checkpointer.py`（166 行）完整存在，`executor.py` 的 11 处检查点代码全部保留。被 `if self.enable_checkpoint and self.data_dir` 隔离。默认 `False`
  - **勘误**：原计划说 executor.py "连带回滚"——**不准确**。仅 `fan_out_enabled` 被调整，checkpoint 代码从未被回滚
  - **需要做**：
    1. `default_config.py` 第 34 行：`"enable_checkpoint": False` → `True`
    2. 确认 `langgraph-checkpoint-sqlite` 在 `pyproject.toml` 依赖中
    3. 跑 `test_checkpoint.py` + `test_checkpoint_resume.py` 验证
  - **预估**：0.5 天
  - **参考文件**：`tradingagents/graph/checkpointer.py`、`tradingagents/graph/executor.py`（第 78-165 行）、`tradingagents/default_config.py`（第 34 行）
  - **注意**：有优雅 fallback（package 未安装时自动降级到无 checkpoint 模式）

---

### P1-A — FIX-1 并行化重设计（最高复杂度）

- [ ] **FIX-1：分析师并行化重新启用**
  - **当前状态**：`fan_out_enabled=false`。Oracle 分析结论：**方案 A（Send API 迁移）** 是最优路径
  - **决策依据**：`setup.py` 已有 141 行完整可运行的 LangGraph Send API 真并行实现（仅未被动态图复用）。不存在根本性的 LangGraph 限制——条件边 + Send API 已在 setup.py 中证明可行。方案 B（线程池）有线程安全风险，方案 C（缓存加速）是补充优化非替代方案。
  - **实施方案（~1-2 天）**：
    1. 解耦状态 Key：`AgentState` 新增 `macro_report` 字段，更新 `_ANALYST_STATE_KEY_MAP`
    2. 实现 Send API 扇出：在 `dynamic_graph_builder.py` 新增 `_build_parallel_analyst_path()` 方法（参考 `setup.py` lines 148-170），包含 FanOut 节点 + MergeReports 屏障
    3. 简化分组检测：将 `_detect_parallel_analyst_groups` 改为仅识别可并行的分析师列表
    4. 集成测试 + 逐步启用（环境变量灰度 → `fan_out_enabled=true`）
  - **预估**：1-2 天
  - **参考文件**：`tradingagents/graph/dynamic_graph_builder.py`、`tradingagents/graph/setup.py`、`tradingagents/agents/utils/agent_states.py`

---

### P1-B — Planner 行业上下文注入

- [ ] **Planner 辩论模板匹配优化**
  - **根因**：`Context.industry`（`schemas.py` 第 17 行）是**死字段**——被定义但从未在任何地方被填充：
    - `api_server.py` 和 `scheduler.py` 构造 `Context` 时不传 `industry`
    - `template_matcher.py` 完全不使用 `industry`
    - LLM 兜底路径收到 `行业:无`，对 `600418`（汽车制造）自行推断为"AI 云服务"
  - **勘误**：原计划说存在"AI 云服务场景模板"——**不存在此模板**。代码库只有 6 个通用模板，是 LLM 自行生成的幻觉场景
  - **需要做**：
    1. 在 `api_server.py` / `scheduler.py` 中填充 `context.industry`（从 a_stock_data/akshare 获取 SW 行业一级/二级分类）
    2. 在 `template_matcher._extract_features()` 中添加 `industry` 维度
    3. 确保 LLM 兜底路径收到正确的行业信息
  - **预估**：1 天
  - **参考文件**：`tradingagents/planner/schemas.py`（第 17 行）、`tradingagents/planner/llm_planner.py`（第 117 行）、`tradingagents/planner/template_matcher.py`（第 61-72 行）、`tradingagents/api_server.py`（第 135-139 行）、`tradingagents/scheduler/scheduler.py`（第 135-138 行）

---

### P2-A — 数据源 fallback 全链路验证

- [ ] **数据源 fallback 链完善**
  - `VENDOR_METHODS` 已加入 `a_stock_data` 路由，但 test_notice.py 的失败说明迁移不完整
  - 需要确认 a_stock_data → akshare 自动降级在下列核心函数上全部生效：
    - `get_stock_data`
    - `get_fundamentals`（当前已切换到腾讯财经，需确认 fallback 路径）
    - `get_current_price`
    - `get_indicators`
    - `get_individual_notices`（新增，迁移不完整）
    - `get_research_reports`（新增，迁移不完整）
  - **预估**：0.5 天
  - **参考文件**：`tradingagents/dataflows/interface.py`（VENDOR_METHODS 路由表）

---

## 执行顺序建议

```
     ✅ P0 全部完成
          ↓
     P1-A (FIX-1 并行化重设计) + P1-B (行业上下文注入)  ← 可并行
          ↓
     P2-A (fallback 全链路验证)
```

---

## 成功标准（修正后）

- [x] **857 测试通过，0 失败**（1 个 pre-existing skip 除外：`test_memory_log.py` 第 524 行）
- [ ] `fan_out_enabled=true` 时 000001 分析成功（无 InvalidUpdateError）
- [x] `enable_checkpoint=true` 时 POST /analyze 崩溃后能从断点恢复（配置已启用，8 个 checkpoint 测试通过）
- [ ] 600418 辩论使用汽车行业相关数据（非 AI 云服务场景）
- [x] test_notice.py / test_a_share.py / test_macro_context.py 的 10 个失败全部修复
- [ ] 数据源 fallback 在至少 3 个核心函数上可验证降级生效
