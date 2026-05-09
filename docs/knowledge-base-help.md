# TradingAgents 知识库系统使用指南

## 引言

TradingAgents 知识库系统是一个自动累积、结构化存储、按需查询的历史分析管理体系。每次你通过 CLI 运行股票分析，完整的分析结果都会自动保存到磁盘，形成跨天、跨标的的知识积累。

为什么需要这套系统？单一的分析结果只是一次性的 LLM 输出。但当几百次分析累积起来，它们就构成了一个可检索、可反刍的交易知识资产。后续的 AI agent 可以读取历史记录，避免重复计算，从过去的成功和失败中学习。这套系统让每次分析都不是孤立的，而是知识库不断生长的一部分。

## 1. 快速启动

从零开始体验知识库，只需要两步：

第一步，运行一次分析。系统会自动把结果存档。

```bash
tradingagents batch --ticker 600519 --date 2026-05-09 --analysts market,technical --llm openai
```

第二步，查看刚才保存的分析记录。

```bash
tradingagents archive list --ticker 600519 --limit 5
```

如果看到输出中出现了你的分析条目，说明知识库已经开始工作了。多运行几次不同的股票和分析日期，你的知识库就会越来越丰富。

## 2. 分析存档（AnalysisArchive）

### 什么会被保存

每次使用以下命令完成分析后，结果自动写入存档：

- `tradingagents batch` — 单股票全量分析
- `tradingagents morning-scan` — 盘前扫描
- `tradingagents evening-review` — 收盘复盘
- `tradingagents scan-watchlist` — 批量扫描

写入失败不会影响主流程（静默跳过），所以不用担心存档问题阻塞分析。

### 目录结构

存档存储在 `~/.tradingagents/analysis-archive/`，按年/月/日组织：

```
~/.tradingagents/analysis-archive/
├── index.json                          # 全量索引
├── 2026/
│   └── 05/
│       ├── index.json                  # 月索引
│       └── 09/
│           ├── index.json              # 日索引
│           ├── morning-scan_600519.json
│           ├── batch_600519.json
│           ├── evening-review_600519.json
│           └── 2026-05-09_summary.md   # 当日汇总
└── ...
```

每个层级都有 `index.json`，用于快速过滤查询。

### 每条存档的内容

每个 JSON 文件包含以下字段：

| 字段 | 内容 |
|------|------|
| `_meta` | 版本号、存档时间戳、来源命令（batch/morning-scan 等） |
| `request` | 股票代码、分析日期、参与的分析师、LLM 供应商 |
| `market_context` | 实时行情快照（最新价、涨跌幅、成交量等） |
| `analysis` | 各分析师信号汇总、最终决策（Buy/Hold/Sell）、推理过程 |
| `tags` | 自动提取的关键标签，用于搜索 |

### 存档子命令

所有存档操作通过 `tradingagents archive` 命令组完成。

#### 列出条目

按条件筛选存档条目：

```bash
# 列出某只股票最近 10 条记录
tradingagents archive list --ticker 600519 --limit 10

# 只显示 buy 决策的记录
tradingagents archive list --decision buy --days 30

# 只看盘前扫描类型的条目
tradingagents archive list --type morning-scan --limit 5

# 输出 JSON 格式供其他工具处理
tradingagents archive list --ticker 600519 --output json
```

输出示例：

```
找到 3 条记录:
--------------------------------------------------------------------------------
  ID:       2026/05/09/batch_600519
  日期:     2026-05-09
  类型:     batch
  股票:     600519
  决策:     Buy
  标签:     放量突破, MACD金叉
--------------------------------------------------------------------------------
  ID:       2026/05/09/morning-scan_600519
  日期:     2026-05-09
  类型:     morning-scan
  股票:     600519
  决策:     Hold
  标签:     缩量震荡
--------------------------------------------------------------------------------
```

#### 获取完整内容

用条目 ID 获取某次分析的完整 JSON：

```bash
tradingagents archive get 2026/05/09/batch_600519
```

输出会包含完整的分析推理、各分析师信号、市场行情快照等。加上 `--output json` 可输出原始 JSON。

#### 全文搜索

在所有存档条目中搜索关键词，适合模糊查找：

```bash
# 搜索技术面描述
tradingagents archive search "放量突破"

# 搜索决策理由
tradingagents archive search "MACD金叉"

# 搜索市场判断
tradingagents archive search "政策利好"
```

搜索会遍历每条存档的 JSON 内容，所以即使关键词出现在推理文本中也能找到。

#### 信号分布汇总

查看某只股票在一段时间内的历史信号分布：

```bash
tradingagents archive summary 600519 --days 90
```

输出示例：

```
股票:     600519
统计周期: 最近 90 天
总条目数: 12

--- 决策分布 ---
  buy          5  █████
  hold         5  █████
  sell         2  ██

--- 条目类型分布 ---
  batch                 5  █████
  morning-scan          4  ████
  evening-review        3  ███
```

#### 删除条目

误保存或测试数据可以删除：

```bash
tradingagents archive delete 2026/05/09/batch_600519
```

删除后索引会自动更新。

#### 重建索引

如果索引文件损坏（比如手动删除了 JSON 文件导致索引不一致），可以完整重建：

```bash
tradingagents archive rebuild-index
```

这会遍历整个存档目录，重新扫描所有 JSON 文件并重建全部三层索引。数据量大的时候可能需要几秒钟。

### 数据流

从 CLI 命令到可检索的存档，数据流如下：

```
CLI 命令 (batch/morning-scan/...)
    │ 调用 save_to_archive()
    ▼
构建存档格式 JSON (含 _meta, request, analysis, tags)
    │ 以日期/类型/ticker 生成唯一 ID
    ▼
原子写入 YYYY/MM/DD/{type}_{ticker}.json
    │ 增量更新 root/month/day index.json
    ▼
索引就绪，可通过 list/get/search/summary 查询
```

### 与 TradingMemoryLog 的关系

存档系统还有一个孪生兄弟叫 TradingMemoryLog，两者分工不同：

| 维度 | TradingMemoryLog | 分析存档 |
|------|-----------------|---------|
| 存什么 | 决策结果 + LLM 反思（精简） | 完整分析上下文（行情+报告+推理） |
| 谁消费 | AI agent prompt 注入 | 人和 AI 通过 CLI/MCP 查询 |
| 管理方式 | LRU 自动裁剪（只保留最近 N 条） | 持久保留，手工管理 |
| 文件路径 | `~/.tradingagents/memory/trading_memory.md` | `~/.tradingagents/analysis-archive/` |

简单说，TradingMemoryLog 是给 AI agent 看的简短记忆，分析存档是给人（和 AI 工具）查的完整档案。

## 3. 数据缓存层（DataCache）

每次分析都需要获取行情数据。如果没有缓存，同一份数据会被不同分析师重复请求，浪费 API 配额和时间。

### 缓存了什么

| 命名空间 | 存储方式 | 有效期 |
|---------|---------|--------|
| `ohlcv/` | CSV 文件 | 持久化 |
| `benchmark/` | CSV 文件 | 持久化 |
| `fundamentals/` | CSV / JSON 文件 | 持久化 |
| `spot/` | 内存 | 30 秒 |

- OHLCV、基准指数、基本面数据：缓存在磁盘上，一次获取永久使用
- 实时行情快照：缓存在内存中，30 秒后过期，下次请求自动刷新

### 效果

在引入 `DataCache` 之前，一次完整的 `propagate()` 调用会触发 14 次以上的 akshare 请求（各分析师、基准指数、技术指标各取各的）。启用缓存后，同一份数据只下载一次，后续全部命中缓存，调用次数降到 2 次以下。

### 使用方式（代码层面）

```python
from tradingagents.dataflows.cache import DataCache

cache = DataCache("~/.tradingagents/cache")
# 缓存优先：命中返回，未命中调用 fetcher 并自动存入缓存
df = cache.get_or_fetch("benchmark", "000300_2026-05-09.csv", fetcher=fetch_fn)
```

大多数情况下你不需要直接使用 DataCache，因为系统已经自动集成好了。但如果你自己写脚本调用 propagate()，可以通过配置 `enable_archive_first_cache: True`（默认开启）来启用它。

### 清理缓存

如果需要强制刷新数据：

```bash
# 方法一：在 CLI 命令中传入 --refresh-cache（如果支持）
# 方法二：直接删除缓存目录
rm -rf ~/.tradingagents/cache/ohlcv
rm -rf ~/.tradingagents/cache/benchmark
rm -rf ~/.tradingagents/cache/fundamentals
```

## 4. 历史知识注入（ContextAssembly）

每次分析启动时，ContextAssembly 节点会自动收集所有相关的历史知识，打包成一个结构化的知识上下文，注入到各个 AI agent 的 prompt 中。

### 知识上下文的构成

```
propagate(ticker, date)
  │
  ├── 1. DataCache 缓存检查
  ├── 2. 三重缓存检查链（同天跳过 / 增量模式 / 全量）
  ├── 3. ContextAssembly
  │     ├── AnalysisArchive → 同标的最近 5 条分析
  │     ├── TradingMemoryLog → 历史交易决策与盈亏
  │     ├── 信号分布统计（过去 30 天）
  │     ├── 跨标的经验教训（Lessons）
  │     └── Token 预算控制（默认 25000 tokens）
  │
  └── 4-6. Agent 执行（注入历史知识）
```

### 哪些 agent 收到什么

| 智能体 | 注入内容 |
|--------|---------|
| Trader | 历史交易决策 + 每笔的盈亏结果 + 置信度标签 |
| Research Manager | 历史决策上下文（之前怎么看这只股票的） |
| Portfolio Manager | 存档分析摘要 + 跨标的经验教训 |

### 打开或关闭

```python
config = DEFAULT_CONFIG.copy()
config["enable_context_assembly"] = True   # 开启（默认）
config["enable_context_assembly"] = False  # 关闭
```

关闭后，agent 将不会收到任何历史知识，相当于每次都是从零分析。一般情况下保持开启即可。

## 5. 置信度标签体系（Confidence Tags）

AI agent 在参考历史知识时，需要知道每条知识的可靠程度。置信度标签就是给每条历史结论打上的可信度标记。

### 五个等级

| 标签 | 含义 | 加权 |
|------|------|------|
| `CONFIRMED` | 多次独立分析验证（30 天内 3 次以上同向信号） | 最高 |
| `SINGLE` | 只有一次分析记录 | 中 |
| `DERIVED` | 跨标的推理结论（预留） | 中低 |
| `CONFLICTING` | 近期既有买又有卖信号，分析师存在分歧 | 低 |
| `STALE` | 超过 90 天未更新 | 最低 |

### 计算规则

- 如果某股票只有 1 条分析记录 → `SINGLE`
- 如果 30 天内 buy 和 sell 信号同时存在 → `CONFLICTING`
- 如果 30 天内同向信号达到 3 次以上 → `CONFIRMED`
- 如果最新分析超过 90 天 → `STALE`
- 如果分析次数多于 1 次但不足 3 次，且都在 90 天内 → `SINGLE`

### 配置

```python
config["confidence_tags_enabled"] = True         # 开启标签（默认）
config["confidence_threshold_inject"] = "CONFLICTING"  # 低于此等级的结论不注入 prompt
```

`confidence_threshold_inject` 的取值从高到低：`CONFIRMED` > `SINGLE` > `DERIVED` > `CONFLICTING` > `STALE`。默认是 `CONFLICTING`，意思是只有 `CONFLICTING` 及以上等级（包括 `CONFIRMED`、`SINGLE`、`DERIVED`、`CONFLICTING`）的结论才会被注入到 agent prompt，`STALE` 级别的会被过滤掉。

如果 agent 总是忽略历史知识，可以试着降低阈值到 `STALE`。如果历史知识太多导致 prompt 超长，可以提高阈值到 `SINGLE` 或 `CONFIRMED`。

## 6. 三重缓存检查链（Triple Cache Chain）

为了避免不必要的重复分析，系统在 `propagate()` 入口处实现了三级递进检查。

### 三级逻辑

```
Level 1: 同 ticker 同天是否已分析？
    ├── 是 → 直接返回上次的存档结果，跳过整个分析流程
    └── 否 → 进入 Level 2

Level 2: 近 N 天内是否有过分析？
    ├── 是 → 进入增量模式（分析师数量减少，辩论轮次减少）
    └── 否 → 进入 Level 3

Level 3: 无历史 → 全量分析，完成后自动写入存档
```

### 配置

```python
config["skip_if_analyzed_today"] = True    # Level 1：同天跳过
config["incremental_window_days"] = 3      # Level 2：3 天内增量
```

- `skip_if_analyzed_today`：设为 `True` 后，同一天对同一股票的重复调用直接返回上次结果。适合定时任务场景（比如 morning-scan 和 evening-review 在同一天触发但不重复跑）。
- `incremental_window_days`：设为大于 0 的值后，在窗口内的分析会走"轻量模式"。比如设为 3，意味着昨天分析过的股票今天再分析时，不会跑全量分析师，而是只跑市场和技术的简版。

### 实际效果

假设你每天早上 9 点跑 `morning-scan`：

- 第一天（无历史）：全量分析，结果写入存档
- 第二天（在增量窗口内）：增量模式，减少分析师数量
- 同天第二次触发：直接跳过，返回第一次的结果

## 7. Wiki 导航（Knowledge Wiki）

分析存档累积到几十上百条之后，直接翻目录就不太方便了。Wiki 导航系统会自动把存档内容整理成结构化的 Markdown 页面，方便人和 AI agent 浏览。

### 生成 Wiki

```bash
# 全量生成所有股票的分析导航页
tradingagents wiki generate

# 只更新某只股票的页面（增量更新，速度更快）
tradingagents wiki generate --ticker 600519
```

### 查看 Wiki

```bash
# 查看个股详情页
tradingagents wiki show 600519

# 列出所有已生成的页面
tradingagents wiki list
```

### 目录结构

Wiki 页面默认输出到 `~/.tradingagents/wiki/`，包含三个部分：

| 文件 | 内容 |
|------|------|
| `index.md` | 全量索引页。列出所有股票的分析次数、最近信号、置信度标签 |
| `{ticker}.md` | 个股详情页。信号时间线、决策分布、最近 N 条分析 |
| `lessons.md` | 跨标的经验教训汇总。从各次分析中提取的可复用洞察 |

### 为什么不用 RAG

Wiki 是纯 Markdown 文件，没有任何外部依赖。一个 index.md 页大约 2000 tokens，AI agent 读一遍就能知道整个知识库的全貌（有哪些股票、各自什么信号、置信度如何）。相比 RAG 需要向量数据库、embedding 模型、检索管道，Wiki 的零成本浏览模式在 token 开销和部署复杂度上都有优势。

### 增量更新

Wiki 支持增量更新。如果你只新增了一两条分析记录，不需要全量重新生成：

```bash
tradingagents wiki generate --ticker 600519
```

这样只会刷新索引页和贵州茅台的个股详情页，其他股票不受影响。

### 自动生成

```python
config["wiki_auto_generate"] = True  # 每次分析完成后自动更新 Wiki
config["wiki_output_dir"] = "~/.tradingagents/wiki/"  # 输出目录
```

设为 `True` 后，每次 CLI 分析完成后都会自动触发 Wiki 增量更新。

## 8. MCP Server（Model Context Protocol）

MCP（Model Context Protocol）是 AI agent 与知识库之间的标准通信协议。启动 MCP Server 后，你的分析存档就变成了一组可供 AI agent 直接调用的工具。

### 启动服务器

```bash
tradingagents mcp serve
```

MCP Server 以 stdio 模式运行，读取 stdin 的 JSON-RPC 2.0 请求，在 stdout 输出响应。它不打开网络端口，只通过标准输入输出与父进程通信。

### 六个工具

启动后，AI agent 可以通过 function calling 调用以下工具：

| 工具 | 功能 | 一句话场景 |
|------|------|-----------|
| `query_analysis` | 按标的/日期/关键词查询分析记录 | "查一下 600519 近期所有分析" |
| `get_ticker_signals` | 获取某标的的信号分布和趋势 | "茅台最近信号是否一致看多？" |
| `search_patterns` | 搜索反复出现的市场模式 | "历史上缩量突破后怎么走？" |
| `get_lessons` | 获取跨标的经验教训 | "其他股票的教训能否参考？" |
| `get_confidence` | 评估某标的当前信号的可信度 | "当前 Buy 信号可信吗？" |
| `get_graph_neighbors` | 查询知识图谱中的关联节点 | "茅台和哪些行业龙头有关联？" |

### 配置到 Claude Desktop / OpenClaw

在 AI 客户端中配置 MCP Server 地址：

```json
{
  "mcpServers": {
    "trading-knowledge": {
      "command": "python",
      "args": ["-m", "tradingagents.knowledge.mcp_server"],
      "env": {
        "TRADINGAGENTS_ARCHIVE_DIR": "~/.tradingagents/analysis-archive"
      }
    }
  }
}
```

配置完成后，AI agent 就会自动识别到这些工具，在对话中按需调用。

### 传输方式

目前只支持 stdio 模式（标准输入输出）。这意味着 MCP Server 作为子进程被 AI 客户端启动，通过管道通信。不需要配置端口、防火墙或网络权限。

## 9. 图合并（Graph Merge）

TradingAgents 内部有两种知识图谱：

- **代码知识图谱**：由 graphify 从源代码生成的 AST 关系图
- **分析知识图谱**：从分析存档中提取的信号、决策、关联关系图

图合并工具可以将两者合并为统一的查询层。

### 使用方式

```bash
python -m tradingagents.knowledge.mcp_server --merge-graphs \
  graphify-out/graph.json \
  graphify-out/analysis-graph.json \
  --output graphify-out/unified-graph.json
```

合并后的统一图会保留每个节点和边的来源标记（来自代码图还是分析图）。如果一个节点同时出现在两张图中，它的元数据会被合并。

### 为什么有用

合并后，你可以通过 `get_graph_neighbors` 工具做跨域查询。比如某个涨跌停信号在分析图中关联了一个代码中的限价单模块，合并后就可以从一个信号出发，一路追踪到实现该信号的源代码。

### 加载统一图

启动 MCP Server 时通过环境变量加载：

```bash
GRAPH_PATH=graphify-out/unified-graph.json tradingagents mcp serve
```

加载后，`get_graph_neighbors` 工具就可以工作了。

## 10. 完整配置参考

以下是所有与知识库系统相关的配置项及其默认值：

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `knowledge_token_budget` | 25000 | ContextAssembly 知识上下文的 token 预算 |
| `skip_if_analyzed_today` | False | 同 ticker 同天已分析则跳过（Level 1 缓存） |
| `incremental_window_days` | 0 | 增量分析窗口天数（Level 2 缓存，0=禁用） |
| `enable_context_assembly` | True | 是否启用 ContextAssembly 历史知识注入 |
| `enable_archive_first_cache` | True | 是否启用 DataCache 缓存层 |
| `confidence_tags_enabled` | True | 是否启用置信度标签 |
| `confidence_threshold_inject` | CONFLICTING | 最低注入置信度（低于此值的结论被过滤） |
| `graphify_auto_sync` | True | 分析完成后自动更新知识图谱 |
| `mcp_server_enabled` | False | MCP Server 是否随启动自动运行 |
| `wiki_output_dir` | ~/.tradingagents/wiki/ | Wiki 导航页面输出路径 |
| `wiki_auto_generate` | False | 分析完成后自动更新 Wiki |
| `analysis_archive_dir` | ~/.tradingagents/analysis-archive/ | 存档存储路径 |

这些配置在以下位置设置：

```bash
# 通过环境变量覆盖路径
export TRADINGAGENTS_CACHE_DIR=/custom/path/cache
export TRADINGAGENTS_MEMORY_LOG_PATH=/custom/path/memory.md

# 或在 Python 代码中覆盖
from tradingagents.default_config import DEFAULT_CONFIG
config = DEFAULT_CONFIG.copy()
config["skip_if_analyzed_today"] = True
config["incremental_window_days"] = 3
```

## 11. 知识消费双通道

AI agent 消费知识库中的历史知识有两条通道，一条被动一条主动，互为补充。

```
┌────────────────────────────────────────────────────────────────┐
│                       知识消费双通道                            │
├──────────────────────────┬─────────────────────────────────────┤
│  通道 A: Wiki 导航        │  通道 B: MCP 工具调用               │
│  （被动发现）             │  （主动查询）                       │
│                          │                                     │
│  AI agent 读取 Markdown   │  AI agent 通过 function calling     │
│  页面，浏览知识库全貌      │  按需调用具体工具                   │
│                          │                                     │
│  适合场景：                │  适合场景：                         │
│  每次分析的前置步骤        │  深度回溯某一问题                   │
│  快速了解某只股票概况       │  跨标的对比查询                     │
│                          │  搜索特定模式                       │
│  Token 开销：             │  Token 开销：                       │
│  约 2000 tokens/页       │  按需调用，每次调用返回结构化数据     │
│  读 index.md 可知全局     │  精确提取，不做多余工作               │
│                          │                                     │
│  零依赖，纯文件系统        │  需启动 MCP Server 进程             │
└──────────────────────────┴─────────────────────────────────────┘
```

**什么时候用哪个？**

- 每天早上第一次分析前，让 agent 读一遍 index.md 了解全局状况 — 用通道 A
- 分析过程中发现某个信号需要追溯历史，查 600519 过去 30 天的信号分布 — 用通道 B
- 想搜索"历史上出现放量突破后怎么走的" — 用通道 B 的 search_patterns 工具

两个通道可以同时使用。渠道 A 提供低成本的全景视图，渠道 B 提供精准的按需查询。

## 12. 常见问题

### 存档索引损坏了怎么办？

```bash
tradingagents archive rebuild-index
```

这会遍历整个存档目录，从每个 JSON 文件重新提取元信息，重建全部三层索引。原文件不受影响。

### 误保存了一条分析，想删掉？

```bash
tradingagents archive delete 2026/05/09/batch_600519
```

删除后索引会自动更新。如果删错了，重跑一次分析就会重新存档。

### 缓存数据太旧了，怎么刷新？

```bash
# 删除对应命名空间的缓存目录即可
rm -rf ~/.tradingagents/cache/ohlcv
rm -rf ~/.tradingagents/cache/benchmark
```

下次分析时会自动重新下载。或者在支持的命令中使用 `--refresh-cache` 参数。

### AI agent 完全不参考历史知识怎么办？

可能是置信度过滤阈值太高了。尝试调低注入阈值：

```python
config["confidence_threshold_inject"] = "STALE"
```

这样所有等级的历史知识都会被注入。如果 prompt 太长，再逐步提高阈值。

### Wiki 页面和实际存档不一致？

Wiki 是基于存档快照生成的，不会自动同步。两种方式更新：

```bash
# 全量重新生成
tradingagents wiki generate

# 只更新某只股票
tradingagents wiki generate --ticker 600519
```

如果设置了 `wiki_auto_generate: True`，每次分析完成后会自动触发增量更新。

### 存档数据特别多，查询慢？

- 尽量使用 `--ticker` 和 `--days` 参数缩小范围
- `--limit` 默认 20，如果不需要这么多可以设小一些
- 全文搜索 `archive search` 需要遍历所有 JSON 文件，数据量大时速度会慢，这是正常的

### MCP Server 连接不上？

确认以下几点：

1. MCP Server 是否正在运行：`tradingagents mcp serve`
2. AI 客户端配置中的命令路径是否正确（见第 8 节配置示例）
3. 存档目录是否存在且有数据：`ls ~/.tradingagents/analysis-archive/index.json`
4. MCP 工具只在 AI agent 决定调用时启用，不是自动运行的

### 测试环境和生产环境的存档路径不同？

通过 `TRADINGAGENTS_ARCHIVE_DIR` 环境变量切换：

```bash
# 测试环境
export TRADINGAGENTS_ARCHIVE_DIR=/tmp/test-archive
tradingagents batch --ticker 600519 --date 2026-05-09

# 生产环境
unset TRADINGAGENTS_ARCHIVE_DIR
tradingagents batch --ticker 600519 --date 2026-05-09
```

也可以把存档目录软链接到网络存储，实现多机共享。
