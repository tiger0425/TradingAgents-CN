# AI 知识消费实施计划 — 让知识库被 AI 发现、使用、节省算力

## 摘要

在已有知识库存储体系（analysis-archive + graphify + notepads）之上，解决三个核心问题：
1. **发现** — AI 如何知道有可用的历史知识（prompt 注入 + MCP 工具调用双通道）
2. **消费** — 历史知识如何注入到每个 agent 的推理过程（ContextAssembly + Wiki 导航）
3. **节省** — 如何用历史知识替代冗余外部调用，减少 LLM 重复计算

**借鉴 graphify v7 的 8 个生产模式**：
- MCP Server 暴露知识库为 AI 可调用的工具
- Wiki 模式生成 agent 可导航的 Markdown 索引（低成本替代 RAG）
- Confidence 标签（EXTRACTED/INFERRED/AMBIGUOUS）追踪分析结论可信度
- Auto-Sync 在每次分析后自动增量更新知识图谱
- Graph Merge 合并代码图 + 分析图为统一查询层
- Token Reduction 将 100 条历史分析压缩到 ~8K tokens
- God Nodes 发现龙头 ticker 和高影响力分析模式
- 增量更新只处理新增分析，不重做已归档内容

## 背景

当前状态的关键发现（来自对 propagate() 全流程的代码审计）：

- `AgentState.past_context` 仅在初始化时注入一次，**仅 Portfolio Manager** 读取
- 其他 8 个 agent（Market/News/Fundamentals/Social Analyst, Bull/Bear Researcher, Research Manager, Trader, Risk Analysts）**完全无历史视野**
- `trading_graph.py` 中有 **4 处无缓存 akshare 调用**，每次 propagate() 重复
- 基准指数数据（`ak.stock_zh_index_daily`）**完全无缓存**
- CLI 层 4 个命令独立调用 `ak.stock_zh_a_spot()` 全市场下载，**彼此不共享缓存**

## 目标

1. 建立 ContextAssembly 节点，在每次分析启动时自动装配全部可用历史知识
2. 将历史知识注入从 PM-only 扩展到 Trader + Research Manager + Analysts
3. 消除 trading_graph.py 中冗余的 akshare 调用
4. 实现三重缓存检查链，避免同 ticker 同天重复分析
5. 暴露分析知识库为 MCP Server，让 AI agent 通过工具调用主动查询（graphify serve 模式）
6. 自动生成 Wiki 导航索引，提供低成本的 agent 知识发现路径
7. 为分析结论打 Confidence 标签，跨分析汇总时区分可信度
8. 实现 graphify Auto-Sync：每次分析完成后自动增量更新知识图谱
9. 所有改动不破坏向后兼容性

## 范围

### 纳入范围

- `tradingagents/graph/trading_graph.py` — propagate() 流程改动
- `tradingagents/graph/context_assembly.py` — 新建 ContextAssembly 节点
- `tradingagents/agents/utils/agent_states.py` — AgentState 扩展（含 confidence 字段）
- `tradingagents/agents/trader/trader.py` — Trader prompt 注入
- `tradingagents/agents/managers/research_manager.py` — RM prompt 注入
- `tradingagents/agents/managers/portfolio_manager.py` — PM prompt 增强
- `tradingagents/dataflows/akshare.py` — 缓存统一
- `tradingagents/dataflows/cache.py` — 新建统一缓存层
- `tradingagents/knowledge/wiki_generator.py` — 新建 Wiki 导航生成器（借鉴 graphify --wiki）
- `tradingagents/knowledge/mcp_server.py` — 新建 MCP Server（借鉴 graphify serve）
- `tradingagents/default_config.py` — 新增配置项
- `cli/portfolio.py`, `cli/scan.py`, `cli/alerts.py`, `cli/market_scan.py` — CLI 缓存统一
- `cli/` — 新增 `tradingagents wiki` 和 `tradingagents mcp` 命令
- `tests/` — 全部测试

### 不纳入范围

- ChromaDB / 向量数据库集成（后续 Phase）
- graphify 语料扩展（已在知识库设计计划中）
- 每日分析日志模板（已在知识库设计计划中）
- 交易策略本身的修改

## 技术决策

### ADR-005: ContextAssembly 作为独立节点而非嵌入现有节点

**背景**: 历史知识装配涉及多个数据源（archive、memory、lessons、cache），逻辑独立。

**决策**: 新建 `tradingagents/graph/context_assembly.py`，作为 propagate() 中的独立步骤，在 `create_initial_state()` 之前执行。

**理由**:
- 职责单一，易于测试
- 不污染现有 agent 逻辑
- 可独立开关（通过配置控制）

### ADR-006: AgentState 使用结构化字典而非拼接字符串

**背景**: 不同 agent 需要不同切片的历史知识（trader 要交易记录，analyst 要信号汇总）。

**决策**: `knowledge_context` 字段为 `dict`，不同 agent 自行提取所需部分。

```python
knowledge_context = {
    "archived_analyses": [...],   # 存档分析列表
    "past_decisions": [...],       # 交易决策历史
    "ticker_signals": {...},       # 信号分布统计
    "lessons": [...],              # 跨 ticker lessons
    "cache_status": {...},         # 数据缓存状态
}
```

**理由**:
- 灵活：不同 agent 取不同切片
- 可测：每个 agent 的消费逻辑独立测试
- 可扩展：新增知识源不影响已有 consumer

### ADR-007: 缓存层用磁盘 + 命名空间，不引入外部依赖

**背景**: 需要统一的缓存策略，覆盖 OHLCV、基准指数、财务数据。

**决策**: 在 `tradingagents/dataflows/cache.py` 中实现统一缓存层，使用 JSON/CSV 文件 + 命名空间。

```
~/.tradingagents/cache/
├── ohlcv/             # OHLCV 数据（已有，统一文件名格式）
├── benchmark/         # 基准指数数据（新增）
│   └── 000300_2026-05.csv
├── fundamentals/      # 财务数据（新增）
│   └── 600519_balance_sheet_2026Q1.csv
└── spot/              # 实时行情（内存 TTL，30 秒）
```

**理由**:
- 零外部依赖，与项目现有模式一致
- 基准指数数据是最大的缺失（每次 propagate 都重新下载）
- 文件名编码请求参数，天然防冲突

### ADR-008: 双重知识消费通道（Prompt 注入 + MCP 工具调用）

**背景**: 历史知识可以预注入到 prompt 中（被动），也可以通过 MCP 工具让 agent 主动查询（主动）。借鉴 graphify 的 MCP Server 模式。

**决策**: 同时实现两种通道：
- **Prompt 注入**（ContextAssembly）：高频/小量历史知识，在分析启动时注入到 agent prompt
- **MCP 工具调用**（`tradingagents mcp serve`）：低频/大量/复杂查询，让 agent 通过 function calling 按需调用

**理由**:
- Prompt 注入适合"每次分析必用的知识"（最近 N 天信号汇总），token 成本可控
- MCP 工具适合"偶尔才需要查的知识"（跨 ticker 模式、3 个月前的某次分析详情），不浪费 prompt 空间
- 两个通道互补，AI agent 自己决定什么时候用哪个

### ADR-009: Confidence 标签体系（借鉴 graphify EXTRACTED/INFERRED/AMBIGUOUS）

**背景**: 历史分析结论质量参差不齐。需要让 AI 知道哪些结论可信，哪些仅供参考。

**决策**: 每次分析结论标注置信度标签：

| 标签 | 含义 | 例子 |
|------|------|------|
| `CONFIRMED` | 多次分析独立验证的结论 | "600519 连续 5 次分析看多" |
| `SINGLE` | 单次分析结论，未验证 | "某次 batch 分析的 Buy 信号" |
| `CONFLICTING` | 多次分析意见分歧 | "3 次看多 vs 2 次看空" |
| `STALE` | 超过 90 天未更新的结论 | "3 个月前的技术面判断" |
| `DERIVED` | 跨 ticker 推理的结论 | "从 000858 模式类推到 600519" |

**理由**: 直接借鉴 graphify 的置信度体系，让 AI agent 在注入/查询历史知识时自动加权——CONFIRMED > SINGLE > DERIVED > CONFLICTING > STALE。

### ADR-010: Wiki 导航作为 RAG 的轻量替代

**背景**: 分析存档积累到数百条后，需要一种方式让 AI agent 快速了解"知识库里有什么"，再决定深入查什么。graphify 的 `--wiki` 模式已证明这种方案可行。

**决策**: 自动为分析存档生成一组 Markdown 导航文章：
- `wiki/index.md`：所有 ticker 的分析概览索引
- `wiki/{ticker}.md`：单个 ticker 的分析历史和信号分布
- `wiki/patterns/{pattern}.md`：反复出现的市场模式
- `wiki/lessons.md`：跨 ticker 的经验教训

**理由**:
- 零外部依赖（不需要 embedding / vector DB）
- Token 极度友好：agent 读 `index.md` 就知道知识库全貌
- 与 graphify 的 `--wiki` 模式完全对齐，可复用其生成思路
- 比 RAG 实现快 10 倍以上，且结果可复现

## 系统架构

```
propagate(ticker, date, ...)
  │
  ├── 1. Archive-First 检查（缓存层）
  │     ├── check_disk_cache() → OHLCV / 基准 / 财务
  │     └── check_spot_cache() → 实时行情 TTL
  │
  ├── 2. 三重缓存检查链（同 ticker 分析）
  │     ├── Level 1: 同天已分析？→ 直接返回
  │     ├── Level 2: 3天内分析过？→ 增量模式
  │     └── Level 3: 无历史 → 全量分析
  │
  ├── 3. ContextAssembly（新增）
  │     ├── query_archive() → 存档分析（含 Confidence 标签加权）
  │     ├── query_memory() → 交易记忆
  │     ├── query_lessons() → Lessons
  │     ├── query_graph()  → 知识图谱（graphify graph.json 查询）
  │     ├── token_budget() → Token 预算控制
  │     └── → AgentState.knowledge_context
  │
  ├── 4. create_initial_state()（已有，扩展）
  │     └── 携带 knowledge_context（含 confidence 字段）
  │
  ├── 5. graph.invoke()（已有，扩展）
  │     ├── Trader        ← 新增: past_decisions
  │     ├── Research Mgr  ← 新增: past_decisions
  │     ├── PM            ← 增强: archived_analyses
  │     └── 其他 agent    ← 可选: wiki 导航索引
  │
  └── 6. Post-Analysis（增强）
        ├── archive.save() → 本次分析
        ├── memory.store() → 决策（已有）
        ├── lessons.store() → Lessons（可选）
        └── graphify update . → 自动增量更新知识图谱（借鉴 Auto-Sync）

═══════════════════════════════════════════════════════════
                       知识消费双通道
═══════════════════════════════════════════════════════════

通道 A: Prompt 注入（高频，被动）
  每日分析启动时，ContextAssembly 自动装配历史知识
  → 注入到 AgentState.knowledge_context
  → 各 agent prompt 中按需提取
  适合: 最近 N 天信号汇总、历史决策经验

通道 B: MCP 工具调用（低频，主动）
  AI agent 通过 function calling 调用 MCP 工具
  → query_analysis("600519", "2026-05")  
  → get_ticker_signals("600519")
  → search_patterns("缩量突破")
  适合: 跨 ticker 模式查询、历史详情回溯

═══════════════════════════════════════════════════════════
                       graphify 集成
═══════════════════════════════════════════════════════════

graphify-out/
├── graph.json              ← 代码知识图谱（已有）
├── analysis-graph.json     ← 分析知识图谱（新建，分析存档经 graphify 提取）
└── unified-graph.json      ← 合并后的统一图谱（graphify merge-graphs）
       │
       ├── MCP Server (python -m graphify.serve unified-graph.json)
       │     └── query_graph / get_node / get_neighbors / shortest_path
       │
       ├── Wiki 导航（tradingagents wiki generate）
       │     └── wiki/index.md + wiki/{ticker}.md + wiki/patterns/
       │
       └── God Nodes / Surprising Connections（graph analyze）
             └── 挖掘龙头 ticker、跨市场模式
```

## 模块设计

### 1. `tradingagents/dataflows/cache.py` — 统一缓存层

```python
class DataCache:
    """
    统一数据缓存层：先查缓存，再调 API。
    
    命名空间:
    - ohlcv/{ticker}_{start}_{end}.csv
    - benchmark/{ticker}_{date}.csv
    - fundamentals/{ticker}_{type}_{date}.csv
    """

    def __init__(self, cache_dir: str):
        self._cache_dir = Path(cache_dir)

    def get(self, namespace: str, key: str) -> Optional[Any]:
        """读缓存。存在即返回，不存在返回 None。"""

    def set(self, namespace: str, key: str, data: Any) -> None:
        """写缓存。原子写入。"""

    def get_or_fetch(
        self, namespace: str, key: str,
        fetcher: Callable[[], Any],
        ttl: Optional[int] = None,
    ) -> Any:
        """缓存优先：先查缓存，miss 则调 fetcher 并写入。"""

    def invalidate(self, namespace: str, key: str) -> None:
        """手动失效（如 --refresh-cache）。"""
```

### 2. `tradingagents/graph/context_assembly.py` — ContextAssembly 节点

```python
class ContextAssembler:
    """
    上下文装配器：在每次分析启动时收集所有可用历史知识。
    
    职责:
    - 查询存档分析（archive）
    - 查询交易记忆（memory）
    - 查询 lessons（跨 ticker 洞察）
    - Token 预算控制
    """

    MAX_HISTORY_TOKENS = 25000  # 可配置

    def __init__(self, config: dict):
        self.archive = AnalysisArchive(config)
        self.memory = TradingMemoryLog(config)
        self._budget = config.get("knowledge_token_budget", self.MAX_HISTORY_TOKENS)

    def assemble(
        self,
        ticker: str,
        date: str,
        market_type: str = "A_SHARE",
    ) -> dict:
        """装配所有可用的历史知识，返回结构化字典。"""
        context = {
            "archived_analyses": self._get_archived_analyses(ticker, date),
            "past_decisions": self._get_past_decisions(ticker),
            "ticker_signals": self._get_ticker_signal_summary(ticker),
            "lessons": self._get_relevant_lessons(ticker, market_type),
            "cache_status": self._get_data_cache_status(ticker),
        }
        # Token 预算裁剪
        self._apply_budget(context)
        return context

    def _get_archived_analyses(self, ticker: str, date: str, limit: int = 5) -> list:
        """从 analysis-archive 获取同 ticker 历史分析。"""
        return self.archive.list(ticker=ticker, end_date=date, limit=limit)

    def _get_past_decisions(self, ticker: str) -> str:
        """从 TradingMemoryLog 获取历史决策记录。"""
        return self.memory.get_past_context(ticker, n_same=5, n_cross=3)

    def _get_ticker_signal_summary(self, ticker: str, days: int = 30) -> dict:
        """从存档统计过去 N 天的信号分布。"""
        entries = self.archive.list(ticker=ticker, days_back=days)
        return self._summarize_signals(entries)

    def _get_relevant_lessons(self, ticker: str, market_type: str, limit: int = 3) -> list:
        """从 lessons 库获取跨 ticker 洞察。"""
        return self.archive.get_lessons(ticker=ticker, market_type=market_type, limit=limit)

    def _apply_budget(self, context: dict) -> None:
        """按 token 预算裁剪历史知识。"""
        # 优先级: past_decisions > archived_analyses > lessons
        # 超出预算时从低优先级开始裁剪
        ...
```

### 3. AgentState 扩展

```python
# tradingagents/agents/utils/agent_states.py

class AgentState(MessagesState):
    # ... 现有字段 ...

    # 新增
    knowledge_context: Annotated[
        dict,
        "Structured knowledge context assembled at run start. "
        "Contains archived_analyses, past_decisions, ticker_signals, lessons. "
        "Each agent extracts what it needs.",
    ] = {}
```

### 4. Trader prompt 注入

```python
# tradingagents/agents/trader/trader.py — 修改 trader_node()

def trader_node(state: AgentState):
    # ... 现有代码 ...

    # 新增: 历史交易决策注入
    past_decisions = state.get("knowledge_context", {}).get("past_decisions", "")
    if past_decisions:
        history_section = (
            "\n\n**历史交易经验（来自过往决策）：**\n"
            f"{past_decisions}\n\n"
            "请参考以上历史交易的盈亏结果，避免重复过去的错误。"
        )
        user_msg = user_msg.replace(
            "请基于上述信息", f"{history_section}\n\n请基于上述信息"
        )

    # ... 后续流程 ...
```

### 5. 三重缓存检查链

```python
# tradingagents/graph/trading_graph.py — 修改 propagate()

def propagate(self, ticker, date, ...):
    """存档优先 + 三重缓存检查。"""

    # ★ Level 1: 同天同 ticker 已分析？→ 直接返回
    if self.config.get("skip_if_analyzed_today", False):
        cached = self.archive.get(ticker=ticker, date=date, entry_type="batch")
        if cached:
            logger.info(f"[Cache L1] {ticker} on {date} already analyzed, returning cached")
            return cached["final_state"], cached["decision"]

    # ★ Level 2: 近 N 天有分析？→ 增量模式
    incremental_days = self.config.get("incremental_window_days", 0)
    if incremental_days > 0:
        recent = self.archive.list(ticker=ticker, date_from=date, days_back=incremental_days)
        if recent:
            logger.info(f"[Cache L2] {ticker} recent analysis found, incremental mode")
            config["__incremental_mode__"] = True
            config["__recent_analyses__"] = recent

    # ★ Level 3: 正常全量分析
    result = self._run_full_analysis(ticker, date, config, ...)

    # ★ Post-analysis: 写入存档
    self.archive.save(result, entry_type="batch", ticker=ticker, date=date)
    return result
```

### 6. 消除 trading_graph.py 冗余 akshare 调用

```python
# tradingagents/graph/trading_graph.py — 改动4处

# ① _get_ashare_close_series() (行257)
# 改前: ak.stock_zh_a_daily(symbol) 每次都调
# 改后: 用 _load_ohlcv_akshare() 已有缓存

def _get_ashare_close_series(self, symbol, start, end):
    df = _load_ohlcv_akshare(symbol, start, end)
    return df[["date", "close"]].copy()

# ② _get_ashare_benchmark_close_series() (行284)
# 改前: ak.stock_zh_index_daily() 完全无缓存
# 改后: 走 DataCache

def _get_ashare_benchmark_close_series(self, symbol, start, end):
    cache = DataCache(self.config.get("data_cache_dir"))
    return cache.get_or_fetch(
        namespace="benchmark",
        key=f"{symbol}_{start}_{end}",
        fetcher=lambda: ak.stock_zh_index_daily(symbol=symbol),
    )

# ③ 限价计算循环 (行423)
# 改前: for _ in range(14): ak.stock_zh_a_daily()
# 改后: 一次 _load_ohlcv_akshare() 读取

# ④ _get_analysis_day_close() (行578)
# 改前: ak.stock_zh_a_daily()
# 改后: 从已加载的 DataFrame 取值
```

### 8. `tradingagents/knowledge/wiki_generator.py` — Wiki 导航生成器

借鉴 graphify `--wiki` 模式，为分析存档自动生成 Markdown 导航索引。

```python
class WikiGenerator:
    """
    Wiki 导航生成器：为分析存档生成 agent-crawlable Markdown 索引。

    借鉴 graphify --wiki 的设计：不引入外部依赖，
    用纯 Markdown 文件构建知识导航体系。

    生成产物:
    - wiki/index.md          # 全量索引：所有 ticker 的分析概览
    - wiki/{ticker}.md       # ticker 详细页：历史信号分布、关键结论
    - wiki/patterns/{name}.md # 模式页：反复出现的市场行为模式
    - wiki/lessons.md        # 经验教训页：跨 ticker 的可复用洞察
    """

    def generate(self, archive_dir: str, output_dir: str) -> str:
        """生成完整 Wiki。返回 index.md 路径。"""

    def _build_index(self, entries: List[dict]) -> str:
        """构建顶层索引页。Agent 读这个文件就知道知识库全貌。"""

    def _build_ticker_page(self, ticker: str, entries: List[dict]) -> str:
        """构建单个 ticker 详情页。含信号分布、置信度标签、时间线。"""

    def _build_pattern_page(self, pattern: str, entries: List[dict]) -> str:
        """构建模式页。自动聚合同类市场行为。"""

    def _build_lessons_page(self, lessons: List[dict]) -> str:
        """构建跨 ticker 经验教训页。"""

    def incremental_update(self, new_entries: List[dict]):
        """增量更新：只更新有变化的页面，不重建整个 Wiki。"""
```

**Wiki 页面示例** (`wiki/index.md`)：

```markdown
# 分析知识库导航

## 股票分析索引

| Ticker | 名称 | 总分析次数 | 最近分析 | 当前信号 | 置信度 |
|--------|------|-----------|---------|---------|-------|
| 600519 | 贵州茅台 | 47 | 2026-05-09 | Hold | CONFIRMED (5/5) |
| 000001 | 平安银行 | 32 | 2026-05-08 | Buy | SINGLE |
| ... | ... | ... | ... | ... | ... |

## 反复出现的市场模式
- [[缩量突破后回踩]] (12 次)
- [[MACD 底背离后反弹]] (8 次)
- [[财报前资金抢跑]] (5 次)

## 可用命令
- `tradingagents archive search "放量突破"` — 全文搜索
- `tradingagents wiki show 600519` — 查看 ticker 详情
- `tradingagents mcp serve` — 启动 MCP Server
```

### 9. `tradingagents/knowledge/mcp_server.py` — MCP Server

借鉴 graphify `serve.py`，暴露分析知识库为 MCP 工具，让 AI agent 通过 function calling 主动查询。

```python
class KnowledgeMCPServer:
    """
    将分析知识库暴露为 MCP (Model Context Protocol) 工具。

    借鉴 graphify serve 的设计：
    - query_analysis: 按 ticker/日期/关键词查询分析记录
    - get_ticker_signals: 获取某 ticker 的历史信号分布
    - search_patterns: 搜索反复出现的市场模式
    - get_lessons: 获取跨 ticker 经验教训
    - get_confidence: 获取某 ticker 当前信号的置信度
    - get_graph_neighbors: 查询知识图谱中的关联节点

    启动方式:
      tradingagents mcp serve
      # 或
      python -m tradingagents.knowledge.mcp_server
    """

    def __init__(self, archive: AnalysisArchive, graph_path: str = None):
        self.archive = archive
        self.graph = self._load_graph(graph_path) if graph_path else None

    # --- MCP 工具定义 ---

    def tool_query_analysis(self, ticker: str = None, date: str = None,
                            keyword: str = None, limit: int = 10) -> list:
        """查询分析记录。"""

    def tool_get_ticker_signals(self, ticker: str, days: int = 90) -> dict:
        """获取某 ticker 的历史信号分布和趋势。"""

    def tool_search_patterns(self, description: str, limit: int = 5) -> list:
        """搜索反复出现的市场行为模式。"""

    def tool_get_lessons(self, ticker: str = None, market: str = None) -> list:
        """获取跨 ticker 经验教训。"""

    def tool_get_confidence(self, ticker: str) -> dict:
        """获取某 ticker 当前信号的可信度评估。"""

    def tool_get_graph_neighbors(self, node_id: str, depth: int = 1) -> dict:
        """查询知识图谱中某节点的关联信息。"""
```

**MCP 配置示例** (用户添加到 Claude Desktop / Codex / OpenClaw)：

```json
{
  "mcpServers": {
    "trading-knowledge": {
      "command": "python",
      "args": ["-m", "tradingagents.knowledge.mcp_server"],
      "env": {
        "TRADINGAGENTS_ARCHIVE_DIR": "~/.tradingagents/analysis-archive",
        "GRAPH_PATH": "graphify-out/unified-graph.json"
      }
    }
  }
}
```

```python
# 所有 CLI 命令统一通过 get_current_price() 获取行情
# 改动文件: cli/portfolio.py, cli/scan.py, cli/alerts.py, cli/market_scan.py

# 改前:
def _fetch_spot_prices(self):
    df = ak.stock_zh_a_spot()  # 全市场下载，每次独立

# 改后:
def _fetch_spot_prices(self, tickers):
    prices = {}
    for t in tickers:
        quote = get_current_price(t)  # 走共享 30s TTL 缓存
        if quote:
            prices[t] = quote
    return prices
```

## 执行策略

### Phase 0 — 缓存基础设施 + Graphify Auto-Sync（1-2 天，基础）

- [x] 1. 新建 `tradingagents/dataflows/cache.py`，实现 `DataCache` 基类
- [x] 2. 为基准指数数据增加磁盘缓存（`_get_ashare_benchmark_close_series`）
- [x] 3. 消除 `trading_graph.py` 中 4 处冗余 akshare 调用
- [x] 4. CLI 层 spot 缓存统一（portfolio/scan/alerts/market_scan）
- [x] 5. **Graphify Auto-Sync**：在 CLI 命令分析完成后自动执行 `graphify update .`
- [x] 6. 编写测试：`tests/test_data_cache.py`

**验证**：同 ticker 第二次 propagate() 时，akshare 调用次数从 14+ 降到 ≤2；分析完成后 graphify 自动增量更新

### Phase 1 — ContextAssembly + 注入扩展 + Confidence 标签（已完成 ✅）

- [x] 1. 新建 `tradingagents/graph/context_assembly.py`，实现 `ContextAssembler` 类
- [x] 2. 扩展 `AgentState`，新增 `knowledge_context` 字段（含 `confidence` 子字段）
- [x] 3. 在 `_run_graph()` 中调用 ContextAssembly
- [x] 4. Trader prompt 注入历史决策（含 Confidence 标签）
- [x] 5. Research Manager prompt 注入历史计划
- [x] 6. Portfolio Manager prompt 注入存档分析增强
- [x] 7. **Confidence 标签体系**：为每条历史结论标注 CONFIRMED/SINGLE/CONFLICTING/STALE/DERIVED
8. **Confidence 加权检索**：高置信度结论优先注入，低置信度降权
9. Token 预算控制实现
10. 编写测试：`tests/test_context_assembly.py`（单元）+ `tests/test_knowledge_injection.py`（集成）+ `tests/test_confidence.py`

**验证**：运行 batch 分析，确认每个 agent 的 prompt 中出现了对应历史知识，且带置信度标签

### Phase 2 — 三重缓存检查链（已完成 ✅）

- [x] 1. 在 `propagate()` 中实现 Level 1 检查（同天跳过）
- [x] 2. 在 `propagate()` 中实现 Level 2 检查（增量模式）
- [x] 3. 配置项：`skip_if_analyzed_today`, `incremental_window_days`
- [x] 4. Post-analysis 存档写入
- [x] 5. 编写测试：`tests/test_cache_chain.py`

**验证**：同 ticker 连续跑 2 次，第 2 次应直接返回（Level 1）或显著缩短

### Phase 3 — Wiki 导航 + Lessons 回路（已完成 ✅）

- [x] 1. 新建 `tradingagents/knowledge/wiki_generator.py`，实现 `WikiGenerator` 类
- [x] 2. 新建 `cli/wiki.py`，实现 `tradingagents wiki generate/show/list` 命令
- [x] 3. 生成 `wiki/index.md`（全量索引）+ `wiki/{ticker}.md`（单 ticker 页）+ `wiki/patterns/`（模式页）
- [x] 4. Lessons 回路：在 post-analysis 中提取可复用洞察，写入 lessons 库
- [x] 5. Lessons 去重（7 天窗口）
- [x] 6. Wiki 增量更新：只更新有变化的页面
- [x] 7. 编写测试：`tests/test_wiki.py` + `tests/test_lessons.py`

### Phase 4 — MCP Server + Graph Merge（已完成 ✅）

- [x] 1. 新建 `tradingagents/knowledge/mcp_server.py`，实现 `KnowledgeMCPServer` 类
- [x] 2. 实现 6 个 MCP 工具
- [x] 3. 新建 `cli/mcp.py`，实现 `tradingagents mcp serve` 命令
- [x] 4. **Graph Merge**：将分析存档与代码图合并为 `unified-graph.json`
- [x] 5. MCP Server 同时挂载 archive 和 unified graph
- [x] 6. 编写测试：`tests/test_mcp_server.py`
**验证**：启动 `tradingagents mcp serve` 后，通过 MCP 客户端调用 `query_analysis("600519")` 返回结果

### Phase 5 — God Nodes + Surprising Connections（1 天，图分析）

1. 对 `unified-graph.json` 运行 graphify analyze，提取 God Nodes 和 Surprising Connections
2. 在 Wiki 中新增 "关键发现" 页面，展示自动发现的龙头 ticker 和跨市场模式
3. **Token Reduction 基准测试**：对比原始分析数据 vs 图查询输出的 token 数
4. 可选：`graphify --watch` 自动监控分析存档变化

**验证**：`tradingagents wiki show --insights` 展示自动发现的模式

## 配置项

```python
# tradingagents/default_config.py — 新增

# 知识消费配置
"knowledge_token_budget": 25000,            # 历史知识注入 token 预算
"skip_if_analyzed_today": False,            # 同天同 ticker 跳过分析
"incremental_window_days": 0,               # 增量分析窗口（0=关闭）
"enable_context_assembly": True,            # 是否启用 ContextAssembly
"enable_archive_first_cache": True,         # 是否启用存档优先缓存

# Confidence 标签配置
"confidence_tags_enabled": True,            # 是否启用置信度标签
"confidence_threshold_inject": "CONFLICTING", # 低于此置信度的结论不注入 prompt
                                              # CONFIRMED > SINGLE > DERIVED > CONFLICTING > STALE

# Graphify 集成配置
"graphify_auto_sync": True,                 # 分析完成后自动 graphify update
"graphify_analysis_graph_path": "~/.tradingagents/analysis-archive/", # 分析数据 graphify 路径
"mcp_server_enabled": False,               # 是否启动 MCP Server
"mcp_server_port": 8765,                   # MCP Server 端口（stdio 模式不需要）

# Wiki 配置
"wiki_output_dir": "~/.tradingagents/wiki/", # Wiki 输出目录
"wiki_auto_generate": False,                 # 每次分析后自动更新 Wiki
```

## 验证策略

### 单元测试

| 模块 | 测试文件 | 用例数 | 覆盖内容 |
|------|---------|--------|---------|
| `DataCache` | `tests/test_data_cache.py` | 15+ | get/set/get_or_fetch/invalidate/namespace隔离/并发安全 |
| `ContextAssembler` | `tests/test_context_assembly.py` | 20+ | 装配逻辑/预算裁剪/空数据/各知识源组合 |
| `Confidence` | `tests/test_confidence.py` | 15+ | 标签计算/加权排序/阈值过滤/标签合并 |
| `三重缓存链` | `tests/test_cache_chain.py` | 10+ | L1命中/L2增量/L3全量/配置开关 |
| `WikiGenerator` | `tests/test_wiki.py` | 15+ | 索引生成/ticker页/模式页/增量更新/空数据 |
| `Lessons` | `tests/test_lessons.py` | 10+ | lesson提取/去重/加权/格式 |
| `KnowledgeMCPServer` | `tests/test_mcp_server.py` | 12+ | 6个MCP工具/参数校验/异常处理 |

### 集成测试

| 场景 | 步骤 | 预期 |
|------|------|------|
| 存档优先缓存 | 连续 2 次 propagate("600519") | 第 2 次 akshare 调用减少 |
| ContextAssembly | 运行 batch 分析 | AgentState.knowledge_context 含历史数据 + confidence 标签 |
| Trader 注入 | 检查 trader prompt | 出现"历史交易经验"段落，带置信度标签 |
| PM 增强 | 检查 PM prompt | 出现存档分析摘要 |
| L1 跳过 | 第 1 次全量 → 第 2 次带 skip_if_analyzed_today | 第 2 次直接返回 |
| Graphify Auto-Sync | 运行 batch → 检查 graphify-out cache | 有新文件被提取 |
| Wiki 生成 | `tradingagents wiki generate --ticker 600519` | 生成 wiki/600519.md |
| MCP 查询 | `tradingagents mcp serve` → 调 tool_query_analysis | 返回 JSON 结果 |

### 端到端验证

```bash
# 1. 验证缓存层
tradingagents batch --ticker 600519 --date 2026-05-09 --output silent
tradingagents batch --ticker 600519 --date 2026-05-09 --output silent  # 应该更快

# 2. 验证知识注入 + Confidence
tradingagents batch --ticker 600519 --date 2026-05-09 --output json \
  | grep "CONFIRMED"  # 应出现置信度标签

# 3. 验证存档
ls ~/.tradingagents/analysis-archive/2026/05/09/
# 应出现 batch_600519.json 等文件

# 4. 验证 Graphify Auto-Sync
ls graphify-out/cache/  # 应包含分析存档的缓存条目

# 5. 验证 Wiki
tradingagents wiki generate
cat ~/.tradingagents/wiki/index.md  # 应有全量索引

# 6. 验证 MCP Server
tradingagents mcp serve &
# 在其他终端用 MCP 客户端调用 tool_query_analysis("600519")
# 应返回历史分析记录

# 7. 验证 Graph Merge
python -m graphify merge-graphs \
  graphify-out/graph.json \
  graphify-out/analysis-graph.json \
  --out graphify-out/unified-graph.json
graphify query "600519 和涨跌停" --graph graphify-out/unified-graph.json
```

## 风险与约束

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 历史知识注入误导 agent 判断 | 中 | 高 | Confidence 标签降权低质量结论；所有注入内容标记为"仅供参考"；默认关闭，逐步启用 |
| Token 预算估算不准确 | 中 | 中 | 使用 `tiktoken` 或近似估算，提供 `knowledge_token_budget` 配置 |
| 缓存层引入 stale 数据 | 低 | 低 | 提供 `--refresh-cache` 命令强制刷新；OHLCV 数据日频刷新 |
| ContextAssembly 增加启动延迟 | 低 | 低 | 文件读取在 ~5ms 内；Level 1/2 检查在 ~1ms 内；MCP 查询为后台异步 |
| 向后兼容破坏 | 低 | 高 | 所有新增字段用 `.get()` 带默认值；配置项默认关闭新特性 |
| MCP Server 端口冲突 | 低 | 低 | stdio 模式替代 TCP；配置 `mcp_server_port` 可自定义 |
| graphify 版本不兼容 | 低 | 中 | 锁定 graphify 版本；auto-sync 失败静默跳过，不阻塞主流程 |

## 成功标准

1. [x] `DataCache` 所有方法测试通过 (28 tests)
2. [ ] 基准指数数据不再每次 propagate() 重新下载
3. [ ] trading_graph.py 中 akshare 调用从 14 次/run 降到 ≤2 次/run
4. [ ] CLI 层 4 个命令共享 spot 缓存
5. [x] ContextAssembly 正确装配历史知识（含 Confidence 标签）
6. [x] Trader prompt 中出现历史决策 + 盈亏信息 + Confidence 标签
7. [x] Research Manager prompt 中出现历史决策信息
8. [x] PM prompt 中出现存档分析摘要
9. [x] Level 1 缓存检查正确跳过已分析 ticker
10. [x] 所有配置项默认关闭时行为与现有一致
11. [x] 分析完成后 graphify 自动增量更新（Auto-Sync）
12. [x] `tradingagents wiki generate` 生成正确的导航索引
13. [x] `tradingagents mcp serve` 启动并提供 6 个可调用工具
14. [x] unified-graph.json 正确合并代码图 + 分析图
15. [x] 已有测试全部通过，无回归 (593 passed)

## 文件清单

### 新建文件

```
tradingagents/dataflows/cache.py              # 统一缓存层 ✅
tradingagents/graph/context_assembly.py       # ContextAssembly 节点 ✅
tradingagents/knowledge/__init__.py           # knowledge 包初始化 ✅
tradingagents/knowledge/wiki_generator.py     # Wiki 导航生成器 ✅
tradingagents/knowledge/mcp_server.py         # MCP Server ✅
cli/wiki.py                                   # tradingagents wiki 命令组 ✅
cli/mcp.py                                    # tradingagents mcp 命令组 ✅
tests/test_data_cache.py                      # 缓存层测试 ✅
tests/test_context_assembly.py                # ContextAssembly 测试 ✅
tests/test_confidence.py                      # Confidence 标签测试 ✅
tests/test_cache_chain.py                     # 缓存链测试 ✅
tests/test_knowledge_injection.py             # 知识注入集成测试 ✅
tests/test_wiki.py                            # Wiki 生成器测试 ✅
tests/test_lessons.py                         # Lessons 测试 ✅
tests/test_mcp_server.py                      # MCP Server 测试 ✅
```

### 修改文件

```
tradingagents/graph/trading_graph.py          # propagate() + 消除冗余 akshare 调用 + graphify auto-sync
tradingagents/agents/utils/agent_states.py    # 新增 knowledge_context 字段 + confidence 字段
tradingagents/agents/trader/trader.py         # 历史决策注入 + confidence 标签
tradingagents/agents/managers/research_manager.py  # 历史决策注入
tradingagents/agents/managers/portfolio_manager.py # 存档分析增强 + confidence 标签
tradingagents/dataflows/akshare.py            # 缓存统一
tradingagents/default_config.py               # 新增配置项（含 confidence/graphify/wiki/mcp）
cli/portfolio.py                              # spot 缓存统一
cli/scan.py                                   # spot 缓存统一 + graphify auto-sync hook
cli/alerts.py                                 # spot 缓存统一
cli/market_scan.py                            # spot 缓存统一
cli/main.py                                   # 注册 wiki 和 mcp 命令组
cli/batch.py                                  # graphify auto-sync hook
```
