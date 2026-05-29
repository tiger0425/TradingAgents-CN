# 知识消费实施计划 — 架构决策

## ADR 引用
- ADR-005: ContextAssembly 作为独立节点
- ADR-006: AgentState 用结构化字典
- ADR-007: 缓存层用磁盘 + 命名空间，零外部依赖
- ADR-008: 双重知识消费通道（Prompt 注入 + MCP）
- ADR-009: Confidence 标签体系
- ADR-010: Wiki 导航作为 RAG 轻量替代

## 实现决策
- DataCache 使用 `~/.tradingagents/cache/` 作为缓存根目录
- 命名空间: ohlcv/ benchmark/ fundamentals/ spot/
- 原子写入: tmp + os.replace
