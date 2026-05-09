# TradingAgents 股票助手改造 - 问题跟踪

## 已知限制
- akshare 接口可能有变化（依赖 sina 财经）
- 批量扫描 30 只股票 × 每次 ~2 分钟 = 约 1 小时，OpenClaw 需要处理超时
- 飞书/Server酱 webhook 可能有频率限制
- `requests` 依赖需要在 pyproject.toml 中确认已存在
