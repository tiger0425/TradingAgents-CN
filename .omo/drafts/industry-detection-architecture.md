# Draft: 三层行业检测架构改进

## Requirements (confirmed)
- 三层架构：行业检测(L1) → 框架匹配(L2) → 一致性校验(L3)
- TDD 策略，857 现有测试必须保持通过
- 不改变现有 Agent system_message 基础结构

## Technical Decisions
- IndustryClassifier 服务封装 get_industry() 返回结构化结果
- 注入点：AgentState + build_instrument_context()
- 一致性校验：先规则后 LLM（渐进式）
- 框架定义外部化（JSON/YAML）

## Research Findings
- Context.industry 只到 Planner 级别 → AgentState 无 industry 字段（核心 gap）
- executor.py:_build_init_state() 是丢失点
- test_e2e_600418.py 已有幻觉检测基础

## Scope
- IN: IndustryClassifier、AgentState+industry、Agent 提示词注入、运行时校验
- EXCLUDE: 全量行业分类体系、Legacy 路径、LLM-based 一致性（先规则）
