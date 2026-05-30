# V1.3 遗留工作 + V1.4 前瞻计划

> 基于 2026-05-30 工作会话总结

## 摘要

V1.3 核心架构修复（FIX-0~FIX-10）已完成并通过 849/851 测试。遗留 3 项需要重新适配的工作 + 2 项新发现的问题 + 1 项数据源优化。

## 待办事项

### P0 — 需要重新适配

- [ ] **FIX-1: 分析师并行化重新启用**
  - **当前状态**：并行化代码已实现（LangGraph Send API），但 `fan_out_enabled=false`
  - **回滚原因**：并行拓扑与工具循环条件边存在冲突（InvalidUpdateError: market_report 重复写入）
  - **需要修复**：
    - `dynamic_graph_builder.py` 中并行组链和工具循环路由的互斥问题
    - 或者改为纯线程池并行（非 LangGraph 图级别并行）
  - **预估**：2-3 天
  - **参考文件**：`tradingagents/graph/dynamic_graph_builder.py`、`tradingagents/graph/setup.py`

- [ ] **FIX-3: V1.2 动态图检查点重新适配**
  - **当前状态**：检查点代码已实现，但因 FIX-1 回滚（executor.py 连带回滚）而无法启用
  - **需要修复**：从 commit `da2dd0e` 提取 `checkpointer.py` + `executor.py` 的检查点改动，独立于 FIX-1 重新合入
  - **预估**：1 天

- [ ] **12 个 test_quote.py 测试失败修复**
  - **原因**：新增 `a_stock_data` 模块后，`test_quote.py` 中的 mock 数据与实际 API 返回格式不匹配
  - **需要修复**：更新 mock 数据以匹配新的腾讯财经 API 返回格式
  - **预估**：0.5 天

### P1 — 新发现问题

- [ ] **Planner 辩论模板匹配优化**
  - **现象**：600418 的辩论 Agent 使用了 AI 云服务场景模板，与实际公司（汽车制造）不匹配
  - **需要修复**：在 LLM Planner 的模板匹配中添加行业/公司类型检测，为不同行业选择对应的辩论模板
  - **预估**：1 天

- [ ] **eastmoney API 网络兼容性**
  - **现象**：部分服务器环境下 eastmoney API 返回 `Connection aborted`
  - **临时方案**：已通过 TLS adapter 修复（commit cdabde0）
  - **长期方案**：数据源统一增加超时重试 + akshare fallback
  - **预估**：0.5 天

### P2 — 优化

- [ ] **数据源 fallback 链完善**
  - `get_current_price` 的 `VENDOR_METHODS` 已加入 `a_stock_data`，但实际调用仍有间歇失败
  - 需要确保 a_stock_data → akshare 的自动降级在所有核心函数（get_stock_data, get_fundamentals, get_current_price, get_indicators）上生效
  - **预估**：0.5 天

## 成功标准
- [ ] 849+ 单元测试全部通过（含 test_quote.py 12 个修复）
- [ ] `fan_out_enabled=true` 时 000001 分析成功（无 InvalidUpdateError）
- [ ] `enable_checkpoint=true` 时 POST /analyze 崩溃后能从断点恢复
- [ ] 600418 辩论使用汽车行业相关数据（非 AI 云服务场景）
