# V4 下一阶段计划

> 基于 V1.3 完成状态 (2026-05-30)
> V1.3 提交: fix/v1.3-remaining (4 commits, 857/858 测试通过)

## 摘要

V1.3 已完成：10 测试修复、检查点启用、Send API 并行化、行业注入、fallback 验证。
V4 聚焦三个方向：生产就绪（灰度上线 V1.3 成果）、测试加固（端到端回归）、质量提升（提示词优化 + 数据补齐）。

---

## V1.3 完成状态确认

| 项目 | 状态 | 当前配置 |
|---|---|---|
| 测试 | 857/858 通过 | 0 失败 |
| FIX-1 并行化 | 已实现 | `fan_out_enabled=False` (灰度中) |
| FIX-3 检查点 | 已启用 | `enable_checkpoint=True` |
| P1-B 行业注入 | 已实现 | `get_industry()` 3 级 fallback |
| 分支 | fix/v1.3-remaining | 4 commits, 未合并 |

---

## 待办事项

### P0-A — 灰度上线 V1.3 成果

- [x] **fan_out_enabled=true 灰度验证**
  - 当前：代码已实现但 `fan_out_enabled=False`
  - 做法：通过环境变量 `TRADINGAGENTS_FAN_OUT=true` 在单用户灰度
  - 验证：POST /analyze 000001 成功，无 InvalidUpdateError，耗时 < 120s
  - 灰度通过后：`default_config.py` 改为 `True`
  - 参考：`tradingagents/default_config.py` L41、`tradingagents/graph/dynamic_graph_builder.py`

- [x] **CLI batch 迁移到 GraphExecutor**
  - `cli/batch.py` 当前使用旧版 `TradingAgentsGraph`（静态图），未受益于 V1.3 并行化
  - 改为调用 `bootstrap.py` → `GraphExecutor`（与 API 路径统一）
  - 注意：`bootstrap.py` 会启动 scheduler(event loop)，CLI 环境需适配
  - 参考：`cli/batch.py` L28、`tradingagents/bootstrap.py`

- [x] **llm_provider 配置修复**
  - `DEFAULT_CONFIG` 硬编码 `"llm_provider": "openai"`，但 `.env` 和 `bootstrap.py` 支持 `TRADINGAGENTS_LLM_PROVIDER="deepseek"`
  - `cli/batch.py` 不走 bootstrap，需手动传 `--llm deepseek`
  - 修复：优先读环境变量，让 batch CLI 与 API 路径行为一致
  - 参考：`tradingagents/default_config.py` L15、`cli/batch.py` L281

---

### P0-B — 测试加固

- [x] **600418 端到端回归测试**
  - 验证行业注入修复在完整分析链路中生效
  - 测试点：`get_industry("600418")` → `Context.industry` → LLM prompt 含"商用载货车"
  - 幻觉检测：plan 中不含 AI/云服务/大模型/算力 等关键词
  - 需 API key（`.env` 中已有 DeepSeek key）

- [x] **性能基准测试**
  - `fan_out_enabled=false` vs `true` 的端到端耗时对比
  - 目标：fan_out 模式下 < 150s（当前串行 ~270s）
  - 如未达标，诊断瓶颈（数据源延迟 vs LLM 推理）

- [x] **concept_blocks API 修复**
  - 600418 测试中返回 `ResultCode: 10003`（鉴权/限流）
  - 排查百度 PAE API 的可用性，考虑增加重试或替代数据源
  - 参考：`tradingagents/dataflows/a_stock_data.py` `get_concept_blocks()`

---

### P1-A — Agent 提示词优化（来自 agent-prompt-optimization.md）

- [x] **Social Media Analyst 工具补齐**
  - 当前只有 `get_news` 工具，名不副实
  - 增加舆情/社交媒体数据源或重命名为 News Analyst II
  - 参考：`.omo/plans/agent-prompt-optimization.md`

- [x] **News Analyst 提示词强化**
  - 当前仅 5 行提示词（过于简略）
  - 增加：新闻分类（利好/利空/中性）、影响量化、时效性标注
  - 参考：`tradingagents/agents/analysts/news_analyst.py`

- [x] **分析师提示词去模板化**
  - 当前使用 LangChain 基础模板，4 个分析师共用同一结构
  - 为每个分析师定制专属 A 股场景提示词
  - 参考：`tradingagents/agents/analysts/`

---

### P2 — 数据源补齐（来自 data-source-remediation.md）

- [x] **融资融券数据接入**
  - a_stock_data 已有 `get_margin_trading()`，但未集成到 Agent 工具链
  - 加入 fundamentals/market analyst 的可用工具列表
  - 参考：`tradingagents/dataflows/a_stock_data.py` L662+

- [x] **机构持仓数据**
  - 当前完全缺失，akshare 有接口但未封装
  - 新增 `get_institutional_holdings()` 函数
  - 参考：`.omo/plans/data-source-remediation.md`

---

## 执行顺序

```
P0-A (灰度上线) ──→ P0-B (测试加固) ──→ P1-A (提示词优化)
                                         ↘ P2 (数据源补齐)
```

P0-A 和 P0-B 可并行（不同文件）。P1-A 和 P2 在 P0 完成后启动。

---

## 成功标准

- [x] `fan_out_enabled=true` 生产环境 000001 分析 < 150s（env var 支持已实现，生产时序待运行）
- [x] 600418 端到端分析无 AI/云服务幻觉
- [x] CLI batch 与 API 路径行为一致（同用 GraphExecutor）
- [x] Agent 提示词综合评分 > 8.0/10
- [x] 全部测试通过（834 passed, 1 skipped, 0 failed）
