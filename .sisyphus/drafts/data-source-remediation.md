# 草稿：数据源补齐方案

## 需求（已确认）

- **补齐路线**：混合方案 —— 稳定数据用 Python 库、实时快讯/舆情用爬虫、机构持仓用付费 API
- **付费接受度**：可接受小额付费，需先分析各家付费方案的费率和数据完整度
- **7 类缺失数据**：公告/新闻、北向资金明细、机构持仓/股东变化、融资融券数据、大盘资金流（北向分类）、舆情监控、监管/政策快讯

## 现有数据架构分析

### 数据采集模块结构

```
tradingagents/dataflows/
├── akshare.py          # 主数据采集，14 个 get_ 函数
├── interface.py        # 统一入口，按类别路由到 vendor
├── config.py           # 全局配置管理
├── default_config.py   # 默认配置（数据 vendor 选择）
├── macro_context.py    # 宏观背景（美股、汇率、商品、VIX、北向资金、国债）
├── market_context.py   # A股市场背景（指数、板块轮动、资金流、市场宽度）
├── y_finance.py        # Yahoo Finance vendor
├── alpha_vantage.py    # Alpha Vantage vendor
├── guosen.py           # 国信证券 vendor（空壳）
├── yfinance_news.py    # Yahoo Finance 新闻
├── alpha_vantage_news.py  # Alpha Vantage 新闻
├── cache.py            # 数据缓存
├── position_risk.py    # 持仓风险评估
├── position_utils.py   # 持仓工具
├── a_share_anomalies.py  # A股异常检测
├── a_share_calendar.py   # A股交易日历
├── a_share_constraints.py # A股交易约束
├── stockstats_utils.py  # technical indicator utilities
├── trading_plan.py      # 交易计划生成
└── utils.py             # 通用工具
```

### 数据分类体系（interface.py）

```python
TOOLS_CATEGORIES = {
    "core_stock_apis": ["get_stock_data", "get_current_price"],
    "technical_indicators": ["get_indicators"],
    "fundamental_data": ["get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement"],
    "news_data": ["get_news", "get_global_news", "get_insider_transactions"],
}
```

### 现有 akshare 函数清单（14个）

| # | 函数 | 数据源 | 状态 |
|---|------|--------|------|
| 1 | `get_stock_data` | Sina via akshare | ✅ 正常 |
| 2 | `get_indicators` | stockstats wrap | ✅ 正常 |
| 3 | `get_fundamentals` | akshare 基本面 | ✅ 正常 |
| 4 | `get_balance_sheet` | akshare 资产负债表 | ✅ 正常 |
| 5 | `get_cashflow` | akshare 现金流 | ✅ 正常 |
| 6 | `get_income_statement` | akshare 利润表 | ✅ 正常 |
| 7 | `get_news` | EastMoney via akshare | ⚠️ 有限 |
| 8 | `get_global_news` | akshare 宏观新闻 | ⚠️ 有限 |
| 9 | `get_insider_transactions` | akshare | ⚠️ 有限 |
| 10 | `get_current_price` | Sina hq.sinajs.cn | ✅ 实时 |
| 11 | `get_social_sentiment` | EastMoney + 雪球 via akshare | ⚠️ 基础 |
| 12 | `get_real_time_quotes` | EastMoney via akshare | ✅ 实时 |
| 13 | `get_individual_notices` | akshare 个股公告 | ⚠️ 基础 |
| 14 | `get_research_reports` | akshare 研报 | ⚠️ 基础 |

### 宏观/市场背景数据（已有但部分断裂）

- **北向资金**：`macro_context.py` 中 `_fetch_northbound_flow()`，主用 EastMoney 汇总，历史 fallback。但 EastMoney 2024-08-16 已停止发布详细数据
- **大盘资金流**：`market_context.py` 中 `_fetch_capital_flow()`，全市场主力资金流，无北向分类
- **市场宽度**：`_fetch_market_breadth()`，上证挂牌数和成交额
- **板块轮动**：`_fetch_sector_rotation()`，行业资金流排名

### Agent 数据消费者

- `News Analyst` → 消费 `get_news` + `get_global_news`
- `Social Media Analyst` → 消费 `get_social_sentiment`
- `Fundamentals Analyst` → 消费基本面数据
- `Market Analyst` → 消费 macro/market context
- 目前没有专门的：持仓分析师、融资融券分析师、监管/政策分析师

---

## 7 类缺失数据的替代方案分析

### 1. 公告/新闻（❌ News Analyst 空）
**现有**：`get_news` (EastMoney), `get_individual_notices` (个股公告)
**问题**：Sina 接口有限，新闻覆盖不全
**方案**：
- akshare: `stock_notice_report()` - 巨潮资讯网公告（免费，覆盖全）
- akshare: `stock_info_a_code_name()` + 巨潮公告爬取
- 付费：tushare pro `disclosure` 接口（200/年基础版）
- 自建爬虫：巨潮资讯网 (cninfo.com.cn) 公告爬取
- 自建爬虫：上交所/深交所官网公告

### 2. 北向资金明细（⭐ ⭐ 宏观不完整）
**现有**：`_fetch_northbound_flow()` 使用 EastMoney 汇总 + 历史 fallback
**问题**：EastMoney 2024-08-16 起停止发布详细数据
**方案**：
- akshare: `stock_hsgt_board_rank_em()` - 沪深港通板块排名（北向持股比例排名）
- akshare: `stock_hsgt_individual_em()` - 沪深港通个股资金流（免费，可能有限制）
- akshare: `stock_hsgt_individual_detail_em()` - 个股北向资金详细（逐笔，可能已失效）
- 替代数据源：沪/深港通官网 (Shanghai/Shenzhen Stock Connect)
- 付费：tushare pro `moneyflow_hsgt`（2000/年专业版）

### 3. 机构持仓/股东变化（⭐ ⭐ ⭐ 基本面粗糙）
**现有**：`get_fundamentals` 中有基本财务数据，无持仓明细
**方案**：
- akshare: `stock_fund_hold_detail_em()` - 基金持仓明细
- akshare: `stock_hold_control_cninfo()` - 十大股东/流通股东
- akshare: `stock_shareholder_change_em()` - 股东户数变化
- 付费：tushare pro `top10_holders` + `stk_holdernumber` + `fund_portfolio`（2000/年专业版）
- 付费：jqdatasdk `finance.STK_SHAREHOLDER` 系列（5000/年）
- 付费：rqdatac `get_shareholder` 系列（3000-8000/年）

### 4. 融资融券数据（⭐ ⭐ ⭐ 风控缺失）
**现有**：无
**方案**：
- akshare: `stock_margin_detail_sse()` / `stock_margin_detail_szse()` - 沪深融资融券明细
- akshare: `stock_margin_sse()` - 沪市融资融券汇总
- akshare: `stock_margin_underlying_info_szse()` - 深市标的
- akshare: `stock_margin_ratio_pb()` - 融资融券比率
- 代替：baostock `query_margin_data()` - 免费但仅日级别
- 付费：tushare pro `margin_detail` + `margin`（2000/年专业版）

### 5. 大盘资金流-北向分类（⭐ ⭐ ⭐ 资金面不精准）
**现有**：`_fetch_capital_flow()` 全市场主力资金流，无北向分类
**方案**：
- akshare: `stock_market_fund_flow()` - 市场资金流（已有，增强分类）
- akshare: `stock_sector_fund_flow_rank()` - 行业资金流（已有）
- akshare: `stock_individual_fund_flow()` - 个股资金流（新增）
- 付费：tushare pro `moneyflow` + `moneyflow_hsgt`（分类齐全）

### 6. 舆情监控（⭐ ⭐ 消息滞后）
**现有**：`get_social_sentiment` (EastMoney 关注 + 雪球关注)
**问题**：仅基础关注度数据，无情绪分析
**方案**：
- akshare: 已有 EastMoney comment、雪球关注、热度排名
- 自建爬虫：东方财富股吧（guba.eastmoney.com）- 帖子爬取
- 自建爬虫：雪球（xueqiu.com）热门讨论
- 自建爬虫：微博财经话题
- 付费：tushare pro 无直接舆情，但可结合 news 接口
- 第三方：通联数据/万得舆情 API（较贵）

### 7. 监管/政策快讯（⭐ ⭐ 需爬虫）
**现有**：无专门来源
**方案**：
- akshare: `stock_info_global_news_em()` 或类似国际财经新闻
- 自建爬虫：证监会官网 (csrc.gov.cn) 最新政策
- 自建爬虫：央行官网 (pbc.gov.cn) 货币政策
- 自建爬虫：新华网财经频道
- 自建爬虫：财联社 (cls.cn) 快讯（有免费电报频道）
- RSS：多个财经媒体 RSS 聚合

---

## 付费数据源对比

| 源 | 费用 | 北向明细 | 机构持仓 | 融资融券 | 公告 | 优势 | 劣势 |
|---|------|---------|---------|---------|------|------|------|
| **tushare pro** | 200/年（基础）<br>2000/年（专业）| ✅ 专业版 | ✅ 专业版 | ✅ 专业版 | ✅ | 覆盖面广，积分制 | 需积分，API 频率限制 |
| **jqdatasdk** | 5000/年 | ✅ | ✅ | ✅ | ✅ | 数据质量高，回测兼容 | 贵，需机构认证 |
| **rqdatac** | 3000-8000/年 | ✅ | ✅ | ✅ | ✅ | 数据全，Python SDK好 | 贵 |
| **baostock** | 免费 | ❌ 无 | ❌ 无 | ⚠️ 基础 | ❌ 无 | 免费，无限制 | 数据粗糙，更新慢 |
| **akshare** | 免费 | ⚠️ 部分 | ⚠️ 部分 | ✅ 有 | ✅ 有 | 免费，数据源多 | 不稳定，依赖第三方 |

## 推荐组合方案

| 数据类别 | 首选方案 | 备选方案 | 预估费用 |
|---------|---------|---------|---------|
| 公告/新闻 | akshare + 巨潮爬虫 | tushare pro 基础版 | 0-200/年 |
| 北向资金明细 | akshare 板块+个股 | tushare pro 专业版 | 0-2000/年 |
| 机构持仓 | akshare 基金持仓+十大股东 | tushare pro 专业版 | 0-2000/年 |
| 融资融券 | akshare 沪深深交所 | baostock 备用 | 0 |
| 大盘资金流 | akshare 增强分类 | tushare pro 基础版 | 0-200/年 |
| 舆情监控 | 东方财富+雪球爬虫 | 通联舆情 API | 0-5000/年 |
| 监管/政策 | 证监会/央行/财联社爬虫 | — | 0 |

## 技术决策

- **数据 vendor 扩展**：在 `dataflows/` 下新增 `tushare.py` vendor 模块（可选付费开关）
- **爬虫基础设施**：新增 `dataflows/crawlers/` 子目录，统一爬虫框架
- **新增数据分类**：在 `interface.py` 中增加 `position_data`、`margin_data`、`macro_flow_data`、`sentiment_data` 分类
- **Agent 扩展**：新增 `position_analyst.py` 持仓分析师
- **数据格式统一**：所有新函数返回 Markdown 格式字符串（与现有模式一致）
- **优雅降级**：所有新数据源需支持 fallback，数据不可用时不阻断分析流程
