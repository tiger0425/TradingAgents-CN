# 学习笔记 — TradingAgents A 股适配

## 关键发现

### 数据层架构
- `interface.py` 中 `VENDOR_METHODS` 字典是核心路由表，每个 method 映射到 vendor 实现
- 新增 vendor 只需：在 VENDOR_LIST 加名字 + 在 VENDOR_METHODS 每个 method 中加条目
- `route_to_vendor()` 有自动 fallback 链，主 vendor 失败自动尝试备用
- 配置通过 `default_config.py` 的 `data_vendors` 和 `tool_vendors` 控制

### 9 个需实现的接口函数签名（来自 agents/utils/*_tools.py）

```python
get_stock_data(symbol: str, start_date: str, end_date: str) -> str
get_indicators(symbol: str, indicator: str, curr_date: str, look_back_days: int = 30) -> str  
get_fundamentals(ticker: str, curr_date: str) -> str
get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str
get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str
get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str
get_news(ticker: str, start_date: str, end_date: str) -> str
get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 5) -> str
get_insider_transactions(ticker: str) -> str
```

### akshare API 参考
- K线: `ak.stock_zh_a_hist(symbol, period="daily", start_date, end_date, adjust="qfq")`
- 实时行情: `ak.stock_zh_a_spot_em()` (含涨跌停价)
- 财务摘要: `ak.stock_financial_abstract(symbol)` 新浪源
- 财务指标: `ak.stock_financial_analysis_indicator(symbol, start_year)` 新浪源
- 三大报表: `ak.stock_financial_report_sina(stock, symbol_type)` 参数为 "资产负债表"/"利润表"/"现金流量表"
- 个股新闻: `ak.stock_news_em(symbol)` 东方财富
- 大股东持股: `ak.stock_hold_management_detail_em(symbol)` 
- 交易日历: `ak.tool_trade_date_hist_sina()`
- 指数: `ak.stock_zh_index_daily_em(symbol="sh000300")` 沪深300

### 输出格式约束
- 所有函数必须返回 `str`（CSV 格式或文本报告）
- `get_stock_data` 返回 CSV（与 yfinance 一致）
- 基本信息相关返回 CSV
- 新闻返回 Markdown 格式文本

### 2026-05-06: 在 interface.py 和 default_config.py 中注册 akshare 供应商
- `interface.py`: 新增 `from .akshare import (...)` 引入 9 个 akshare 函数（以 `get_akshare_*` 别名）
- `interface.py`: `VENDOR_LIST` 中 `"akshare"` 放在首位，成为默认 fallback 优先供应商
- `interface.py`: `VENDOR_METHODS` 中所有 9 个 method 都添加了 `"akshare"` 条目，放在每个字典的第一位
- `default_config.py`: `data_vendors` 四项全部从 `"yfinance"` 改为 `"akshare"`，注释更新为 `# Options: akshare, alpha_vantage, yfinance`
- 未修改 `route_to_vendor()` 函数逻辑和 `TOOLS_CATEGORIES`

### 2026-05-06: 实现 akshare.py 数据供应商模块

**文件**: `tradingagents/dataflows/akshare.py` (新建，约 750 行)

**9 个公共函数已实现**:

| 函数 | akshare API | 输出格式 |
|------|------------|---------|
| `get_stock_data` | `ak.stock_zh_a_hist(adjust="qfq")` | CSV (OHLCV) |
| `get_indicators` | `_load_ohlcv_akshare` + `stockstats.wrap` | Markdown 文本报告 |
| `get_fundamentals` | `ak.stock_financial_analysis_indicator` | 文本报告 |
| `get_balance_sheet` | `ak.stock_financial_report_sina(type="资产负债表")` | CSV |
| `get_cashflow` | `ak.stock_financial_report_sina(type="现金流量表")` | CSV |
| `get_income_statement` | `ak.stock_financial_report_sina(type="利润表")` | CSV |
| `get_news` | `ak.stock_news_em` (东方财富) | Markdown |
| `get_global_news` | `ak.stock_info_global_em` + `ak.stock_info_sse` fallback | Markdown |
| `get_insider_transactions` | `ak.stock_hold_management_detail_em` (管理层持股变动) | Markdown |

**关键设计决策**:
- 懒导入 akshare: `ak = None` fallback，未安装时返回人类可读错误
- 每函数 `try/except` 包裹，异常返回 `f"Error ... {str(e)}"` 字符串
- `_load_ohlcv_akshare()` 使用与 yfinance 相同的 stockstats 管线模式（Date/Open/High/Low/Close/Volume 列），含缓存和回测防未来数据泄露过滤
- `get_indicators()` 复用 yfinance 的 `best_ind_params` 描述，保持指标语义一致
- `get_global_news()` 有 fallback 链：东方财富全球资讯 → 上交所公告
- `get_insider_transactions()` 映射为 A 股管理层持股变动（无 SEC insider 概念）

**验证结果**:
- Python 语法检查通过
- AST 分析确认全部 9 个函数签名与 `agents/utils/*_tools.py` 中的 `@tool` 装饰器参数匹配
- 全部 9 个函数返回类型注解为 `-> str`
- `interface.py` 的 9 个 akshare import 全部解析成功
- `VENDOR_LIST` 中 `akshare` 排在首位

### 2026-05-06: 新建 a_share_calendar.py — A 股交易日历模块

**文件**: `tradingagents/dataflows/a_share_calendar.py` (新建，92 行)

**3 个公开函数**:

| 函数 | 核心逻辑 | 异常回退 |
|------|---------|---------|
| `is_trade_day(date_str) -> bool` | 查询 `ak.tool_trade_date_hist_sina()` 的 `trade_date` 列 | 周末判断（weekday < 5） |
| `next_trade_day(date_str) -> str` | 筛选 `trade_date > target` 取第一个 | 逐日 +1 直到工作日 |
| `prev_trade_day(date_str) -> str` | 筛选 `trade_date < target` 取最后一个 | 逐日 -1 直到工作日 |

**关键设计**:
- `_load_calendar()` 使用 `@functools.lru_cache(maxsize=1)` 避免同进程重复请求
- 所有函数都有 `try/except` 包裹，异常时回退到简单的周末判断
- akshare 使用延迟导入（函数内 import），确保模块在无 akshare 环境也可导入
- DataFrame 的 `trade_date` 列为 `datetime64` 类型

### 2026-05-06: 扩展 AgentState 新增 A 股字段

**文件**: `tradingagents/agents/utils/agent_states.py` (追加 5 字段，共 80 行)

**新增字段**（在 `past_context` 之后追加）：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `market_type` | `str` | `"A_SHARE"` | `'A_SHARE'` 或 `'US_STOCK'` |
| `benchmark_ticker` | `str` | `"000300"` | 基准指数代码（沪深300） |
| `position_opened_date` | `str` | `""` | 持仓开仓日期 |
| `limit_up_price` | `float` | `0.0` | A 股涨停价 |
| `limit_down_price` | `float` | `0.0` | A 股跌停价 |

**注意**: 未修改任何现有字段，未改变 `MessagesState` 继承关系。新增字段在波段二-C 中被 `portfolio_manager.py` 使用。

### 2026-05-06: 替换硬编码 SPY 基准为可配置 benchmark
- **`default_config.py`**: 新增 `benchmark_ticker` (默认 "000300" 沪深300)、`benchmark_name` (默认 "沪深300")、`market_type` (默认 "A_SHARE")
- **`trading_graph.py` `_fetch_returns()`**:
  - 从 `self.config.get("benchmark_ticker", "SPY")` 读取基准 ticker
  - 变量 `spy` → `benchmark`, `spy_ret` → `bench_ret`
  - fallback 为 "SPY" 确保向后兼容 US stock 场景
- **`reflection.py`**:
  - `Reflector.__init__` 新增 `benchmark_name` 参数 (默认 "沪深300")
  - prompt 中 `"Alpha vs SPY"` → `f"Alpha vs {self.benchmark_name}"`
  - 在 trading_graph.py 实例化时传入 `benchmark_name=self.config.get("benchmark_name", "沪深300")`
- 用户可通过覆盖 `benchmark_ticker` 和 `benchmark_name` 适配任意 yfinance 支持的指数

### 2026-05-06: A 股涨跌停 + T+1 约束注入到 Trader 和 Portfolio Manager

**新建文件**: `tradingagents/dataflows/a_share_constraints.py` (82 行)

**4 个公开函数**:

| 函数 | 签名 | 说明 |
|------|------|------|
| `get_limit_prices` | `(prev_close, name="") → (limit_up, limit_down)` | 默认主板 10% 计算涨跌停 |
| `get_limit_rate` | `(symbol, name="") → float` | 按板块/ST 返回比例：科创板/创业板 20%，北交所 30%，ST 5%，主板 10% |
| `format_limit_constraint` | `(limit_up, limit_down, market_type) → str` | 注入 prompt 的限价文本；非 A 股返回空字符串 |
| `format_t_plus_1_constraint` | `(position_opened_date, trade_date, market_type) → str` | T+1 约束文本；非 A 股/无仓位/可卖出时返回空字符串 |

**修改文件 1**: `tradingagents/agents/trader/trader.py`
- 新增 import: `from tradingagents.dataflows.a_share_constraints import format_limit_constraint`
- `trader_node` 从 state 读取 `market_type`, `limit_up_price`, `limit_down_price`（使用 `.get()` 默认值）
- user message 末尾追加 `{format_limit_constraint(limit_up, limit_down, market_type)}`
- 非 A 股场景下追加空字符串，完全无影响

**修改文件 2**: `tradingagents/agents/managers/portfolio_manager.py`
- 新增 import: `format_limit_constraint`, `format_t_plus_1_constraint`
- `portfolio_manager_node` 从 state 读取 `market_type`, `limit_up_price`, `limit_down_price`, `position_opened_date`, `trade_date`
- prompt 末尾（`get_language_instruction()` 之后）追加两个约束函数的输出
- 美股场景下两个函数均返回空字符串，prompt 完全不变

**向后兼容性验证**:
- `format_limit_constraint(11.0, 9.0, "US_STOCK")` → `""` ✓
- `format_t_plus_1_constraint("...", "...", "US_STOCK")` → `""` ✓
- 所有新字段使用 `state.get()` 带默认值，无需 state 预填 ✓

### 2026-05-06: 新建 tests/test_a_share.py — A 股集成测试套件（223 行）

**文件**: `tests/test_a_share.py` (新建，223 行)

**6 个测试类，24 个测试用例**：

| 测试类 | 测试内容 | 依赖 |
|--------|---------|------|
| `TestDataRouting` | VENDOR_LIST 排序、VENDOR_METHODS 完整、default_config 默认值 | 无 |
| `TestStockData` | 4 只多 ticker 数据获取（parametrize）、fundamentals、balance_sheet | akshare + 网络 |
| `TestTradingCalendar` | is_trade_day、next/prev_trade_day | akshare + 网络 |
| `TestConstraints` | 涨跌停价、涨跌停率（板块/ST）、约束文本格式、T+1 约束（4 种场景） | 纯逻辑 |
| `TestAgentState` | AgentState 新增 5 个 A 股字段的 AST 结构检查 | ast 静态解析 |
| `TestModuleImports` | ak share 9 函数、calendar 3 函数、constraint 4 函数可导入 | 无 (lazy import) |

**验证结果**:
- 16 个非网络测试全部通过 ✓
- 网络测试（TestStockData、TestTradingCalendar）需要 akshare 环境，隔离运行
- AST 结构检查发现的陷阱：`AnnAssign` 的 `target` 可能是 `ast.Name`（.id）而非 `ast.Attribute`（.attr），当有默认值赋值时需要用 `isinstance(n.target, ast.Name)` 处理
