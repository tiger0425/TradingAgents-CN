# ADR: OpenCode OMO DeepSeek V4 前缀缓存适配优化

> **文档类型**: ADR (Architecture Decision Record)  
> **日期**: 2026-05-29  
> **状态**: 提案  
> **关联文档**: `docs/架构决策记录.md`（TradingAgents 业务架构）、`oh-my-openagent.deepseek-v4.json`、`opencode.json`  
> **对标参考**: [esengine/DeepSeek-Reasonix](https://github.com/esengine/DeepSeek-Reasonix)（v0.52，MIT）  
> **分析范围**: OpenCode OMO（oh-my-openagent@v4.5.0）的 DeepSeek v4 前缀缓存优化方案

---

## 摘要

当前开发主力模型已切换为 DeepSeek v4（flash + pro），但 OpenCode OMO 的 agent 编排层未针对 DeepSeek 的前缀缓存（prefix-cache）机制做任何优化。每一次 `task()` 委托、每一轮子 agent 调用都重新构造 prompt，导致 DeepSeek **实际缓存命中率远低于理论值（<20% vs 可实现的 >90%）**。

本 ADR 基于对 DeepSeek-Reasonix（业界唯一将前缀缓存作为核心设计约束的 coding agent）的深度分析，提出 OMO 层可移植的 5 项优化及其优先级。

---

## 背景

### 1. DeepSeek 前缀缓存的经济意义

DeepSeek 的自动前缀缓存是其最具差异化的成本优势：

| 计费项 | 价格（$/1M tokens） | 比例 |
|---|---|---|
| 缓存命中（input） | $0.05 | ~1×（基准） |
| 缓存未命中（input） | $0.50 | ~10× |
| 输出 | $2.19 | ~44× |

**核心机制**：前缀缓存仅在*完全相同的字节前缀*下激活。前缀中任何一个字节的变化都会使整个请求回退到未命中价格。

### 2. OMO 当前架构的缓存问题

```
当前 OMO 每轮 task() 调用:
┌──────────────────────────────────────────────┐
│  system prompt (内容固定，但序列化字节不固定)     │ ← 每轮重新构造
│  tool specs (同上)                              │ ← 缓存无法命中
│  few shots (同上)                               │
├──────────────────────────────────────────────┤
│  历史消息 (每次重写/重排序)                      │ ← 前缀断裂
│  当前消息                                       │
└──────────────────────────────────────────────┘
```

每个子 agent 的 prompt 在构造时包含不完全相同的字节序列（时间戳、排序、序列化选项差异），导致 **DeepSeek 无法识别为同一前缀**，每次都是 10× 价格的未命中请求。

### 3. Reasonix 的对标价值

DeepSeek-Reasonix 是**唯一一个将前缀缓存作为核心架构约束**的 coding agent。它的三大支柱中，Pillar 1（缓存优先循环）直接解决了上述问题：

> "缓存稳定不是开关，而是循环要围绕设计的不变量。—— Reasonix"

Reasonix 实现了一个生产环境验证的案例：单用户单日 435M input tokens，**99.82% 缓存命中率**，~$12 成本（无缓存时 ~$61）。

---

## 分析

### 5 项可移植优化

基于对 Reasonix 源码的深入分析，以下 5 项优化可与 OMO 的现有架构兼容，无需改写 OMO 内核。

#### 优化 1：三区域上下文分区

**Reasonix 做法**：
```
┌─────────────────────────────────────────┐
│ 不可变前缀 (IMMUTABLE PREFIX)            │ ← 会话固定，字节完全一致
│   system + tool_specs + few_shots        │   缓存命中候选
├─────────────────────────────────────────┤
│ 追加日志 (APPEND-ONLY LOG)               │ ← 单调增长，不重写
│   [assistant₁][tool₁][assistant₂]...     │   保持前序前缀不变
├─────────────────────────────────────────┤
│ 易失暂存区 (VOLATILE SCRATCH)             │ ← 每轮重置，不进 API
└─────────────────────────────────────────┘
```

**OMO 改造点**：
- `task()` 的 prompt 组装层将 system / tool_specs 序列化为确定性字节序列（规范 JSON 序列化、固定 key 顺序、去除时间戳等可变字段）
- 子 agent 的历史传递只做 append，不做 rewrite
- 将"当前轮指令"与"不可变上下文"分离

**预期收益**：前缀缓存命中率从 <20% → >90%

#### 优化 2：回合结束工具结果自动压缩

**Reasonix 做法**：每个工具结果 >3000 token 的在回合结束时自动压缩为摘要。完整内容按需 `read_file`。

**Reasonix 原话**："一次 read_file 调用比拖 12KB 内容通过每轮 prompt 便宜得多。"

**OMO 改造点**：
- 在 orchestrator 侧（即 Sisyphus 的循环逻辑中），对 `task()` 返回的 long output 自动截断
- 完整结果写入文件，按需读取
- 对 explore / librarian 等输出天然长的子 agent 效果最明显

**预期收益**：每轮 `task()` 的 context 缩小 30-50%

#### 优化 3：风暴防护（Storm Breaker）

**Reasonix 做法**：滑动窗口（默认窗口=6，阈值=3）检测 `(tool_name, args)` 相同元组，抑制重复调用并注入反思。

**OMO 改造点**：
- 在 orchestrator 的调度层增加去重检测
- 检测到连续相同的 `task()` 调用时自动阻断并通知用户
- 纯 orchestrator 行为规则改动，不改 OMO 内核

**预期收益**：防止无限循环失控，避免成本爆炸

#### 优化 4：自报告模型升级/降级

**Reasonix 做法**：
- 模型在响应开头嵌入 `<<<NEEDS_PRO>>>` 标记 → 系统自动升级当前轮到 pro
- 所有辅助调用强制用 flash（绝不浪费 pro 在简单任务上）
- 升级/降级对用户完全透明，仅通过 cost badge 反映

**OMO 改造点**：
- 当前 Sisyphus 固定用 pro（~12× 成本），很多简单任务不需要
- 在 Behavior_Instructions 中增加指令：判断当前任务复杂度，主动声明降级到 flash
- 子 agent 返回 `<<<NEEDS_PRO>>>` 时 orchestrator 自动升级其模型

**预期收益**：降低 2-5× 平均每轮成本

#### 优化 5：智能上下文折叠

**Reasonix 做法**（多级阈值决策）：
```
promptTokens/ctxMax 比率:
  > 80% → 强制总结退出
  > 75% → 折叠（保留 20% tail）
  > 78% → 激进折叠（只保留 10% tail）
  < 30% → 不动
```

折叠时用 v4-flash 做模型摘要，保留：用户原始目标（含否定约束）、关键决策、pinned skill 内容、系统提示中的高优先级约束。摘要调用复用主会话的 prefix-cache（成本几乎为零）。

**OMO 现状**：已有实验性 `preemptive_compaction`（70% threshold），但只是简单的尾部截断，不会做模型摘要。

**预期收益**：会话长度翻倍不超限，长会话推理质量不因截断下降

### 优化与架构耦合度

| 优化 | 耦合层 | 改动范围 | 实现成本 |
|---|---|---|---|
| 自动压缩 | orchestrator 行为规则 | 低（Sisyphus prompt + 结果处理） | 低 |
| 风暴防护 | orchestrator 调度层 | 低（行为规则 + 状态检测） | 低 |
| 自报告升级/降级 | agent prompt + 路由 | 低（prompt 指令） | 低 |
| 三区域分区 | task() 序列化层 | 中（需改 prompt 组装逻辑） | 中 |
| 智能折叠 | context 管理 | 中高（需调用模型做摘要） | 中 |

### ROI 评估

```
收益/成本:
  ★★★★★  自动压缩         成本极低，收益立竿见影
  ★★★★★  风暴防护         成本极低，防止灾难性成本
  ★★★★☆  自报告升级/降级   低投入，持续节约
  ★★★★☆  三区域分区        中等投入，核心机制
  ★★★☆☆  智能折叠         较高投入，长会话场景价值大
```

---

## 决策

### 决策 1：立即采用前三项低投入优化

**事项**：在 Sisyphus 的 Behavior_Instructions 中增加三条规则：

1. **工具结果自动压缩**：`task()` 返回 >3000 token 的内容自动截断为摘要，完整内容存文件
2. **风暴防护**：检测到连续 3+ 次相同内容/相同参数的 `task()` 调用时阻断并注入反思
3. **自报告模型降级**：当前任务明显不需要 pro 级别推理时，主动声明降级到 flash

**理由**：这三项是 pure prompt 工程 / orchestrator 行为规则改动，不涉及 OMO 内核修改，可以在**当前 ADR 通过后立即实施**。

### 决策 2：中期推进三区域上下文分区

**事项**：在 OMO 的 `task()` 序列化层中实现：
- 统一的 prompt 序列化规则（规范化 JSON key 顺序、去除可变字段、固定编码）
- 历史消息传递方式从"完整重传"改为"增量追加"
- 区分"不可变前缀"和"当前指令"

**理由**：这是前缀缓存优化的核心机制，收益最高。但需要 OMO 插件层配合（oh-my-openagent 的 agent 通信协议），建议作为 feature request 提交给 OMO 维护者。

### 决策 3：智能折叠作为可选增强

**事项**：在 `preemptive_compaction` 实验性功能基础上，增加模型摘要能力。当前保持现状，等到长会话场景（>50 轮）成为瓶颈时再实施。

**理由**：当前 tradingagents-cn 的会话轮数通常 <20，尾部截断已够用。智能折叠在 coding agent 场景（Reasonix 的场景）下更迫切，在金融分析场景中优先级较低。

---

## 实施计划

### Phase 1：Prompt 层优化（本周）

| 步骤 | 改动 | 文件/位置 |
|---|---|---|
| 1.1 | 工具结果自动压缩规则 | `Behavior_Instructions` 中增加后处理指令 |
| 1.2 | 风暴防护规则 | `Behavior_Instructions` + orchestrator 循环中增加状态检测 |
| 1.3 | 自报告模型降级规则 | Sisyphus system prompt 中增加复杂度评估指令 |

### Phase 2：序列化层优化（下个版本）

| 步骤 | 改动 | 牵涉方 |
|---|---|---|
| 2.1 | 确定 prompt 序列化规范 | OMO 插件配置 |
| 2.2 | task() 增量追加协议 | OMO 插件（oh-my-openagent） |
| 2.3 | 不可变前缀缓存 | task() 调用方（Sisyphus） |

### Phase 3：评估与迭代

| 指标 | 测量方式 | 目标 |
|---|---|---|
| 缓存命中率 | DeepSeek API 返回的 `prompt_cache_hit_tokens` | >50% |
| 每轮 token 消耗 | 按 agent 类型统计 | 降低 40% |
| 爆费事件 | 单次会话无限循环次数 | 0 |

---

## 风险与约束

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| 字节序列优化导致 prompt 格式错误 | 低 | 中 | 加验证步骤，回归测试 |
| 模型降级后任务质量下降 | 中 | 中 | 降级仅在明确安全时触发，模型可自行升级 |
| 增量追加协议改变 OMO 兼容性 | 低 | 高 | 保持向后兼容，Phase 2 前先在沙箱验证 |
| 缓存命中率提升效果低于预期 | 中 | 低 | 先评估 Phase 1 效果再决定是否推进 Phase 2 |

---

## 成功标准

- [ ] Phase 1 完成后，单轮 `task()` 调用 token 消耗降低 ≥30%
- [ ] 无新增暴费事件（工具调用失控导致成本超支）
- [ ] 子 agent 输出质量在模型降级/升级前后无退化
- [ ] 缓存命中率从基线提升 2× 以上
- [ ] 所有改动保持与 OMO v4.5.0 兼容

---

## 附录：对标参考关键数据

### Reasonix 缓存基准（公开数据）

```
用户: 真实用户，单日（2026-05-01）
Input tokens: 435M
缓存命中率: 99.82%
实际成本: ~$12
无缓存估算成本: ~$61
模型: deepseek-v4-flash
```

### OMO 当前配置速查

```
oh-my-openagent: v4.5.0
主模型: deepseek/deepseek-v4-pro（Sisyphus）
子模型: deepseek/deepseek-v4-flash（explore/librarian/...）
上下文阈值: preemptive_compaction at 70%
```

### Reasonix 关键源码引用

| 模块 | 功能 | 文件 |
|---|---|---|
| AppendOnlyLog | 前缀不可变日志 | `src/memory/runtime.ts` |
| ContextManager.fold | 智能上下文折叠 | `src/context-manager.ts` |
| StormBreaker | 风暴防护 | `src/repair/storm.ts` |
| ToolCallRepair | 工具调用修复管线 | `src/repair/index.ts` |
| scavengeToolCalls | 从 reasoning 中捞取调用 | `src/repair/scavenge.ts` |
| CacheFirstLoop.step | 完整回合循环 | `src/loop.ts` |
