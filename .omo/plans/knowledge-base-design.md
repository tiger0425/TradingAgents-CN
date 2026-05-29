# 知识库系统设计 — TradingAgents 分析积累架构

## 摘要

为 TradingAgents 项目设计一个分层知识库系统，将分散在交易决策日志、开发笔记、CLI 分析输出和代码知识图谱中的信息统一为可查询、可追溯、可积累的体系。目标是让"每天做的分析"能够被检索、对比和继承，实现分析能力的持续累积。

## 背景

当前项目已经具备以下知识积累能力：

- **TradingMemoryLog**（`memory.py`）：每次交易决策的决策+反思持久化，支撑跨运行上下文注入
- **PositionState**：持仓状态持久化，模拟持仓自动更新
- **.sisyphus/notepads/**：按开发工作流组织的 learnings/decisions/issues
- **graphify-out/**：代码级知识图谱，支持 query/path/explain 查询
- **CLI 分析输出**：`morning-scan`、`evening-review`、`batch`、`scan-watchlist` 等命令产生结构化 JSON 输出

**核心缺失**：CLI 分析结果生命周期止于终端/文件，没有被系统性地存档和积累；四个体系彼此孤立，无法交叉查询；缺少一个轻量的每日分析日志入口。

## 目标

1. 每次 CLI 分析结果自动持久化到结构化存档，支持按 ticker、日期、决策方向检索
2. 建立每日分析日志模板，记录市场观察、策略假设、工具新发现
3. 将分析日志和分析存档纳入 graphify 语料，实现代码+分析统一查询
4. 给用户提供 `tradingagents archive` 命令组，用于搜索和浏览历史分析

## 范围

### 纳入范围

- `AnalysisArchive` 模块（新建）：分析结果存档的核心实现
- `tradingagents archive` CLI 命令组（新建）：搜索/浏览历史分析
- CLI 命令（scan/batch）的自动存档 hook（改造）
- 每日分析日志模板与工作流（新建）
- graphify 语料扩展配置（配置）

### 不纳入范围

- 本设计不涉及交易策略本身的改进
- 不涉及数据库选型（暂定文件系统即可，数据量级无需数据库）
- 不涉及真实券商 API 对接
- 不涉及分布式/多用户场景

## 技术决策

### ADR-001: 分析存档使用文件系统 + JSON，而非数据库

**背景**: 按每天 ~20 只股票 × 2 次分析（晨间+收盘）= 40 个 JSON，每文件 ~5KB，一年约 75MB。文件系统完全胜任。

**决策**: 使用目录结构 + JSON 文件 + index.json 倒排索引。

**理由**:
- 零依赖，与现有 `position_state.json` / `watchlist.json` 一致
- 易于版本控制、备份、grep
- 文件路径本身携带日期和 ticker 信息，天然分片

**后果**:
- 无 ACID 事务（但分析存档是 append 为主，偶有删除，文件级原子写即可）
- 全文搜索不如数据库高效（但 ~75MB 的数据量，grep 够用）

### ADR-002: archive 与 TradingMemoryLog 互补而非替代

**背景**: TradingMemoryLog 存的是决策结果+反思，供下一次分析的 prompt 注入使用。

**决策**: archive 存完整分析上下文（分析师报告全文、行情快照、环境参数），与 memory 互补。

**理由**:
- memory 是"给 LLM 看的"，archive 是"给人看的"
- memory 追求精简（限制条目数），archive 追求完整
- 两者都引用同一笔分析，但视角不同

### ADR-003: 每日分析日志走 .sisyphus/notepads/daily-log/ 而非独立系统

**背景**: 需要记录每日的市场观察、策略假设等自由格式内容。

**决策**: 使用 Markdown 文件，遵循已有 notepads 体系。

**理由**:
- 复用现有 `.sisyphus/` 目录结构，用户已熟悉
- 低摩擦：打开写 MD 即可
- graphify 可以直接摄取到知识图谱
- 不需要任何代码改动即可开始使用

### ADR-004: graphify 作为统一查询层

**背景**: 代码、分析、日志分属三个体系，但常常需要在同一个问题中引用。

**决策**: 将 `daily-log/` 和 `analysis-archive/` 中的 Markdown 纳入 graphify 的 corpus，构建跨体系知识图谱。

**理由**:
- graphify 已经具备 query/path/explain 的图查询能力
- 不需要引入新的查询基础设施
- 增量更新只在文件变更时重新提取，成本可控

## 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                      查询接口层                                    │
│  tradingagents archive list/get/search/summary                   │
│  graphify query "..."           graphify path A B                │
└──────────────────────────────────────────────────────────────────┘
         │                            │
         ▼                            ▼
┌────────────────────────┐  ┌───────────────────────────────┐
│  结构化索引             │  │  知识图谱                     │
│  index.json (倒排)      │  │  graphify-out/               │
│                        │  │  (含代码 + 分析 + 日志节点)    │
└────────────────────────┘  └───────────────────────────────┘
         │                            │
         ▼                            ▼
┌────────────────────────┐  ┌───────────────────────────────┐
│  分析存档 (File System) │  │  开发笔记 (File System)        │
│  ~/.tradingagents/     │  │  .sisyphus/notepads/          │
│  analysis-archive/     │  │  ├── daily-log/               │
│  ├── 2026/             │  │  ├── trading-assistant-plan/  │
│  │   ├── 05/           │  │  └── ...                      │
│  │   │   ├── index.json│  │                               │
│  │   │   └── 09/       │  │                               │
│  │   └── ...           │  │                               │
│  ├── ...               │  │                               │
│  └── index.json        │  │                               │
└────────────────────────┘  └───────────────────────────────┘
         │
         ▼
┌────────────────────────┐
│  交易记忆               │
│  trading_memory.md     │
│  position_state.json   │
└────────────────────────┘
```

### 存档目录结构详解

```
~/.tradingagents/analysis-archive/
├── index.json                       # 全量索引
│   {
│     "version": 1,
│     "updated_at": "2026-05-09T15:30:00",
│     "total_entries": 1420,
│     "by_ticker": {
│       "600519": ["2026/05/09/morning-scan", "2026/05/09/batch", ...],
│       "000001": [...]
│     },
│     "by_decision": {
│       "buy":  ["2026/05/09/batch_600519", ...],
│       "sell": [...],
│       "hold": [...]
│     },
│     "entries": [
│       {
│         "id": "2026/05/09/morning-scan_600519",
│         "date": "2026-05-09",
│         "type": "morning-scan",
│         "ticker": "600519",
│         "decision": "hold",
│         "rating": "hold",
│         "analysts": ["market", "technical"],
│         "tags": ["放量", "突破前高"]
│       },
│       ...
│     ]
│   }
│
├── 2026/
│   ├── 05/
│   │   ├── index.json              # 月索引（简化版，仅本月条目）
│   │   ├── 09/
│   │   │   ├── index.json          # 日索引
│   │   │   ├── morning-scan_600519.json
│   │   │   ├── morning-scan_000001.json
│   │   │   ├── batch_600519.json
│   │   │   ├── batch_000001.json
│   │   │   ├── evening-review_600519.json
│   │   │   └── 2026-05-09_summary.md    # 当日汇总（可选）
│   │   └── 10/
│   └── 06/
└── ...
```

### 存档 JSON 格式

每次 CLI 分析结果持久化为标准格式：

```json
{
  "_meta": {
    "id": "2026/05/09/morning-scan_600519",
    "archived_at": "2026-05-09T09:35:00+08:00",
    "source_command": "morning-scan",
    "cli_version": "0.2.5"
  },
  "request": {
    "ticker": "600519",
    "date": "2026-05-09",
    "analysts": ["market", "technical"],
    "llm_provider": "openai",
    "config_snapshot": {
      "market_type": "A_SHARE",
      "benchmark_ticker": "000300"
    }
  },
  "market_context": {
    "spot_price": 1580.00,
    "change_pct": -0.32,
    "volume": 2850000,
    "turnover": 4523000000,
    "limit_up": 1738.00,
    "limit_down": 1422.00
  },
  "analysis": {
    "signals": {
      "market": {
        "direction": "cautious",
        "summary": "沪深300...",
        "details": "..."
      },
      "technical": {
        "direction": "bullish",
        "summary": "MACD 金叉...",
        "details": "..."
      }
    },
    "final_decision": "hold",
    "rating": "hold",
    "reasoning": "综合看多空因素..."
  },
  "tags": ["放量", "MACD金叉", "缩量环境"],
  "raw_output": { }
}
```

## 模块设计

### 1. `tradingagents/analysis_archive.py` — 存档核心模块

```python
class AnalysisArchive:
    """
    分析结果存档系统。
    
    功能:
    - save(result: dict, entry_type: str) -> str: 保存分析结果，返回 entry_id
    - get(entry_id: str) -> Optional[dict]: 按 ID 获取完整条目
    - list(ticker=None, date_from=None, date_to=None, decision=None, 
           entry_type=None, limit=20) -> List[dict]: 条件查询
    - search(query: str, limit=20) -> List[dict]: 全文搜索
    - summary(ticker: str, days=90) -> dict: 某股票历史信号汇总
    - delete(entry_id: str) -> bool: 删除条目
    
    内部方法:
    - _build_index(): 重建全量索引
    - _update_index(entry): 增量更新索引
    - _entry_path(entry_id) -> Path: ID 到文件路径的映射
    - _atomic_write(path, data): 原子写入
    """
```

### 2. CLI 命令组 `tradingagents archive`

```python
# cli/archive.py
archive_app = typer.Typer(name="archive")

@archive_app.command("list")
def list_entries(
    ticker: str = typer.Option(None, "--ticker", "-t"),
    decision: str = typer.Option(None, "--decision", "-d"),
    entry_type: str = typer.Option(None, "--type"),
    days: int = typer.Option(30, "--days"),
    limit: int = typer.Option(20, "--limit"),
    output: str = typer.Option("text", "--output"),
): ...

@archive_app.command("get")
def get_entry(
    entry_id: str = typer.Argument(...),
    output: str = typer.Option("text", "--output"),
): ...

@archive_app.command("search")
def search_entries(
    query: str = typer.Argument(...),
    limit: int = typer.Option(20, "--limit"),
    output: str = typer.Option("text", "--output"),
): ...

@archive_app.command("summary")
def ticker_summary(
    ticker: str = typer.Argument(...),
    days: int = typer.Option(90, "--days"),
    output: str = typer.Option("text", "--output"),
): ...
```

### 3. CLI 命令自动存档 hook

在以下命令的成功执行路径末尾插入 `save_to_archive()`：

| 命令 | 入口文件 | 触发位置 |
|------|---------|---------|
| `morning-scan` | `cli/scan.py` | 主函数末尾，notify 之前/之后 |
| `evening-review` | `cli/scan.py` | 主函数末尾，notify 之前/之后 |
| `batch` | `cli/batch.py` | 主函数末尾 |
| `scan-watchlist` | `cli/scan.py` | 主函数末尾 |

hook 函数签名：

```python
def save_to_archive(
    result: dict,
    entry_type: str,        # "morning-scan" | "evening-review" | "batch" | "scan-watchlist"
    ticker: str,
    date: str,
    config: dict = None,
) -> Optional[str]:         # 返回 entry_id 或 None（存档目录不可用时）
    """保存分析结果到存档。静默失败，不阻塞主流程。"""
```

### 4. 每日分析日志模板

```
.sisyphus/notepads/daily-log/YYYY-MM-DD.md

格式：
# YYYY-MM-DD 分析日志

## 市场观察
- 关键信号和异常

## 策略假设
- 新形成的假设或待验证的想法

## 工具/数据新发现
- CLI 使用技巧、数据源变化

## 关联代码变更
- 今天做的代码改动

## 明日计划
- 需要关注的 ticker 或待办
```

## 执行策略

### Phase 1 — AnalysisArchive 核心模块（建议 2-3 天）

1. 新建 `tradingagents/analysis_archive.py`，实现 `AnalysisArchive` 类
2. 实现 `save()`、`get()`、`list()`、`search()`、`summary()` 核心方法
3. 实现索引的增量更新和全量重建
4. 编写测试（`tests/test_analysis_archive.py`）

### Phase 2 — CLI archive 命令组（建议 1-2 天）

1. 新建 `cli/archive.py`，实现 list/get/search/summary 四个命令
2. 注册到 `cli/main.py`
3. 编写测试（`tests/test_archive_cli.py`）

### Phase 3 — CLI 自动存档 hook（建议 1-2 天）

1. 在 `cli/scan.py` 中插入 hook 调用
2. 在 `cli/batch.py` 中插入 hook 调用
3. 验证：跑一次 morning-scan 后确认存档目录有产物

### Phase 4 — 每日日志模板 + graphify 扩展（建议 0.5 天）

1. 创建 `.sisyphus/notepads/daily-log/` 目录和首条日志
2. 配置 graphify 将 daily-log/ 纳入 corpus
3. 配置 graphify 将 analysis-archive/ 纳入 corpus（可选）

## 验证策略

- **单元测试**: AnalysisArchive 核心逻辑 30+ 测试用例
  - 存/取/列/删/搜索 基本操作
  - 索引完整性（增量 vs 全量重建验证数据一致）
  - 边界条件（空存档、不存在的 entry、非法日期格式）
  - 原子写入容错（模拟写入中断）
  - 多 ticker 多日期的混合查询

- **集成测试**: 
  - `save()` 后 `get()` 返回一致
  - `list()` 按 ticker/日期/决策 过滤正确
  - `search()` 全文搜索命中正确

- **端到端验证**:
  - 跑一次 `morning-scan --output json` → 确认存档目录生成文件
  - `tradingagents archive list --ticker 600519` → 能看到刚才的条目
  - `tradingagents archive summary 600519` → 能看到信号汇总

## 风险与约束

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 存档文件增长失控 | 低 | 中 | index.json 分片按月/日，文件系统天然分片 |
| 磁盘空间不足 | 低 | 低 | 每个 JSON ~5KB，一年 ~75MB，可忽略 |
| 索引与数据不一致 | 中 | 中 | 提供 `archive rebuild-index` 重建命令；每次 save 先写数据后更新索引 |
| 并发写入冲突 | 低 | 低 | CLI 单进程执行，无并发问题 |
| akshare 数据源变更导致存档格式过时 | 中 | 低 | `_meta` 中记录版本号，可做格式迁移 |

## 成功标准

1. [x] `AnalysisArchive` 类所有方法有完整测试覆盖，测试通过率 100%
2. [x] `tradingagents archive --help` 展示所有子命令
3. [ ] 一次 `morning-scan` 执行后，`~/.tradingagents/analysis-archive/` 下生成对应条目（需要真实 LLM 运行验证，hook 已实现并单元测试通过）
4. [x] `tradingagents archive search "关键词"` 返回匹配的历史分析
5. [x] `tradingagents archive summary 600519` 展示过去 N 天的信号分布
6. [ ] `graphify query "600519 5月分析"` 能跨代码+分析返回结果（需要真实分析数据后验证）
7. [x] 已有测试全部通过，无回归
