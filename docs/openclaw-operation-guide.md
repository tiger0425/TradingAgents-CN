# OpenClaw Agent 操作指南：TradingAgents 股票助手

> 本文档面向 OpenClaw 编排 agent，描述如何通过 CLI 命令操作 TradingAgents 股票助手。
> 所有命令均支持 `--output json`，返回结构化数据供 agent 解析。

---

## 一、快速索引

| 命令 | 用途 | 是否需要 LLM API |
|------|------|:---:|
| `tradingagents batch` | 单只股票深度分析 | ✅ 需要 |
| `tradingagents scan-watchlist` | 批量扫描自选股 | ✅ 需要 |
| `tradingagents morning-scan` | 盘前快速扫描 | ✅ 需要 |
| `tradingagents evening-review` | 收盘复盘 | ✅ 需要 |
| `tradingagents check-alerts` | 预警条件检查 | ❌ 纯数据 |
| `tradingagents market-scan` | 全市场扫描 | ❌ 纯数据 |
| `tradingagents portfolio` | 持仓组合概览 | ❌ 纯数据 |
| `tradingagents backtest` | 简化回测 | ✅ 需要 |
| `tradingagents watchlist` | 自选股管理 | ❌ 纯数据 |
| `tradingagents notify` | 发送通知 | ❌ 纯网络 |
| `tradingagents analyze` | 交互式分析 | ✅ 需要（保留） |

---

## 二、通用参数约定

### `--output` 输出模式

所有查询类命令支持三种输出模式：

| 值 | 行为 | 适用场景 |
|-----|------|---------|
| `json` | 打印结构化 JSON 到 stdout | agent 解析 |
| `text` | 打印人类可读文本摘要 | 调试/日志 |
| `silent` | 不打印任何输出，exit 0 表示成功 | 纯副作用操作 |

### LLM 相关参数

分析类命令（batch/scan-watchlist/morning-scan/evening-review/backtest）共享 LLM 配置参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--llm` | str | config | LLM 供应商：openai/google/anthropic/xai/deepseek/qwen/glm |
| `--deep-model` | str | config | 深度推理模型名 |
| `--quick-model` | str | config | 快速推理模型名 |
| `--debate-rounds` | int | 1 | 牛熊辩论轮次，越高越耗时 |

---

## 三、命令详解

### 3.1 `tradingagents batch` — 单股票深度分析

**用途**：对单只股票运行完整的多智能体分析流水线（分析师→研究员辩论→交易员→风控→组合管理）。

**语法**：
```bash
tradingagents batch \
  --ticker 600519 \
  --date 2026-05-09 \
  --analysts market,news,social,fundamentals \
  --llm openai \
  --deep-model gpt-5.4 \
  --quick-model gpt-5.4-mini \
  --debate-rounds 1 \
  --cost-price 1580.0 \
  --quantity 100 \
  --opened-date 2026-01-15 \
  --output json
```

**`--output json` 返回结构**：
```json
{
  "ticker": "600519",
  "date": "2026-05-09",
  "status": "completed",
  "analyst_reports": {
    "market": "市场分析报告文本...",
    "social": "情绪分析报告文本...",
    "news": "新闻分析报告文本...",
    "technical": "技术面分析报告文本..."
  },
  "investment_plan": "研究经理投资方案...",
  "trader_plan": "交易员交易计划...",
  "final_decision": {
    "rating": "Buy",
    "reasoning": "最终决策理由全文..."
  },
  "position": {
    "cost_price": 1580.0,
    "quantity": 100,
    "pnl_pct": 2.53,
    "pnl_amount": 4000.0,
    "current_price": 1620.0
  },
  "signals": {
    "rating": "Buy",
    "direction": "buy"
  }
}
```

**`rating` 可选值**：Buy / Overweight / Hold / Underweight / Sell
**`direction` 映射**：Buy/Overweight→buy, Hold→hold, Underweight/Sell→sell

**耗时**：约 1-3 分钟（取决于 LLM 速度和辩论轮次）。

---

### 3.2 `tradingagents scan-watchlist` — 批量扫描自选股

**用途**：对 watchlist 中所有股票逐只运行完整分析，汇总结果。

**语法**：
```bash
tradingagents scan-watchlist --date 2026-05-09 --output json
```

**`--output json` 返回结构**：
```json
{
  "date": "2026-05-09",
  "total": 15,
  "scanned": 15,
  "signals": {
    "buy": ["600519", "000858"],
    "overweight": ["002415"],
    "hold": ["300750", "601318"],
    "underweight": [],
    "sell": []
  },
  "details": [
    {
      "ticker": "600519",
      "decision": "Buy",
      "summary": "最终决策摘要..."
    }
  ]
}
```

**重要**：扫描 N 只股票耗时约为 batch 的 N 倍。OpenClaw 应设置合理超时（N × 3 分钟）。

---

### 3.3 `tradingagents morning-scan` — 盘前快速扫描

**用途**：盘前快速分析。获取实时行情 + 轻量分析（仅 market + 技术面分析师，1 轮辩论）。

**语法**：
```bash
tradingagents morning-scan --date 2026-05-09 --output json
```

**`--output json` 返回结构**：
```json
{
  "date": "2026-05-09",
  "total": 10,
  "scanned": 10,
  "signals": { ... },
  "quotes": [
    {
      "ticker": "600519",
      "name": "贵州茅台",
      "current_price": 1620.0,
      "change": 15.0,
      "change_pct": 0.93
    }
  ],
  "details": [ ... ]
}
```

**耗时**：约 30-60 秒/只（轻量模式）。

---

### 3.4 `tradingagents evening-review` — 收盘复盘

**用途**：收盘后复盘。获取持仓收盘价，计算浮动盈亏，更新决策日志。

**语法**：
```bash
tradingagents evening-review --date 2026-05-09 --output json
```

**`--output json` 额外字段**：
```json
{
  "holdings": 2,
  "total_pnl": 5000.0,
  "positions": [
    {
      "ticker": "600519",
      "cost_price": 1580.0,
      "quantity": 100,
      "current_price": 1620.0,
      "pnl_amount": 4000.0,
      "pnl_pct": 2.53,
      "decision": "Buy"
    }
  ],
  ...
}
```

**自动通知**：如果配置了通知渠道，review 完成后自动推送复盘摘要。

---

### 3.5 `tradingagents check-alerts` — 预警条件检查

**用途**：检查 watchlist 中每只股票的预警条件是否触发。纯数据操作，不需要 LLM。

**语法**：
```bash
tradingagents check-alerts --date 2026-05-09 --output json
```

**`--output json` 返回结构**：
```json
{
  "date": "2026-05-09",
  "checked": 5,
  "triggered_count": 2,
  "triggered": [
    {
      "ticker": "600519",
      "alert": "price_below",
      "current": 1490,
      "threshold": 1500
    },
    {
      "ticker": "300750",
      "alert": "rsi_oversold",
      "current": 28,
      "threshold": 30
    }
  ]
}
```

**支持预警类型**：

| 类型 | 触发条件 | 需历史数据 |
|------|---------|:-------:|
| `price_above` | 现价 > 阈值 | ❌ |
| `price_below` | 现价 < 阈值 | ❌ |
| `rsi_oversold` | RSI < 30 | ✅ |
| `rsi_overbought` | RSI > 70 | ✅ |
| `volume_surge` | 今日量 > N× 20日均量 | ✅ |
| `ma_cross` | 价格上穿/下穿 MA | ✅ |

**所需预警条件在 watchlist 中配置**（见 §4.2）。

---

### 3.6 `tradingagents market-scan` — 全市场扫描

**用途**：获取 A 股全市场快照，输出涨幅榜/跌幅榜/成交量榜。纯数据操作。

**语法**：
```bash
tradingagents market-scan --top 20 --output json
```

**`--output json` 返回结构**：
```json
{
  "date": "2026-05-09",
  "market_status": "open",
  "top_gainers": [
    { "ticker": "600xxx", "name": "名称", "price": 15.20, "change_pct": 10.02 }
  ],
  "top_losers": [ ... ],
  "top_volume": [ ... ]
}
```

**耗时**：约 2-5 秒。

---

### 3.7 `tradingagents portfolio` — 持仓组合概览

**用途**：读取 `position_state.json` 中所有持仓，获取实时行情，计算盈亏和集中度。

**语法**：
```bash
tradingagents portfolio --date 2026-05-09 --output json
```

**`--output json` 返回结构**：
```json
{
  "date": "2026-05-09",
  "total_holdings": 2,
  "total_cost": 170000.0,
  "total_market_value": 175000.0,
  "total_pnl": 5000.0,
  "total_pnl_pct": 2.94,
  "holdings": [
    {
      "ticker": "600519",
      "name": "贵州茅台",
      "cost_price": 1580.0,
      "quantity": 100,
      "current_price": 1620.0,
      "market_value": 162000.0,
      "pnl_amount": 4000.0,
      "pnl_pct": 2.53,
      "weight": 92.57
    }
  ],
  "concentration": {
    "top1_weight": 92.57,
    "top3_weight": 100.0,
    "num_holdings": 2
  }
}
```

---

### 3.8 `tradingagents backtest` — 简化回测

**用途**：对单只股票在日期范围内逐日运行分析流水线，汇总决策分布和胜率。

**语法**：
```bash
tradingagents backtest \
  --ticker 600519 \
  --start-date 2026-04-01 \
  --end-date 2026-04-30 \
  --debate-rounds 1 \
  --output json
```

**`--output json` 返回结构**：
```json
{
  "ticker": "600519",
  "start_date": "2026-04-01",
  "end_date": "2026-04-30",
  "total_trading_days": 21,
  "analyzed_days": 21,
  "decisions": {
    "buy": 5,
    "hold": 10,
    "sell": 6
  },
  "performance": {
    "total_return_pct": 3.5,
    "win_rate_pct": 60.0,
    "avg_holding_return_pct": 1.2
  }
}
```

**⚠️ 成本警告**：每个交易日调用一次完整 LLM 分析流水线。21 个交易日 ≈ 21 × 2 分钟 ≈ 42 分钟。建议仅用 `--debate-rounds 1`。

---

### 3.9 `tradingagents watchlist` — 自选股管理

**用途**：管理 `~/.tradingagents/watchlist.json` 中的自选股列表。

**子命令**：

```bash
# 添加/更新股票
tradingagents watchlist add 600519 \
  --name "贵州茅台" \
  --priority 1 \
  --price-above 1600 \
  --price-below 1500 \
  --rsi-oversold \
  --rsi-overbought \
  --volume-surge 2.0

# 移除股票
tradingagents watchlist remove 600519

# 列出所有股票（按优先级排序）
tradingagents watchlist list --output json

# 查看单只股票详情
tradingagents watchlist get 600519 --output json

# 设置预警
tradingagents watchlist set-alert 600519 --price-below 1500

# 移除预警
tradingagents watchlist remove-alert 600519 --price-above
```

**`list --output json` 返回**：
```json
[
  {
    "ticker": "600519",
    "name": "贵州茅台",
    "priority": 1,
    "alerts": {
      "price_above": 1600.0,
      "rsi_oversold": true
    }
  }
]
```

---

### 3.10 `tradingagents notify` — 发送通知

**用途**：向已配置的通知渠道发送消息。

**语法**：
```bash
# 发送到飞书
tradingagents notify feishu --title "今日信号" --content "600519: Buy"

# 发送到微信（Server酱/PushPlus）
tradingagents notify wechat --title "预警" --content "价格跌破支撑"

# 发送到所有渠道
tradingagents notify all --markdown --title "晨报" --content "$(cat report.md)"
```

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `--title` | str | 消息标题（必填） |
| `--content` | str | 消息正文（必填） |
| `--markdown` | flag | 以 markdown 格式发送 |

**成功返回**：exit 0，无 stdout 输出（`--output` 不受支持）。

---

## 四、数据文件

### 4.1 持仓文件 `~/.tradingagents/memory/position_state.json`

```json
{
  "600519": {
    "cost_price": 1580.0,
    "quantity": 100,
    "opened_date": "2026-01-15",
    "updated_at": "2026-05-09T10:00:00"
  },
  "000858": {
    "cost_price": 120.0,
    "quantity": 500,
    "opened_date": "2026-03-01",
    "updated_at": "2026-05-09T10:00:00"
  }
}
```

**自动更新规则**：
- `batch`/`scan-watchlist` 分析完成后，PM 决策为 Buy/Overweight 且无持仓 → 自动开仓 100 股（分析日收盘价）
- 决策为 Sell/Underweight 且有持仓 → 自动平仓（受 T+1 约束保护）
- 同 ticker 同日期不会重复更新（幂等）

### 4.2 自选股文件 `~/.tradingagents/watchlist.json`

```json
{
  "stocks": [
    {
      "ticker": "600519",
      "name": "贵州茅台",
      "priority": 1,
      "alerts": {
        "price_above": 1600.0,
        "price_below": 1500.0,
        "rsi_oversold": true,
        "rsi_overbought": true,
        "volume_surge": 2.0,
        "ma_cross": true
      }
    }
  ]
}
```

### 4.3 决策日志 `~/.tradingagents/memory/trading_memory.md`

每次运行后自动追加。下次分析时 LLM 会读取同 ticker 的历史决策和收益，形成经验教训注入 PM prompt。

---

## 五、配置项

### 5.1 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | OpenAI | - |
| `DEEPSEEK_API_KEY` | DeepSeek | - |
| `GOOGLE_API_KEY` | Google Gemini | - |
| `ANTHROPIC_API_KEY` | Anthropic Claude | - |
| `DASHSCOPE_API_KEY` | 阿里 Qwen | - |
| `ZHIPU_API_KEY` | 智谱 GLM | - |
| `FEISHU_WEBHOOK` | 飞书机器人 webhook URL | - |
| `SERVER_CHAN_KEY` | Server酱 SendKey | - |
| `PUSHPLUS_TOKEN` | PushPlus Token | - |

### 5.2 默认配置 (`tradingagents/default_config.py`)

```python
DEFAULT_CONFIG = {
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    "market_type": "A_SHARE",        # A_SHARE / US_STOCK
    "benchmark_ticker": "000300",    # 沪深300
    "benchmark_name": "沪深300",
    "output_language": "Chinese",
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
}
```

OpenClaw agent 可以通过 `--llm`、`--deep-model`、`--quick-model` 等参数覆盖。

---

## 六、典型工作流

### 工作流 A：盘前例行（每日 8:50）

```bash
# Step 1: 市场快照
market_scan=$(tradingagents market-scan --top 10 --output json)

# 解析 market_scan 获取大盘概况

# Step 2: 盘前快速扫描（轻量分析）
morning_report=$(tradingagents morning-scan --date "$TODAY" --output json)

# 解析 morning_report 获取信号
# 注意：可能耗时较长（N × 30-60s）

# Step 3: 检查预警
alerts=$(tradingagents check-alerts --date "$TODAY" --output json)

# 解析 alerts，如有触发则发送通知
if [ $(echo "$alerts" | jq '.triggered_count') -gt 0 ]; then
  tradingagents notify feishu --title "⚠️ 预警触发" --content "$triggered_summary"
fi
```

### 工作流 B：盘中监控（每 30 分钟）

```bash
# Step 1: 检查预警
alerts=$(tradingagents check-alerts --date "$TODAY" --output json)

# Step 2: 如有触发，运行 batch 分析该股票
for ticker in $(echo $alerts | jq -r '.triggered[].ticker' | sort -u); do
  analysis=$(tradingagents batch --ticker "$ticker" --date "$TODAY" --analysts market,technical --debate-rounds 1 --output json)
  decision=$(echo $analysis | jq -r '.final_decision.rating')
  if [ "$decision" = "Sell" ] || [ "$decision" = "Buy" ]; then
    tradingagents notify feishu --title "🔔 $ticker 信号: $decision" --content "..."
  fi
done
```

### 工作流 C：收盘复盘（每日 15:30）

```bash
# Step 1: 收盘复盘
review=$(tradingagents evening-review --date "$TODAY" --output json)

# Step 2: 如果配置了通知渠道，复盘结果会自动推送
# 无需额外操作

# Step 3: 查看持仓变动
portfolio=$(tradingagents portfolio --date "$TODAY" --output json)
total_pnl=$(echo $portfolio | jq '.total_pnl')
echo "今日总盈亏: $total_pnl"
```

### 工作流 D：新增自选股并首次分析

```bash
# Step 1: 添加自选股
tradingagents watchlist add 600519 --name "贵州茅台" --priority 1 --price-below 1500

# Step 2: 首次深度分析
analysis=$(tradingagents batch --ticker 600519 --date "$TODAY" --output json)

# Step 3: 如果结果为 Buy，通知用户
decision=$(echo $analysis | jq -r '.final_decision.rating')
if [ "$decision" = "Buy" ] || [ "$decision" = "Overweight" ]; then
  tradingagents notify feishu --title "📈 首次分析: $ticker → $decision" --content "..."
fi
```

### 工作流 E：周末复盘/回测

```bash
# 对持仓股票进行回测
for ticker in 600519 000858; do
  result=$(tradingagents backtest \
    --ticker "$ticker" \
    --start-date "$(date -d '30 days ago' +%Y-%m-%d)" \
    --end-date "$TODAY" \
    --debate-rounds 1 \
    --output json)
  echo "$ticker 回测: $(echo $result | jq '.performance')"
done
```

---

## 七、错误处理

所有命令在 `--output json` 模式下，出错时返回：

```json
{
  "ticker": "600519",
  "date": "2026-05-09",
  "status": "error",
  "error": "错误描述信息"
}
```

`scan-watchlist` 等批量命令中，单只股票失败不影响其他股票：

```json
{
  "ticker": "600519",
  "status": "error",
  "error": "API rate limit exceeded"
}
```

**建议的处理策略**：
1. 检查 `status` 字段是否为 `"completed"`
2. 批量命令中检查 `details[].status` 区分成功/失败
3. 失败时等待 30 秒后重试
4. 连续 3 次失败则跳过该 ticker，记录日志

---

## 八、已知限制

| 限制 | 说明 |
|------|------|
| **耗时** | 单股票 batch 分析约 1-3 分钟 |
| **批量耗时** | 30 只股票 × 2 分钟 ≈ 1 小时，需处理超时 |
| **akshare 稳定性** | 依赖新浪财经接口，可能随行情波动 |
| **guosen 调用限制** | 国信证券每个 API Key 限制 50 次调用 |
| **guosen 独有工具** | `get_macro_data`/`screen_stocks`/`get_rankings`/`get_fund_flow`/`compare_funds`/`filter_etf_pro`/`filter_etf_custom` 需配置 `GS_API_KEY` |
| **webhook 频率** | 飞书/Server酱可能有频率限制 |
| **JSON 序列化** | 所有输出已处理 datetime/Decimal 等类型 |
| **网络要求** | 需连接 akshare（新浪财经）和 LLM API |

### 数据源对比

| 数据源 | 覆盖 | 调用频率 | 环境变量 |
|--------|------|----------|----------|
| akshare（默认） | A 股行情/财报/新闻 | 理论无限制，受源站限制 | 无需配置 |
| guosen | A股/港股/美股行情+财务+宏观+选股 | **50次/Key** | `GS_API_KEY` |

---

## 九、版本信息

- 适用版本：v0.2.5+
- 最后更新：2026-05-09
- 计划文档：`.sisyphus/plans/trading-assistant-plan.md`
- 学习记录：`.sisyphus/notepads/trading-assistant-plan/learnings.md`
