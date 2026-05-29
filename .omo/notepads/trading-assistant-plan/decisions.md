# TradingAgents 股票助手改造 - 架构决策

## ADR-001: CLI 非交互式模式使用 typer 子命令而非 argparse
- 原因：现有 CLI 已使用 typer，新增子命令自然扩展；argparse 与 typer 混用增加维护复杂性
- 所有新命令注册到 `cli/main.py` 的 `app` 上

## ADR-002: watchlist 存储为 JSON 文件而非数据库
- 原因：数据量小（数十只股票），JSON 文件零依赖、易修改、可版本控制
- 路径：`~/.tradingagents/watchlist.json`

## ADR-003: JSON 输出使用 Python 原生 json 模块
- 原因：避免额外依赖；datetime/Decimal 通过自定义 encoder 处理
- 策略：所有输出前调用 `json.dumps()` 确保可序列化

## ADR-004: 通知抽象层使用接口模式
- 原因：支持多渠道（飞书、微信），接口模式便于扩展新渠道
- 设计：`Notifier` base class → `FeishuNotifier` / `ServerChanNotifier` / `PushPlusNotifier`
