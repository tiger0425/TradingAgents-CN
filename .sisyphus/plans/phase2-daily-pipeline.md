# 阶段2：每日自动投研管线

## 摘要

将被动查询工具升级为**无人值守每日投研管线**。用户醒来收到：
宏观上下文 → 预警提醒 → 个股分析（含对抗辩论）→ 组合交叉验证 → 明日操作计划。

## 并行执行策略

```
Wave 1（并行3项，无依赖）
├── Step1: 宏观/外围数据层
├── Step2: 辩论胜负手强化
└── Step3: 组合交叉分析

Wave 2（1项，依赖Wave1）
└── Step4: 明日开盘操作计划

Wave 3（1项，依赖全部）
└── Step5: 每日管线编排
```

## 各步骤详情

### Step 1 — 宏观/外围数据层
- 新建 `tradingagents/dataflows/macro_context.py`
- 接入 akshare: 美股三大指数、美元人民币汇率、黄金/原油/铜、VIX、北向资金、国债收益率
- 每个数据源都加"最近交易日回退"逻辑（避开非交易日空数据）
- 注入 Market Analyst + Portfolio Manager prompt
- TDD: `tests/test_macro_context.py`

### Step 2 — 辩论胜负手强化
- 修改 Bull/Bear Researcher prompt：强制输出"核心证据字段"
- 修改 Research Manager prompt：锚定该字段做对比裁判
- akshare API "数据暂不可用" → 自动回退到最近交易日数据
- TDD: `tests/test_debate_anchoring.py`

### Step 3 — 组合交叉分析
- 扩展 `position_risk.py`：
  - `assess_correlation_risk()` — 持仓间皮尔逊相关性矩阵
  - `detect_hedge_opportunities()` — 识别天然对冲
- 注入 PM prompt
- TDD: `tests/test_correlation.py`

### Step 4 — 明日开盘操作计划
- Trader 结构化输出：建议买入价、目标价、止损价、仓位比例
- 基于 a_share_constraints 校验涨跌停可行性
- 结合持仓成本，输出「加仓/持有/减仓」

### Step 5 — 每日管线编排
- 新建 `cli/daily.py` — 一条命令串全部
- 支持 `--push` 一键推送晨报到通知渠道
- crontab: `0 8 * * 1-5 tradingagents daily --push`

## 成功标准
- [ ] `tradingagents daily --push` 一次运行走通全部链路
- [ ] 推送内容包含：宏观、预警、操作建议、组合风险
- [ ] 非交易日不报错，优雅降级到最近交易日数据
- [ ] 全部新增测试通过
