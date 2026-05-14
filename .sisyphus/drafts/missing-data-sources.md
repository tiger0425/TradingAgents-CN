# 草案：缺失数据源补齐方案

## 用户需求
补齐以下7类缺失数据源：公告/新闻、北向资金明细、机构持仓/股东变化、融资融券数据、大盘资金流(北向分类)、舆情监控、监管/政策快讯

## 用户偏好确认
- **补齐路线**：混合方案（稳定数据用 Python 库，实时快讯/舆情用爬虫，核心数据可小额付费）
- **付费接受度**：可接受小额付费（¥200-500/年级别）
- **需要分析**：有哪些付费数据源可选，费用和数据完整度对比

## 现有项目架构（已摸清）

### 数据采集模块
- `tradingagents/dataflows/akshare.py` — 主要A股数据源，14个公开函数
- `tradingagents/dataflows/macro_context.py` — 宏观环境数据（北向资金汇总、汇率、债券等）
- `tradingagents/dataflows/market_context.py` — 市场数据（指数、板块轮动、资金流）
- `tradingagents/dataflows/y_finance.py` — 美股数据
- `tradingagents/dataflows/alpha_vantage.py` — 美股/全球数据
- `tradingagents/dataflows/interface.py` — 统一接口路由
- `tradingagents/dataflows/config.py` — 配置管理（vendor 选择）

### 数据消费方 (Agent)
- `tradingagents/agents/analysts/news_analyst.py` — 新闻分析师（使用 get_news + get_global_news）
- `tradingagents/agents/analysts/social_media_analyst.py` — 舆情分析师
- `tradingagents/agents/analysts/fundamentals_analyst.py` — 基本面分析师
- `tradingagents/agents/analysts/market_analyst.py` — 市场分析师
- `tradingagents/agents/utils/market_context_tools.py` — 市场上下文字段引用

### 现有数据源状态
- 默认全部使用 akshare（default_config.py line 40-44）
- 北向资金使用 `stock_hsgt_fund_flow_summary_em`（汇总），明细断更后使用 `stock_hsgt_hist_em` 历史回溯
- 新闻使用 `stock_news_em`（东方财富），有 `get_individual_notices` 和 `get_research_reports` 但仅 CLI 用
- 社交舆情 `get_social_sentiment` 已有实现（东方财富评论 + 雪球 + 热度）
- 资金流 `stock_market_fund_flow`（大盘整体，非北向分类）

## 调研结论：每类缺失数据的解决方案

### 1. 公告/新闻 ⭐⭐
- **现状**：akshare `stock_news_em` 有新闻标题+摘要，`get_individual_notices` 有个股公告
- **推荐**：akshare 免费已有能力，增强即可
  - 新增：`ak.stock_notice_report(symbol)` 获取巨潮资讯公告全文
  - 可选：tushare pro 无新闻接口
- **难度**：低，akshare 已有接口，直接封装

### 2. 北向资金明细 ⭐⭐
- **现状**：macro_context.py 用汇总接口，明细（EastMoney）已于2024-08-16停更
- **推荐方案**：
  - tushare pro `moneyflow_hsgt`（沪深港通资金流向，120积分）— 有个股级别的北向持股明细
  - akshare `stock_hsgt_hold_stock_em`（沪深港通持股明细，东方财富个股）— 可拉取持股量
  - 备用：akshare `stock_hsgt_hist_em`（已在用作为 fallback）
- **选择**：**优先 tushare pro**（数据更规范、稳定），akshare 做备用

### 3. 机构持仓/股东变化 ⭐⭐⭐
- **现状**：完全缺失，未实现
- **akshare 已有能力**：
  - `stock_institute_hold(quarter)` — 机构持股一览表
  - `stock_institute_hold_detail(stock, quarter)` — 机构持股详情
  - `stock_gdfx_free_holding_change_em(date)` — 十大流通股东变动
  - `stock_gdfx_holding_analyse_em(date)` — 十大股东分析
  - `stock_gdfx_free_holding_detail_em(date)` — 十大流通股东明细
- **tushare pro 能力**：
  - `top10_holders` (120积分) — 前十大股东
  - `top10_floatholders` (120积分) — 前十大流通股东
  - `stk_holdernumber` (120积分) — 股东人数
  - `stk_holdertrade` (2000积分) — 股东增减持
  - `hk_hold` (2000积分) — 沪深港通持股明细
- **选择**：**akshare 优先**（免费且覆盖足够），tushare pro 做增强（股东人数、增减持）

### 4. 融资融券数据 ⭐⭐⭐
- **现状**：完全缺失，未实现
- **akshare 已有能力**：
  - 上海/深圳融资融券汇总
  - 上海/深圳融资融券明细
  - `stock_margin_underlying_info_szse()` — 标的证券
- **tushare pro 能力**：
  - `margin` (120积分) — 融资融券交易汇总
  - `margin_detail` (120积分) — 融资融券交易明细（个股）
  - `margin_secs` (免费) — 融资融券标的列表
- **选择**：**akshare 优先**（免费），tushare pro 做备用

### 5. 大盘资金流(北向分类) ⭐⭐⭐
- **现状**：market_context.py 已有大盘资金流，但未按北向/南向分类
- **需要**：按北向资金类型（沪股通/深股通）分类的资金流向
- **akshare 能力**：`stock_hsgt_fund_flow_summary_em()` 提供北向/南向分类汇总
- **tushare pro 能力**：`moneyflow_hsgt` (120积分) — 沪深港通资金流向
- **选择**：用 akshare 已有接口增强 market_context.py

### 6. 舆情监控 ⭐⭐
- **现状**：`get_social_sentiment()` 已实现（东方财富评论 + 雪球 + 热度排名），基本可用
- **增强方向**：
  - 增加 `ak.stock_hot_rank_em()` 热度排行
  - 可选：自建爬虫爬取微博热搜、股吧热帖
  - 可选：tushare pro 无舆情接口
- **选择**：akshare 免费已有能力为主，按需加爬虫

### 7. 监管/政策快讯 ⭐⭐
- **现状**：完全缺失，未实现
- **推荐方案**：
  - 爬取：证监会官网（csrc.gov.cn）— 政策发布
  - 爬取：央行官网（pbc.gov.cn）— 货币政策
  - akshare 有 `macro_china` 系列宏观数据但非快讯
  - 可考虑：东方财富/同花顺 快讯 RSS
- **选择**：自建爬虫（requests + BeautifulSoup），存储到缓存

## 付费数据源对比总结

| 数据源 | 年费 | 融资融券 | 机构持仓 | 北向明细 | 新闻公告 | 推荐场景 |
|--------|------|----------|----------|----------|----------|----------|
| akshare | 免费 | ✅(汇总+明细) | ✅(机构/股东) | ✅(汇总,明细断更) | ✅(新闻+公告) | 主力数据源 |
| tushare pro | ¥200起(2000积分) | ✅(120积分) | ✅(120积分) | ✅(120积分) | ❌ | 核心增强 |
| baostock | 免费 | ❌ | ❌ | ❌ | ❌ | 不适合 |
| jqdatasdk | 试用3月免费 | ✅ | ✅ | ⚠️ | ⚠️ | 备选 |
| rqdatac | 试用15天免费 | ⚠️ | ⚠️ | ⚠️ | ⚠️ | 备选 |

## 推荐方案

**主要路线**：
1. akshare (免费) — 补齐所有免费可用能力（融资融券、机构持仓、公告、舆情、资金流北向分类）
2. tushare pro (¥200/年, 2000积分) — 增强北向资金明细、机构持仓明细（股东人数/持股变化）、融资融券明细
3. 自建爬虫 — 监管/政策快讯（证监会、央行官网）

**技术决策**：
- 新增 `dataflows/tushare.py` 模块，遵循与 akshare.py 相同接口规范
- 在 `interface.py` 中添加 tushare vendor 支持
- 在 `default_config.py` 中为各类数据配置多级 fallback（akshare → tushare → None）
- 爬虫用 `requests` + `BeautifulSoup` 或 `lxml`（无需 Selenium，目标站均可直爬）

## 范围界定
- **IN**：7类缺失数据的采集、封装、Agent 工具注册
- **OUT**：不改变 LLM 调用逻辑，不改变交易决策框架，不改变回测系统
