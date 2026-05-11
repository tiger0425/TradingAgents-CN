# 国信证券数据源集成计划

## 摘要

将 6 个国信证券 skill（行情查询、财务数据、宏观经济、智能选股、基金对比、ETF筛选）封装为 `tradingagents/dataflows/guosen.py` 模块，作为项目的新数据源。

## 背景

当前项目通过 `akshare` 获取 A 股数据。国信证券提供了更丰富的 API 接口，包括：
- 实时行情（支持沪深/北交所/港股/美股）
- 财务三表（利润表、资产负债表、现金流量表）
- 宏观经济指标
- 智能选股
- 基金对比分析
- ETF 筛选

所有接口共用同一 API 基础地址 `https://dgzt.guosen.com.cn/skills`，通过 URL 查询参数 `apiKey` 鉴权。

## 目标

- [ ] 创建 `tradingagents/dataflows/guosen.py` 模块
- [ ] 封装 6 个 skill 共 13+ 个公开函数
- [ ] 返回类型统一为 `str`（兼容 TradingAgents tool system）
- [ ] 使用 `Annotated` 类型提示（匹配 akshare.py 风格）
- [ ] 添加环境变量到 `.env.example`
- [ ] 更新 `default_config.py` 的 `data_vendors` 选项

## 技术决策

### 1. HTTP 库选择

**决策**: 使用 `requests`（已存在项目依赖），不使用 `httpx`。

**理由**: `requests` 已在 `pyproject.toml` 中列出；skill 脚本本身用 `urllib` 但封装层不需要异步。

### 2. SSL 兼容

**决策**: 创建 `_create_session()` 工厂函数，生成带有 `verify=False` + 传统 TLS 重协商支持的 `requests.Session`。

**理由**: 国信 API 服务器使用旧版 TLS，需要 `OP_LEGACY_SERVER_CONNECT` 标志。

### 3. API 密钥管理

**决策**: 三个环境变量，统一读取：
- `GS_API_KEY`: 行情查询、财务数据、宏观经济
- `COZE_GUOSEN_API_KEY_7627085587157205043`: 基金对比
- `COZE_GUOSEN_API_KEY_7627056463827140634`: ETF筛选器
- 智能选股使用 `GS_API_KEY` 并通过 URL 参数 `apiKey` 传递

### 4. 模块结构

```
tradingagents/dataflows/guosen.py
├── 常量与配置
│   ├── BASE_URL, SOFT_NAME, TIMEOUT
│   ├── API key 读取（从 os.environ）
│   └── 市场代码映射
├── 内部辅助
│   ├── _create_session() → requests.Session (SSL)
│   ├── _make_request(url, params) → Dict
│   └── _code_to_market(symbol) → (code, set_code, market_str)
├── 行情查询（5 个函数）
│   ├── get_real_time_quote()
│   ├── get_multi_quote()
│   ├── get_fund_flow()
│   ├── get_rankings()
│   └── get_historical_hq()
├── 财务数据（3 个函数）
│   ├── get_balance_sheet()
│   ├── get_income_statement()
│   └── get_cashflow_statement()
├── 宏观经济（1 个函数）
│   └── get_macro_data()
├── 智能选股（1 个函数）
│   └── screen_stocks()
├── 基金对比（1 个函数）
│   └── compare_funds()
└── ETF筛选（2 个函数）
    ├── filter_etf_pro()
    └── filter_etf_custom()
```

## 验证策略

1. `lsp_diagnostics` 检查 guosen.py 无语法/类型错误
2. 运行 `python -c "from tradingagents.dataflows.guosen import *"` 确保导入成功
3. 运行 `pytest tests/ -x -q --timeout=30` 确保无回归
4. 手动检查各函数的 docstring 和参数说明

## 执行策略

所有工作按以下顺序执行：
1. 创建 `guosen.py` 完整模块
2. 更新 `.env.example`
3. 更新 `default_config.py`
4. 验证（lsp + 导入 + 测试）
