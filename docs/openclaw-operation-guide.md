# OpenClaw Agent 操作指南：TradingAgents V1.2

> 本文档面向 OpenClaw 编排 agent，描述如何通过 HTTP API 与 TradingAgents V1.2 交互。
> V1.2 已将交互模式从 CLI 升级为 FastAPI HTTP 服务，支持自然语言消息和智能调度。

---

## 一、快速索引

| 接口 | 方法 | 用途 | 是否需要 LLM API |
|------|------|------|:---:|
| `/analyze` | POST | 自然语言消息 → 智能分析 | ✅ 需要 |
| `/health` | GET | 服务状态检查 | ❌ |
| `tradingagents batch` | CLI | 单股票深度分析（兼容保留） | ✅ 需要 |
| `tradingagents check-alerts` | CLI | 预警条件检查 | ❌ |
| `tradingagents portfolio` | CLI | 持仓组合概览 | ❌ |
| `tradingagents watchlist` | CLI | 自选股管理 | ❌ |
| `tradingagents notify` | CLI | 主动推送通知 | ❌ |

**核心变更**：V1.2 的智能分析全部走 `POST /analyze`。CLI 命令保留用于纯数据查询和管理操作。

---

## 二、HTTP API

### 2.1 `POST /analyze` — 分析请求

向 TradingAgents 发送自然语言消息，LLM Planner 自动理解意图、查询知识库、选择模板、调度 Agent。

**请求**：

```http
POST /analyze HTTP/1.1
Host: tradingagents:8000
Content-Type: application/json

{
  "user_id": "alice",
  "message": "茅台最近走势分析",
  "ticker": "600519",
  "platform": "wechat"
}
```

**参数**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `user_id` | string | 否 | 用户标识（默认 `"default"`） |
| `message` | string | 是 | 自然语言消息，Planner 据此理解意图 |
| `ticker` | string | 否 | 股票代码，可辅助 Planner 准确路由 |
| `platform` | string | 否 | 来源平台（`wechat`/`telegram`/`discord`） |

**响应（200）**：

```json
{
  "report": "## 贵州茅台（600519）分析报告\n\n### 技术面\n...\n\n### 最终建议\n**买入**，目标价 1750，止损 1550",
  "intent": "standard_analysis",
  "generation_mode": "template_exact",
  "template_id": "tpl_standard_analysis",
  "estimated_cost_usd": 0.30,
  "workflow_steps": 6
}
```

**响应字段**：

| 字段 | 说明 |
|------|------|
| `report` | Markdown 格式的完整分析报告 |
| `intent` | Planner 判定的意图类型 |
| `generation_mode` | 生成模式（见下表） |
| `workflow_steps` | 执行的 Agent 步骤数 |

**生成模式**：

| `generation_mode` | 含义 | 说明 |
|------|------|------|
| `template_exact` | 精确模板匹配 | KB 覆盖率高，仅补缺失部分 |
| `template_refined` | 模糊匹配优化 | 类似场景模板调整后使用 |
| `llm_full` | LLM 完整规划 | 无匹配模板，LLM 从零生成方案 |
| `llm_fallback` | 降级模式 | LLM 调用失败，使用最小方案 |

**响应（503）**：服务未完全初始化时返回。

**典型响应时间**：45 秒（有 KB 支撑）到 3 分钟（完整分析），取决于 Agent 步骤数和 LLM 速度。

### 2.2 `GET /analyze` — 便捷 GET 方式

```http
GET /analyze?user_id=alice&message=茅台怎么样&ticker=600519
```

返回格式与 POST 相同。适用于无法发送请求体的场景。

### 2.3 `GET /health` — 服务状态

```http
GET /health
```

```json
{"status":"ok", "kb_entries":42, "user_count":3}
```

| 字段 | 说明 |
|------|------|
| `kb_entries` | 知识库条目总数 |
| `user_count` | 活跃用户数 |

---

## 三、OpenClaw 配置

### 3.1 Advisor Agent — HTTP 调用

在 OpenClaw 的 Advisor Agent 配置中，将 `call_tradingagents_analyze` 工具从 CLI 改为 HTTP POST：

```yaml
# OpenClaw Advisor Agent 配置
tools:
  - name: call_tradingagents_analyze
    description: "将用户消息发送到 TradingAgents 分析引擎进行智能分析"
    http:
      method: POST
      url: "http://tradingagents:8000/analyze"
      headers:
        Content-Type: "application/json"
      body:
        user_id: "{{session.user_id}}"
        message: "{{input}}"
        ticker: "{{extracted_ticker}}"
        platform: "{{session.platform}}"
```

### 3.2 Webhook 接收定时报告

TradingAgents 定时任务（晨会/午评/收盘/周选股）完成后通过 OpenClaw Webhook 推送到用户渠道。

**OpenClaw 侧配置** — `openclaw.json`：

```json5
{
  hooks: {
    enabled: true,
    token: "shared-secret-token",
    path: "/hooks"
  }
}
```

**环境变量**（在 TradingAgents 侧设置）：

```bash
OPENCLAW_URL=http://openclaw:18789
OPENCLAW_HOOK_TOKEN=shared-secret-token
```

### 3.3 docker-compose 联调

```yaml
services:
  openclaw:
    image: ghcr.io/openclaw/openclaw:latest
    ports: ["18789:18789"]
    volumes: ["./config/openclaw:/app/config:ro"]

  tradingagents:
    build: .
    ports: ["8000:8000"]
    environment:
      - OPENCLAW_URL=http://openclaw:18789
      - OPENCLAW_HOOK_TOKEN=${OPENCLAW_HOOK_TOKEN}
    volumes:
      - tradingagents_data:/home/appuser/.tradingagents
```

---

## 四、定时报告

V1.2 内置双层调度器，自动推送报告到 OpenClaw：

| 报告 | 时间 | 频率 | 内容 |
|------|------|------|------|
| 晨报 | 08:50 | 每个交易日 | 隔夜外盘 + 持仓预警 + 今日关注 |
| 午评 | 12:00 | 每个交易日 | 盘中异动 + 偏离度检查 |
| 收盘复盘 | 15:10 | 每个交易日 | 持仓盈亏 + 明日预案 |
| 周选股 | 09:00 | 每周日 | 行业扫描 + 基本面确认 |

报告通过 OpenClaw Webhook 的 `/hooks/agent` 端点推送，格式为 Markdown，包含持仓预警表和操作建议。

---

## 五、CLI 命令（兼容保留）

以下纯数据操作命令保留 CLI 模式，不依赖 LLM Planner：

### 5.1 自选股管理

```bash
tradingagents watchlist add 600519 --name "贵州茅台" --priority 1
tradingagents watchlist list --output json
tradingagents watchlist remove 600519
```

### 5.2 预警检查

```bash
tradingagents check-alerts --date 2026-05-13 --output json
```

### 5.3 持仓概览

```bash
tradingagents portfolio --date 2026-05-13 --output json
```

### 5.4 全市场扫描

```bash
tradingagents market-scan --top 20 --output json
```

### 5.5 分析存档查询

```bash
tradingagents archive list --ticker 600519 --limit 10
tradingagents archive search "放量突破"
```

### 5.6 通知推送

```bash
tradingagents notify feishu --title "预警触发" --content "600519 跌破 1500"
```

---

## 六、数据文件

### 6.1 持仓文件 `~/.tradingagents/users/{user_id}/portfolio/portfolio.yaml`

```yaml
holdings:
  - ticker: "600519"
    name: "贵州茅台"
    cost_price: 1580.0
    quantity: 100
    entry_date: "2026-01-15"
watchlist:
  - ticker: "000858"
    name: "五粮液"
    reason: "等待回调"
risk_profile:
  max_single_stock_pct: 20
  max_drawdown_tolerance: -15
```

### 6.2 知识库 `~/.tradingagents/kb/`

```
shared/
├── market_snapshot/     # 市场快照（所有用户共享）
├── policy_brief/        # 政策简报（所有用户共享）
└── sentiment_report/    # 舆情报告（所有用户共享）
users/{user_id}/
└── stock_snapshot/      # 个股快照（用户专属）
```

### 6.3 分析存档 `~/.tradingagents/users/{user_id}/analysis-archive/`

每次分析自动写入，按年月日分层存储 JSON。

---

## 七、OpenClaw 典型工作流

### 工作流 A：用户交互（实时）

```
用户消息 "茅台最近怎么样"
  → OpenClaw Advisor Agent
    → POST /analyze {user_id, message, ticker}
      → LLMPlanner 查 KB → 选模板 → 动态图构建
        → Agent 执行（只跑 KB 缺失部分）
      ← 返回分析报告
    → 推送给用户
```

**OpenClaw Agent 伪代码**：

```
function handle_user_message(msg):
    ticker = extract_ticker(msg.content)   // "茅台" → "600519"
    response = http_post("http://tradingagents:8000/analyze", {
        user_id: session.user_id,
        message: msg.content,
        ticker: ticker,
    })
    return format_report(response.report)
```

### 工作流 B：定时报告（自动）

```
08:50 交易日
  → APScheduler 触发 _morning_briefing
    → 遍历活跃用户 → 查 KB → Planner 规划 → 执行
      → 生成晨报
    → POST http://openclaw:18789/hooks/agent
      → OpenClaw 投递到用户渠道
```

无需 OpenClaw 侧额外操作——定时报告完全由 TradingAgents 发起。

### 工作流 C：批量预警（建议保留 CLI）

```bash
# 检查预警
alerts=$(tradingagents check-alerts --output json)

# 对触发的股票发送给 /analyze
for ticker in $(echo $alerts | jq -r '.triggered[].ticker'); do
  curl -X POST http://tradingagents:8000/analyze \
    -H "Content-Type: application/json" \
    -d "{\"message\":\"$ticker 预警触发，请分析\",\"ticker\":\"$ticker\"}"
done
```

---

## 八、错误处理

| 场景 | HTTP 状态码 | 说明 |
|------|:---:|------|
| 正常完成 | 200 | `report` 字段含完整报告 |
| 服务初始化中 | 503 | Executor 未配置，设置 API Key 后重启 |
| LLM 调用失败 | 200 | `report` 为空，`generation_mode` 降级 |

---

## 九、已知限制

| 限制 | 说明 |
|------|------|
| **LLM 依赖** | `/analyze` 需要有效 LLM API Key |
| **采集层依赖** | 后台采集需要 AkShare 网络连接 |
| **guosen 限制** | 国信证券每个 API Key 限制 50 次/Key |
| **无分钟级数据** | 仅支持日线 OHLCV，实时行情为快照 |
| **T+1 约束** | A 股模式下开仓当日不可卖出 |

---

## 十、版本信息

- 适用版本：V1.2+
- 最后更新：2026-05-13
- 计划文档：`.sisyphus/plans/v1-llm-planner.md`
