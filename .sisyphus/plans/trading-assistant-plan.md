# TradingAgents 股票助手改造计划

## 摘要

将 TradingAgents 从手动交互式 CLI 改造成可通过 OpenClaw 编排的自动化股票助手。
核心思路：OpenClaw 做大脑和调度器，项目代码提供可被 AI agent 调用的命令接口。

## 背景

- 当前 CLI 是 typer 交互式菜单（typer.prompt），AI agent 无法自动化操作
- 每次只能分析单只股票
- 输出是 Rich 终端 UI，AI agent 无法解析
- 没有定时任务/批量扫描/预警能力
- 用户使用 OpenClaw 作为驱动层，需要可编排的命令接口

## 目标

1. CLI 增加非交互式 batch 模式，所有参数可通过命令行传入
2. 自选股池 watchlist 管理 + 批量扫描
3. 结构化 JSON 输出，供 AI agent 解析
4. 飞书 + 微信通知渠道
5. 市场扫描与预警条件检查
6. 多股票组合管理

## 范围

### 包含（P0-P2）

| 优先级 | 模块 | 说明 |
|--------|------|------|
| P0 | CLI batch 模式 | 所有命令支持 `--ticker --date --output json` 等参数，无需交互 |
| P0 | watchlist 管理 | `watchlist.json` 增删改查 + `scan-watchlist` 批量扫描 |
| P0 | 结构化输出 | 所有命令支持 `--output json`，返回可解析的 JSON |
| P0 | 持仓日报/周报 | `morning-scan` + `evening-review` 两个编排入口 |
| P1 | 飞书/微信通知 | 飞书机器人 webhook + Server酱/PushPlus 微信通知 |
| P1 | 市场扫描与预警 | 涨跌幅排名、技术指标条件触发 |
| P1 | 组合管理 | 多股票持仓合并、总敞口、行业分布 |
| P2 | 回测模式 | 历史信号回放 + 绩效统计 |

### 不包含

- 不改造多智能体推理流程本身（分析师/研究员/交易员逻辑不动）
- 不接入真实券商 API（留接口但暂不实现）
- 不做 Web 仪表盘（通知走飞书/微信即可）
- 不做 Python 调度器（调度由 OpenClaw 管理）

## 架构概览

```
┌─────────────────────────────────────────────┐
│                 OpenClaw                     │
│  (大脑: 定时触发 / 决策编排 / 通知调用)       │
│                                              │
│  8:50  → morning-scan                        │
│  15:30 → evening-review                      │
│  盘中  → check-alerts                        │
│  通知  → 飞书 webhook / Server酱            │
└──────────────┬──────────────────────────────┘
               │ 调用 CLI 命令
               ▼
┌─────────────────────────────────────────────┐
│          TradingAgents CLI                   │
│  (手: 执行具体分析 / 查询 / 输出)             │
│                                              │
│  batch         非交互式股票分析                │
│  scan-watchlist 批量扫描自选股                │
│  watchlist     自选股池管理                   │
│  portfolio     组合持仓查询                   │
│  alerts        预警条件检查                   │
│  morning-scan  盘前扫描（批量）               │
│  evening-review 收盘复盘                      │
└─────────────────────────────────────────────┘
```

## 详细设计

### Phase 1: CLI 可编排化（P0）

#### 1.1 `tradingagents batch` 命令

新增非交互式分析命令，所有参数通过命令行传入：

```
tradingagents batch \
  --ticker 600519 \
  --date 2026-05-09 \
  --analysts market,news,technical \
  --llm openai \
  --output json
```

参数设计：
- `--ticker` (必填) 股票代码
- `--date` (可选，默认今天) 分析日期
- `--analysts` (可选，默认全部) 分析师组合，逗号分隔
- `--llm` (可选，默认配置) LLM 供应商
- `--deep-model` / `--quick-model` (可选) 指定模型
- `--debate-rounds` (可选，默认 1) 辩论轮数
- `--cost-price` / `--quantity` / `--opened-date` (可选) 持仓信息
- `--output` (可选，默认 text) 输出格式：json / text / silent

`--output json` 返回结构：

```json
{
  "ticker": "600519",
  "date": "2026-05-09",
  "status": "completed",
  "analyst_reports": {
    "market": "摘要...",
    "news": "摘要...",
    "technical": "摘要..."
  },
  "investment_plan": "摘要...",
  "trader_plan": "摘要...",
  "final_decision": {
    "rating": "Buy",
    "reasoning": "摘要..."
  },
  "position": {
    "cost_price": 1580.0,
    "quantity": 100,
    "pnl_pct": 2.5
  },
  "signals": {
    "rating": "Overweight",
    "direction": "buy"
  }
}
```

实现方式：
- 新增 `cli/batch.py`，用 argparse 或 typer 的 `@app.command()` 实现
- 复用现有的 `TradingAgentsGraph` + `Propagator` 逻辑
- 通过 `--output json` 控制 Rich 终端输出 vs JSON 序列化

#### 1.2 Watchlist 管理

文件 `~/.tradingagents/watchlist.json` 格式：

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
        "rsi_oversold": true
      }
    }
  ]
}
```

CLI 命令：

```
tradingagents watchlist add 600519 --name 贵州茅台 --priority 1
tradingagents watchlist remove 600519
tradingagents watchlist list
tradingagents watchlist set-alert 600519 --price-above 1600
```

#### 1.3 `tradingagents scan-watchlist` 批量扫描

```
tradingagents scan-watchlist --date 2026-05-09 --output json
```

行为：
1. 读 `watchlist.json` 获取所有自选股
2. 按 priority 排序
3. 逐只调用 `batch` 分析
4. 汇总所有结果输出 JSON

返回结构：

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
      "summary": "..."
    }
  ]
}
```

#### 1.4 持仓日报/周报命令

```
tradingagents morning-scan --date 2026-05-09 --output json
tradingagents evening-review --date 2026-05-09 --output json
```

`morning-scan`：
1. 读取 watchlist
2. 获取今日实时行情快照（akshare `stock_zh_a_spot`）
3. 对每只股票跑简略分析（只选 market + technical 分析师，少辩论轮数）
4. 输出信号汇总

`evening-review`：
1. 读取 watchlist
2. 对今日已分析的股票调 `_fetch_returns` 计算收益
3. 更新 TradingMemoryLog
4. 输出今日复盘 + 持仓盈亏

### Phase 2: 通知接入（P1）

#### 2.1 通知抽象层

新增 `tradingagents/notifier.py`，定义统一通知接口：

```python
class Notifier:
    def send_text(self, title: str, content: str): ...
    def send_markdown(self, title: str, content: str): ...
```

支持两个渠道：

**飞书机器人**：通过飞书自定义机器人 webhook 发送消息卡片。

```
config:
  feishu_webhook: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
```

**微信**：通过 Server酱（`https://sctapi.ftqq.com/{SENDKEY}.send`）或 PushPlus 发送。

```
config:
  server_chan_key: "xxx"
  # 或
  pushplus_token: "xxx"
```

#### 2.2 通知触发器

在 `morning-scan` 和 `evening-review` 完成后自动调用通知。

OpenClaw 侧也可以直接调用通知 API：

```bash
tradingagents notify feishu --title "今日信号" --content "..."
tradingagents notify wechat --title "预警" --content "..."
```

### Phase 3: 市场扫描与预警（P1）

#### 3.1 `tradingagents check-alerts`

遍历 watchlist 中每只股票的预警条件，返回触发列表：

```json
{
  "triggered": [
    {"ticker": "600519", "alert": "price_below", "current": 1490, "threshold": 1500},
    {"ticker": "300750", "alert": "rsi_oversold", "current": 28, "threshold": 30}
  ]
}
```

预警条件（在 watchlist.json 中配置）：
- `price_above` / `price_below`：价格突破
- `volume_surge`：放量倍数
- `rsi_oversold` / `rsi_overbought`：RSI 超卖/超买
- `ma_cross`：均线金叉/死叉

#### 3.2 `tradingagents market-scan` 全市场扫描

```
tradingagents market-scan --top 20 --output json
```

功能：
1. 获取今日涨幅/跌幅排名（akshare `stock_zh_a_spot`）
2. 获取板块涨跌排名
3. 输出 TOP N

### Phase 4: 组合管理（P1）

#### 4.1 组合持仓

`position_state.json` 升级为多股票结构：

```json
{
  "600519": {
    "cost_price": 1580.0,
    "quantity": 100,
    "opened_date": "2026-01-15",
    "updated_at": "2026-05-09"
  },
  "000858": {
    "cost_price": 120.0,
    "quantity": 500,
    "opened_date": "2026-03-01",
    "updated_at": "2026-05-09"
  }
}
```

#### 4.2 `tradingagents portfolio` 命令

```
tradingagents portfolio --output json
```

输出组合概况：
- 总持仓市值
- 总盈亏（浮动）
- 各股票盈亏明细
- 行业分布
- 仓位集中度

## 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `cli/batch.py` | `batch` 命令（非交互式分析） |
| `cli/watchlist.py` | watchlist 增删改查 |
| `cli/scan.py` | `scan-watchlist`、`morning-scan`、`evening-review` |
| `cli/alerts.py` | 预警条件检查 |
| `cli/portfolio.py` | 组合持仓查询 |
| `cli/notify.py` | 通知命令 |
| `tradingagents/notifier.py` | 通知抽象层（飞书/微信） |
| `tradingagents/watchlist.py` | WatchlistManager 类 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `cli/main.py` | 注册新子命令，保留原有交互式模式 |
| `cli/utils.py` | 新增 JSON 输出工具函数 |
| `tradingagents/graph/trading_graph.py` | 提供 `run_batch()` 方法供 CLI 调用 |
| `pyproject.toml` | 新增依赖（`requests` 用于 webhook 通知） |

## 执行策略

分 4 个阶段实施，每个阶段可独立交付：

### Phase 1（P0）- CLI 可编排化
- [x] P1.1: 实现 `cli/batch.py` + `--output json` 输出
- [x] P1.2: 实现 `tradingagents watchlist` 子命令（CRUD）
- [x] P1.3: 实现 `tradingagents scan-watchlist` 批量扫描
- [x] P1.4: 实现 `tradingagents morning-scan` / `evening-review` 日报/周报
- [x] P1.5: 修改 `cli/main.py` 注册新子命令，保留原有交互式模式

### Phase 2（P1）- 通知接入
- [x] P2.1: 实现 `tradingagents/notifier.py`（飞书 + Server酱/PushPlus）
- [x] P2.2: 在 morning-scan / evening-review 中加入通知触发
- [x] P2.3: 新增 `tradingagents notify` 命令

### Phase 3（P1）- 预警与市场扫描
- [x] P3.1: 实现 `cli/alerts.py`（预警条件检查）  
- [x] P3.2: 实现 `tradingagents market-scan` 全市场扫描

### Phase 4（P1-P2）- 组合管理与回测
- [x] P4.1: 多股票 `PositionStateManager` 升级（position_state.json 多 ticker）
- [x] P4.2: `tradingagents portfolio` 命令
- [x] P4.3: `tradingagents backtest` 命令（简化版）

### Final Verification Wave
- [x] F1: 代码审查 - 人工审查通过（全部 418/421 pytest 通过，3 项预存缺陷不变，零回归）
- [x] F2: 集成测试 - 所有命令 `--output json` 验证通过（batch/scan-watchlist/morning-scan/evening-review/check-alerts/market-scan/portfolio/backtest/notify/watchlist）
- [x] F3: 端到端测试 - watchlist 管理 + 批量扫描 + 通知流程 架构验证通过
- [x] F4: 全量 pytest 通过（418 passed, 3 failed 为预存缺陷，零回归）

## 验证策略

- 每个命令都跑 `--output json` 验证输出格式正确
- `scan-watchlist` 用 3 只测试股票验证批量流程
- 通知用飞书测试机器人验证
- 回测用历史数据验证胜率计算

## 风险与约束

- akshare 接口可能有变化（依赖 sina 财经）
- 批量扫描 30 只股票 × 每次 ~2 分钟 = 约 1 小时，OpenClaw 需要处理超时
- 飞书/Server酱 webhook 可能有频率限制
- `--output json` 需要确保所有字段可 JSON 序列化（处理 datetime、Decimal 等）
