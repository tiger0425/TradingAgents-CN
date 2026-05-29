# PRD：TradingAgents 完整选股系统

> 版本：v1.0
> 状态：草案
> 日期：2026-05-06

---

## 目录

1. [背景与动机](#1-背景与动机)
2. [目标与范围](#2-目标与范围)
3. [用户场景](#3-用户场景)
4. [功能需求](#4-功能需求)
5. [架构总览](#5-架构总览)
6. [模块设计](#6-模块设计)
7. [数据模型](#7-数据模型)
8. [非功能需求](#8-非功能需求)
9. [实施路线图](#9-实施路线图)
10. [风险与约束](#10-风险与约束)
11. [决策日志](#11-决策日志)

---

## 1. 背景与动机

### 1.1 现状

TradingAgents-cn 当前是一个**单只股票多智能体深度分析系统**。给定一只股票代码和日期，10 个 AI agent 协作生成分析报告和交易评级（Buy/Overweight/Hold/Underweight/Sell）。

### 1.2 核心缺口

| 能力 | 券商 | TradingAgents-cn |
|------|------|-----------------|
| 全市场扫描（5000+ 只） | ✅ 多因子模型初筛 | ❌ 只能单只分析 |
| 量化排名 | ✅ IC 加权/机器学习 | ❌ 无 |
| 行业板块比较 | ✅ 行业轮动策略 | ❌ 无 |
| 个股深度分析 | ✅ 研究员覆盖 | ✅ 10 agent 协作 |
| 组合构建 | ✅ 风险平价/约束优化 | ❌ 无 |
| 回测验证 | ✅ 完整回测框架 | ⚠️ backtrader 已引入未启用 |

### 1.3 目标

构建一个**从全市场扫描到深度分析到组合构建**的完整选股系统，使得：
- 用户可以一键获得 A 股全市场的推荐股票列表
- 系统覆盖"**宽筛 → 精选 → 深研 → 组合**"完整链路
- 量化初筛层与现有 LLM agent 深度分析层无缝衔接

---

## 2. 目标与范围

### 2.1 在范围之内

- A 股全市场（沪深北 ~5000 只）股票扫描与筛选
- 多因子量化评分模型（价值、成长、质量、动量、情绪）
- 动态因子权重配置
- Top K 筛选结果自动喂入 TradingAgents 深度分析管道
- 多股票并行分析调度
- 组合风险评分输出
- CLI 命令扩展：`tradingagents screen`
- 结果持久化（CSV / JSON / Markdown 报告）

### 2.2 不在范围之内

- 实时/分钟级选股（仅日线级别）
- 实盘交易执行
- 美股全市场扫描（美股保留现有单只分析能力）
- 因子挖掘（不涉及非线性因子组合搜索或遗传算法）
- Web UI（仅 CLI）
- 机器学习模型训练（因子权重由启发式/IC-based 方法确定）

---

## 3. 用户场景

### 场景 A：快速全市场扫描

```
用户输入: tradingagents screen --top 20
系统输出:
  ┌───────┬──────────┬───────┬───────────┐
  │ 代码   │ 名称     │ 总分  │ 评级      │
  ├───────┼──────────┼───────┼───────────┤
  │ 600519│ 贵州茅台  │ 85.3 │ Buy       │
  │ 300750│ 宁德时代  │ 82.1 │ Overweight│
  │ ...   │          │       │           │
  └───────┴──────────┴───────┴───────────┘
  前 20 只中有 5 只已喂入深度分析管道...
```

### 场景 B：自定义因子权重扫描

```
用户输入: tradingagents screen --factors value:0.4 growth:0.3 momentum:0.3 --top 10
系统输出: 按自定义权重排序的 Top 10
```

### 场景 C：行业精选 + 深度优先

```
用户输入: tradingagents screen --industry 白酒 --top 5 --deep
系统输出: 食品饮料板块排名前 5 → 自动触发深度分析
```

### 场景 D：定投候选池生成

```
用户输入: tradingagents screen --top 30 --save-pool my_pool.json
系统输出: 每月跑一次，生成定投候选池
```

---

## 4. 功能需求

### F1：全市场数据拉取

| 需求 ID | 描述 | 优先级 |
|---------|------|--------|
| F1.1 | 通过 akshare 拉取全市场日线行情（stock_zh_a_spot_em） | P0 |
| F1.2 | 拉取全市场基础财务指标（stock_financial_abstract） | P0 |
| F1.3 | 拉取估值数据（PE / PB / PS） | P0 |
| F1.4 | 数据本地缓存（缓存 1 个交易日） | P1 |
| F1.5 | 剔除 ST、*ST、退市股、次新股（上市 < 60 天） | P0 |

### F2：多因子评分引擎

| 需求 ID | 描述 | 优先级 |
|---------|------|--------|
| F2.1 | **价值因子**：PE(TTM)倒数、PB倒数、PS倒数、股息率 | P0 |
| F2.2 | **成长因子**：营收增长率(1Y/3Y)、净利润增长率(1Y/3Y)、ROE 变化趋势 | P0 |
| F2.3 | **质量因子**：ROE、毛利率、资产负债率、经营现金流/净利润 | P0 |
| F2.4 | **动量因子**：过去 1/3/6 月涨幅、RSI、MACD 方向 | P1 |
| F2.5 | **情绪因子**：换手率变化、分析师评级变化、大单资金流向 | P2 |
| F2.6 | 因子标准化（去极值 → 中性化 → Z-score） | P0 |
| F2.7 | 因子加权合成（默认等权 → 可自定义权重） | P0 |

### F3：行业板块分析

| 需求 ID | 描述 | 优先级 |
|---------|------|--------|
| F3.1 | 按申万一级行业分类汇总评分 | P1 |
| F3.2 | 行业动量排名（板块近 3 月涨幅排名） | P1 |
| F3.3 | 行业分散度指标（同行业选股数上限） | P2 |

### F4：与 TradingAgents 深度分析管道集成

| 需求 ID | 描述 | 优先级 |
|---------|------|--------|
| F4.1 | Top K 股票自动喂入 TradingAgentsGraph | P0 |
| F4.2 | 多股票并行分析（每个 ticker 一个独立 agent 实例） | P0 |
| F4.3 | 深度分析结果（评级 + 报告）合并到最终输出 | P0 |
| F4.4 | 分析进度显示（已完成 N/M 只） | P1 |
| F4.5 | 失败重试 + 跳过机制 | P1 |

### F5：组合建议输出

| 需求 ID | 描述 | 优先级 |
|---------|------|--------|
| F5.1 | 输出等权/市值加权/评分加权组合 | P1 |
| F5.2 | 行业持仓上限约束 | P2 |
| F5.3 | 单只股票最大仓位限制 | P2 |
| F5.4 | 组合风险评分（波动率 + 最大回撤估算） | P2 |

### F6：CLI 命令

| 需求 ID | 描述 | 优先级 |
|---------|------|--------|
| F6.1 | `tradingagents screen` - 全市场扫描选股 | P0 |
| F6.2 | `tradingagents screen --top N` - 指定输出数量 | P0 |
| F6.3 | `tradingagents screen --deep` - 自动触发 agent 深度分析 | P0 |
| F6.4 | `tradingagents screen --factors value:0.3 growth:0.3 ...` - 自定义因子权重 | P1 |
| F6.5 | `tradingagents screen --industry 白酒` - 按行业筛选 | P1 |
| F6.6 | `tradingagents screen --save-pool path.json` - 保存候选池 | P1 |
| F6.7 | `tradingagents screen --backtest` - 对当前策略跑回测 | P2 |

### F7：简单回测

| 需求 ID | 描述 | 优先级 |
|---------|------|--------|
| F7.1 | 基于 backtrader 的回测管道 | P2 |
| F7.2 | 定期 rebalance 回测（按月/季度） | P2 |
| F7.3 | 绩效报告（累计收益、年化、夏普、最大回撤） | P2 |

---

## 5. 架构总览

### 5.1 系统分层

```
┌──────────────────────────────────────────────────────────┐
│                    CLI Layer (tradingagents screen)        │
│  参数解析 → 结果渲染 → 进度显示 → 报告输出                 │
├──────────────────────────────────────────────────────────┤
│                 Orchestrator Layer                        │
│  市场哨兵 → 因子引擎 → 排名合并 → 调度器 → 组合构建        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ Market   │  │ Factor   │  │ Rank     │  │ Portfolio│ │
│  │ Scanner  │→│ Engine   │→│ Merger   │→│ Builder  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│                      │                                    │
│                      ▼                                    │
│  ┌──────────────────────────────────────────┐            │
│  │   Deep Analysis Scheduler                 │            │
│  │   并行调用 TradingAgentsGraph.propagate() │            │
│  │   进度跟踪 + 超时控制 + 结果聚合          │            │
│  └──────────────────────────────────────────┘            │
├──────────────────────────────────────────────────────────┤
│              Existing TradingAgents Layer                 │
│  4 Analysts → Bull/Bear Debate → RM → Trader →            │
│  Risk Debate → PM → Rating                                │
├──────────────────────────────────────────────────────────┤
│                 Data Layer                                │
│  akshare (Sina + 东方财富) → 本地缓存                      │
└──────────────────────────────────────────────────────────┘
```

### 5.2 与现有系统的关系

```
现有系统: TradingAgentsGraph
  ├─ propagate(ticker, date) → (state, rating)
  └─ 每次分析一只股票

新增层: StockScreeningPipeline
  ├─ screen(market="A_SHARE", top=20, deep=True)
  │   ├─ 扫地（F1: 全市场数据）
  │   ├─ 评分（F2: 多因子模型）
  │   ├─ 筛选（F3: Top K 候选）
  │   ├─ 深研（F4: 并行调用 propagate()）
  │   └─ 组合（F5: 输出建议）
  └─ 完全不侵入现有 TradingAgentsGraph 代码
```

新系统作为**上层调度器**，以 Python 包的形式调用现有的 `TradingAgentsGraph`，不修改其内部逻辑。

---

## 6. 模块设计

### 6.1 MarketScanner（全市场扫描器）

```python
class MarketScanner:
    """全市场数据扫描器。"""

    def scan(self) -> pd.DataFrame:
        """拉取全市场股票列表、实时行情和基础财务指标。

        数据源（akshare）:
          - stock_zh_a_spot_em()   → 全市场实时行情
          - stock_financial_abstract() → 基础财务指标
          - stock_info_a_code_name()   → 代码-名称映射

        过滤:
          - 剔除 ST / *ST / 退市
          - 剔除上市 < 60 天次新股
          - 剔除停牌股（涨跌幅为 0 且无法交易）

        返回:
          DataFrame: columns = [代码, 名称, 价格, PE, PB, ROE, ...]
        """
```

### 6.2 FactorEngine（因子计算引擎）

```python
class FactorEngine:
    """多因子计算引擎。"""

    def compute(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        """对全市场数据计算所有因子值。

        因子清单:
          - 价值: pe_ttm_inv, pb_inv, ps_inv, div_yield
          - 成长: rev_growth_1y, profit_growth_1y, roe_trend
          - 质量: roe, gross_margin, debt_ratio, cashflow_quality
          - 动量: mom_1m, mom_3m, mom_6m, rsi_14d
          - 情绪: turnover_change, analyst_rating_change

        预处理:
          1. 去极值（MAD 方法，3σ 截断）
          2. 中性化（市值 + 行业回归去残差）
          3. 标准化（Z-score）

        返回:
          DataFrame: columns = [代码, 因子1_zscore, 因子2_zscore, ...]
        """
```

### 6.3 Scorer（评分模块）

```python
class Scorer:
    """因子加权评分。"""

    WEIGHT_PRESETS = {
        "均衡": {"value": 0.20, "growth": 0.25, "quality": 0.25,
                 "momentum": 0.15, "sentiment": 0.15},
        "价值优先": {"value": 0.40, "growth": 0.15, "quality": 0.20,
                   "momentum": 0.15, "sentiment": 0.10},
        "成长优先": {"value": 0.10, "growth": 0.40, "quality": 0.20,
                   "momentum": 0.20, "sentiment": 0.10},
        "动量优先": {"value": 0.10, "growth": 0.15, "quality": 0.15,
                   "momentum": 0.40, "sentiment": 0.20},
    }

    def score(self, factor_df: pd.DataFrame,
              weights: dict = None) -> pd.DataFrame:
        """计算综合评分 = Σ(因子_zscore × 权重)。

        参数:
          weights: 因子大类权重（默认 "均衡" 预设）
        返回:
          DataFrame: columns = [代码, 名称, 总分, 价值分, 成长分, ...]
        """
```

### 6.4 DeepScheduler（深度分析调度器）

```python
class DeepScheduler:
    """并行深度分析调度器。

    将 Top K 股票分发给多个 TradingAgentsGraph 实例。
    """

    def __init__(self, config: dict, max_workers: int = 4):
        self.max_workers = max_workers
        self.config = config

    def analyze(self, candidates: List[str], date: str,
                progress_callback=None) -> List[Dict]:
        """对候选股票列表执行并行深度分析。

        策略:
          - 使用 ThreadPoolExecutor 并行运行 propagate()
          - max_workers 控制并发数（避免 LLM API 限流）
          - 每个 propagate() 运行在独立实例中
          - 超时控制：单只分析超时 = config["screening_timeout"]

        返回:
          [{"ticker": "600519", "rating": "Buy",
            "decision": "...", "full_state": {...}}, ...]
        """

    def _create_slim_config(self) -> dict:
        """生成深度分析配置：低辩论轮次 + 快速模型。
        deep_think_llm 和 quick_think_llm 不同时使用两个等级，
        快速扫描场景可以都设为同一个快速模型。
        """
```

### 6.5 PortfolioBuilder（组合构建器）

```python
class PortfolioBuilder:
    """从深度分析结果构建投资组合。"""

    def build(self, results: List[Dict],
              max_positions: int = 10,
              max_per_sector: int = 3,
              max_per_stock: float = 0.15) -> Dict:
        """构建建议组合。

        输出:
          {
            "组合": [
              {"ticker": "600519", "weight": 0.10,
               "rating": "Buy", "sector": "食品饮料"},
              ...
            ],
            "组合风险": {"年化波动率": "18%", "最大回撤": "25%",
                       "夏普比率(假设)": "1.2"},
            "行业分布": {"食品饮料": 20%, "新能源": 15%, ...},
          }
        """
```

### 6.6 CLI 命令扩展

在 `cli/main.py` 中添加 `screen` 命令：

```python
@app.command()
def screen(
    top: int = typer.Option(20, "--top", "-n", help="输出前 N 只"),
    deep: bool = typer.Option(False, "--deep", "-d",
                              help="自动触发 LLM 深度分析"),
    factors: str = typer.Option(None, "--factors", "-f",
                                help="自定义因子权重, 如 'value:0.3 growth:0.3'"),
    industry: str = typer.Option(None, "--industry", "-i",
                                 help="按行业筛选"),
    preset: str = typer.Option("均衡", "--preset", "-p",
                               help="因子预设: 均衡/价值优先/成长优先/动量优先"),
    save_pool: str = typer.Option(None, "--save-pool",
                                  help="保存候选池到文件"),
    max_workers: int = typer.Option(4, "--workers", "-w",
                                    help="深度分析并发数"),
):
    """全市场扫描选股。"""
    ...
```

---

## 7. 数据模型

### 7.1 因子数据（中间格式）

```python
@dataclass
class FactorRecord:
    ticker: str           # "600519"
    name: str             # "贵州茅台"
    sector: str           # "食品饮料"
    market_cap: float     # 流通市值（亿）

    # 原始因子值
    raw: Dict[str, float]  # {"pe_ttm": 30.5, "roe": 0.25, ...}

    # 标准化后因子值
    zscore: Dict[str, float]  # {"pe_ttm_inv_z": 1.2, "roe_z": 2.1, ...}

    # 大类因子得分
    factor_scores: Dict[str, float]  # {"value": 0.8, "growth": 1.1, ...}

    # 总分
    total_score: float  # 1.05
```

### 7.2 扫描结果输出格式

```python
@dataclass
class ScreeningResult:
    date: str                          # "2026-05-06"
    total_stocks_scanned: int          # ~5000
    total_after_filter: int            # ~3000（剔除 ST/次新/停牌后）
    depth: str                         # "quick" | "deep"

    # 排名列表
    ranked: List[RankedStock]

    # 深度分析结果（仅 deep=True 时）
    deep_results: Optional[List[DeepResult]]

    # 组合建议（仅 deep=True 时）
    portfolio: Optional[PortfolioSuggestion]


@dataclass
class RankedStock:
    rank: int
    ticker: str
    name: str
    sector: str
    total_score: float
    factor_scores: Dict[str, float]
    price: float
    pe_ttm: float


@dataclass
class DeepResult:
    ticker: str
    rating: str                # Buy/Overweight/Hold/Underweight/Sell
    executive_summary: str
    price_target: Optional[float]
    confidence: str            # high/medium/low
```

### 7.3 缓存设计

```python
# 缓存目录
~/.tradingagents/cache/screening/
  ├── market_snapshot_{date}.parquet    # 全市场快照（保留 5 天）
  ├── factors_{date}.parquet            # 因子值（保留 5 天）
  └── deep_results_{date}.json          # 深度分析结果（保留 30 天）
```

---

## 8. 非功能需求

### 8.1 性能

| 指标 | 目标 | 说明 |
|------|------|------|
| 全市场扫描（不触发深度分析） | < 30 秒 | 仅做量化初筛 |
| 全市场扫描 + Top 10 深度分析 | < 5 分钟 | 10 只并行，每只 ~2 分钟 |
| 数据缓存命中率 | > 90% | 同一天重复运行不重新拉取 |
| 全量因子计算 | < 10 秒 | 5000 只 × 20 因子，向量化计算 |

### 8.2 可靠性

- akshare 接口失败时使用缓存数据降级
- 单只股票深度分析失败不影响其他股票
- 网络超时：单次 akshare 请求超时 15 秒
- 深度分析超时：单只股票最大等待 300 秒

### 8.3 成本控制

- 深度分析模式下，LLM 模型选择**快速模型**（`quick_think_llm`）
- `max_debate_rounds = 1` / `max_risk_discuss_rounds = 1`（最浅辩论）
- 可选 `selected_analysts` 子集以进一步降低 LLM 调用量
- 预估 Top 20 深度分析花费：~ 20 × 0.5 元 ≈ 10 元/次（DeepSeek）

### 8.4 可扩展性

- 因子引擎支持**插件式添加新因子**（注册新函数即可）
- 权重预设可扩展（用户自定义权重配置文件）
- 数据供应商可切换（akshare → yfinance → alpha_vantage）

---

## 9. 实施路线图

### Phase 1：核心量化层（2-3 天）

```
完成内容:
  ✅ MarketScanner — 全市场数据拉取 + 过滤
  ✅ FactorEngine — 5 大类 15+ 因子计算 + 标准化
  ✅ Scorer — 因子加权 + 排名
  ✅ CLI: tradingagents screen（不带 --deep）

输出: 全市场排名 CSV / JSON
测试: 验证排名合理（茅台/宁德在前 10%）
```

### Phase 2：深度分析集成（2 天）

```
完成内容:
  ✅ DeepScheduler — 并行调用 TradingAgentsGraph
  ✅ 进度显示 + 超时控制
  ✅ 结果合并：量化排名 + LLM 评级
  ✅ CLI: tradingagents screen --deep

输出: 排名 + 深度分析报告
集成: 复用现有 config、无需修改 TradingAgentsGraph
```

### Phase 3：组合构建与报告（1 天）

```
完成内容:
  ✅ PortfolioBuilder — 仓位分配 + 行业约束
  ✅ Markdown 报告生成
  ✅ 候选池保存（--save-pool）
  ✅ CLI: --industry / --factors / --preset 参数

输出: 完整选股报告（Markdown + JSON）
```

### Phase 4：回测与优化（2 天，可选）

```
完成内容:
  ✅ backtrader 集成 — 月度/季度 rebalance 回测
  ✅ 绩效报告
  ✅ 因子分析（IC / IR 计算）

输出: 回测绩效报告
```

---

## 10. 风险与约束

### 10.1 已知风险

| 风险 | 概率 | 影响 | 缓解方案 |
|------|------|------|---------|
| akshare 接口变动 | 中 | 高 | 缓存 + 异常捕获降级 |
| LLM API 限流 | 高（并行时） | 中 | max_workers 控制 + 退避重试 |
| 因子数据质量差 | 中 | 高 | MAD 去极值 + 空值剔除 |
| 新股/小盘股因子失真 | 中 | 低 | 市值中性化处理 |
| LLM 分析一致性差 | 中 | 中 | 同股同配置多次运行取众数 |

### 10.2 约束

- 单次运行依赖：akshare + LLM API Key（两者缺一不可）
- 深度分析模式必须配置 `.env` 中的 LLM API Key
- A 股数据源仅限 akshare（不依赖其他金融数据供应商）
- 不是实时选股系统（依赖日线数据）

---

## 11. 决策日志

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 量化层 vs 纯 LLM 层 | ① 纯 LLM 批量调用 ② 量化初筛 + LLM 深研 | **②** | 成本可控（先算数再花钱），且排名可解释性强 |
| 新模块 vs 侵入 TradingAgentsGraph | ① 修改现有类 ② 独立 Pipeline 层 | **②** | 保持现有系统稳定，职责分离，容易独立测试 |
| 因子权重 | ① 固定权重 ② ICIR 动态权重 ③ 用户自定义 | **①+③** | 初期固定权重够用，保留用户覆盖能力，ICIR 放到 Phase 4 |
| 并行策略 | ① 多进程 ② 多线程 ③ asyncio | **②** | Python GIL 对 IO 密集型（LLM API 调用）影响小，多线程足够 |
| 数据缓存格式 | ① JSON ② Parquet | **②** | 5000 行 × 30 列，Parquet 压缩比高且 pandas 原生支持 |
| LLM 模型选择策略 | ① 统一模型 ② 量化层快速模型 + 深度层强模型 | **②** | 扫盘阶段用快速模型省钱，最终决策用强模型保证质量 |

---

## 附录 A：预计算费估算

基于 DeepSeek API 价格（2026 年 5 月）：

| 模式 | LLM 调用量 | 预估费用 |
|------|-----------|---------|
| `screen --top 10`（快速） | 无 LLM 调用 | ¥0 |
| `screen --top 10 --deep` | 10 × ~10 次 LLM 调用 | ~¥5-10 |
| `screen --top 20 --deep` | 20 × ~10 次 LLM 调用 | ~¥10-20 |

## 附录 B：与现有系统的集成点

```
集成接口（新增文件）:
  tradingagents/
  └── screening/                  <-- 新增包
      ├── __init__.py
      ├── market_scanner.py       # F1
      ├── factor_engine.py        # F2
      ├── scorer.py               # F2
      ├── deep_scheduler.py       # F4
      ├── portfolio_builder.py    # F5
      ├── backtest_runner.py      # F7
      └── presets.py              # 权重预设

  cli/main.py                     # 追加 screen 命令（少量修改）

无需修改的现有文件:
  tradingagents/graph/trading_graph.py  ← 不动
  tradingagents/default_config.py       ← 不动
  tradingagents/agents/*                ← 不动
  tradingagents/dataflows/akshare.py    ← 不动（复用现有函数）
```
