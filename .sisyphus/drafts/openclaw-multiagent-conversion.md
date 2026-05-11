# 草案：TradingAgents 迁移至 OpenClaw 多 Agent 架构分析

## 项目概况
- **项目名**: TradingAgents-CN（基于 TauricResearch/TradingAgents 二次开发）
- **技术栈**: Python + LangGraph + LangChain + 多种 LLM 供应商（10家）
- **核心功能**: 多智能体 LLM 金融交易框架，模拟真实交易公司运作
- **特色**: 支持 A 股（akshare 数据源），中文输出
- **版本**: v0.2.4

## 当前架构（已确认）

### 编排层（LangGraph StateGraph）
- 入口类：`TradingAgentsGraph`
- State: `AgentState`（扩展 MessagesState，含 20+ 字段）
- 图拓扑：START → 分析师序列 → 牛熊辩论循环 → 研究经理 → 交易员 → 三方风险辩论 → 投资组合经理 → END
- 条件路由：`should_continue_debate`（count 控制轮次）、`should_continue_risk_analysis`
- 检查点：LangGraph SqliteSaver（可选），每股票一个 SQLite 数据库

### 13 个 Agent 分类
**分析师团队（4个）**- 有工具绑定：
- Market Analyst：get_current_price, get_stock_data, get_indicators
- Social Media Analyst：get_news
- News Analyst：get_news, get_global_news, get_insider_transactions
- Fundamentals Analyst：get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement

**研究员团队（3个）**- 无工具，纯推理：
- Bull Researcher：llm.invoke(prompt)，辩论偏多头
- Bear Researcher：llm.invoke(prompt)，辩论偏空头
- Research Manager：结构化输出 ResearchPlan

**交易员（1个）**- 结构化输出：
- Trader：bind_structured(TraderProposal)，综合研究员意见生成交易提案

**风控团队（4个）**- 无工具，纯推理：
- Aggressive Debator：三方风险辩论
- Conservative Debator
- Neutral Debator
- Portfolio Manager：结构化输出 PortfolioDecision，含 A 股涨跌停/T+1 约束

### 数据层
- 四层架构：LLM → 工具(@tool) → 路由(route_to_vendor) → vendor 实现
- 当前默认全部指向 akshare（A 股）
- 支持三类 vendor: akshare, yfinance, alpha_vantage
- 10 个数据函数，全部返回 str（CSV/Markdown），适配 LLM 消费

### LLM 客户端
- 9 家供应商，10 种客户端（OpenAI 含兼容组 7 合 1）
- 工厂模式 `create_llm_client(provider, model, base_url, **kwargs)`
- 两类 LLM：deep_thinking_llm（研究经理+PM）+ quick_thinking_llm（其余）
- 所有客户端通过 Normalized* 子类统一响应格式

### 持久化
- 决策日志：每次运行后 LLM 反思 → ~/.tradingagents/memory/trading_memory.md
- 检查点恢复：LangGraph SqliteSaver，中断后从断点继续

## 范围边界
- INCLUDE: 分析当前架构、评估迁移可行性、制定迁移方案
- EXCLUDE: 实际代码实现

## 关键架构特征（影响迁移决策）
1. 分析师有工具+LangGraph ToolNode，研究员/交易员/风控无工具纯推理
2. 分析师间是顺序执行，研究员辩论是循环执行
3. 状态在 LangGraph AgentState 中共享（TypedDict）
4. 消息清除是关键（Anthropic 兼容性）
5. 结构化输出仅限 3 个管理者 agent

## 决策待定
- [ ] 迁移范围（全部 vs 核心工作流）
- [ ] 目标：替换 LangGraph 还是包裹式集成？
- [ ] 工具层：保留 LangChain @tool 还是转换为 OpenCode MCP 工具？
- [ ] 测试策略

## 迁移可行性评估

### 方案 A：完全迁移（替换 LangGraph）
用 OpenCode 的 task() 调用替换 LangGraph StateGraph。每个 agent 节点变成 OpenCode task，状态通过文件传递。
- **代码改动量**：约 80% 代码需重写
- **核心挑战**：状态管理（AgentState 20+ 字段）、条件路由、ToolNode 循环、检查点恢复

### 方案 B：混合方案（保留 LangGraph，包裹为 Skill）
保留现有 LangGraph 核心，将框架暴露为 OpenCode 技能/命令。
- **代码改动量**：约 20%，主要是包装层
- **优势**：保留现有架构，增量添加 OpenCode 集成

### 方案 C：原生重设计（OpenCode 原生多 Agent）
完全基于 OpenCode 的 task 模型重新设计 agent 系统。
- **代码改动量**：约 90%，本质是完整重写
- **优势**：最符合 OpenCode 设计哲学

### 三种方案对比
| 维度 | 方案A (完全迁移) | 方案B (混合) | 方案C (原生重设计) |
|------|:---:|:---:|:---:|
| 代码改动量 | 80% | 20% | 90% |
| 保留 LangGraph | 否 | 是 | 否 |
| OpenCode 原生度 | 中 | 低 | 高 |
| 风险 | 高 | 低 | 极高 |
| 开发周期 | 3-4周 | 1-2周 | 5-8周 |
