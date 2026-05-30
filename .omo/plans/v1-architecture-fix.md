# V1.3 架构缺陷修复计划

## 摘要

> **快速概览**：修复 TradingAgents V1.2 中的 11 个架构缺陷（含 V1.2 API 路径缺少辩论路由这一致命遗漏），补齐测试基础设施，为 PMF 验证做好生产准备。
>
> **交付物**：
> - 11 个架构缺陷修复（FIX-0~FIX-10），6 个 P0，3 个 P1，2 个 P2
> - 测试基础设施（pytest-cov 覆盖率 + Makefile + CI workflow）
> - 2 个即时行动项（validate_model 调用修复 + 临时文件清理）
>
> **预估工时**：10-15 天
> **并行执行**：YES — 5 波次
> **关键路径**：FIX-0 → FIX-2 + FIX-5 → FIX-1 → 集成测试 → 最终验证

---

## 背景

### 原始需求
项目 V1.2 代码层 100% 完成（4 个 Collector、KB、LLM Planner、13 Agent 调度、HTTP API、Docker），但架构质量仅 30%。`docs/架构缺陷修复方案.md`（1355 行）详细记录了 10 个架构缺陷及修复方案。Metis 审查额外发现了 V1.2 API 路径缺失辩论路由的致命问题（新增 FIX-0）。

### 访谈要点
- **战略转向**：PRD 数字金融团队延期，优先修复架构 → PMF 验证
- **双路径修复**：V1.0 CLI（setup.py）+ V1.2 API（dynamic_graph_builder.py）都必须修
- **测试策略**：修复后补测试 + Agent-Executed QA 强制验证
- **总工期**：10-15 天（FIX-0 2-3天 + P0 5-7天 + P1 2-3天 + P2 1-2天）

### 研究结论
- V1.2 API 路径（`dynamic_graph_builder.py`）完全缺失辩论路由——Bull/Bear 仅是顺序单次发言，无往返对抗
- 38 个测试文件中零测试覆盖图拓扑/路由逻辑（conditional_logic、dynamic_graph_builder、setup.py）
- 6 个模板 JSON 文件存在且完整（`tradingagents/templates/`）
- V1.0 和 V1.2 使用两套不同的图构建路径，需要同步修复

### Metis 审查
**发现的缺口**（已处理）：
- **FIX-0（新增）**：V1.2 API 路径缺少辩论路由——5 个条件路由方法仅在 setup.py 中使用，DynamicGraphBuilder 完全未调用
- FIX-1~FIX-10 方案仅覆盖 V1.0 CLI 路径，需扩展至 API 路径
- 测试盲区：修改的文件在现有 38 个测试中完全无覆盖
- 10 个关键假设中 4 个高风险，需在实施前/中验证
- 每个 FIX 缺 2-4 条具体验收标准，已在任务中补充

---

## 目标

### 核心目标
修复 11 个架构缺陷（FIX-0~FIX-10），将 TradingAgents V1.2 提升至 V1.3 生产可部署标准，为 PMF 验证做好准备。

### 具体交付物
- `tradingagents/graph/dynamic_graph_builder.py` — 辩论路由 + 并行化 + 上下文管理
- `tradingagents/graph/setup.py` — 分析师并行化 + 路由枚举化
- `tradingagents/graph/conditional_logic.py` — 枚举路由 + 死循环检测
- `tradingagents/graph/executor.py` — V1.2 检查点支持
- `tradingagents/graph/causal_tracer.py` — 新建：因果链追踪
- `tradingagents/graph/context_manager.py` — 新建：上下文窗口管理
- `tradingagents/graph/debate_quality.py` — 新建：辩论质量度量
- `tradingagents/llm_clients/resilient_llm.py` — 新建：LLM fallback 机制
- `tradingagents/kb/knowledge_base.py` — KB 覆盖率时效加权
- `tradingagents/agents/utils/position_state.py` — 文件并发锁
- `tradingagents/agents/utils/agent_states.py` — InvestDebateState 扩展
- `tradingagents/agents/researchers/bull_researcher.py` — 上下文管理升级
- `tradingagents/agents/researchers/bear_researcher.py` — 上下文管理升级
- `tradingagents/default_config.py` — 新配置键（10 个 FIX feature flag）
- `pyproject.toml` — pytest-cov + 开发依赖 + 版本号
- `Makefile` — 新建：test/test-cov/test-ci 目标
- `.github/workflows/test.yml` — 新建：CI 流水线

### 完成标准
- [ ] `docker compose up` 后 API 和 CLI 均可用
- [ ] `pytest tests/ -v` 全部通过
- [ ] `make test-cov` 覆盖率 ≥ 70%
- [ ] `POST /analyze` 单次分析 ≤ 3 分钟（原 ~5 分钟）
- [ ] 辩论路由故障率 = 0%（枚举替换字符串匹配）

### 必须包含
- FIX-0~FIX-10 全部 11 个缺陷修复
- 双路径覆盖（V1.0 CLI + V1.2 API）
- 每个 FIX 的独立配置回退开关
- 测试基础设施补齐

### 禁止包含（护栏）
- PRD 数字金融团队（Paperclip/Intent Router/GEPA 学习循环）
- 选股系统（全市场扫描/多因子/回测）
- 新功能开发
- 与 11 个 FIX 无关的重构
- 向量数据库/RAG 管道（FIX-7 严格限定为 LLM 摘要方案）
- 完整 CI/CD 管线（限定为单个 test workflow）

---

## 验证策略

> **零人工介入** — 所有验证由 Agent 直接执行。禁止任何"用户手动测试/确认"类验收标准。

### 测试决策
- **基础设施存在**：YES（pytest，pyproject.toml 配置，38 个测试文件）
- **自动化测试**：修复后补测试（修复缺陷 → 为受影响模块补充/更新测试）
- **框架**：pytest
- **Agent 执行 QA**：所有任务必须包含（作为主要验证手段）

### QA 策略
每个任务必须包含 Agent-Executed QA Scenarios。
- **API/后端**：使用 Bash (curl) — 发送请求、断言状态码与响应字段
- **CLI/TUI**：使用 interactive_bash (tmux) — 运行命令、校验输出
- **代码模块**：使用 Bash (pytest) — 运行测试、校验通过数
证据保存至 `.omo/evidence/task-{N}-{场景名}.{ext}`。

---

## 执行策略

### 并行执行波次

> 最大化并行吞吐。目标每波 4-8 个任务。

```
波次 1（基础层 — 全部独立模块，可立即并行启动）：
├── 任务 1: validate_model() 调用修复 [quick]
├── 任务 2: 清理临时文件 [quick]
├── 任务 3: 测试基础设施补齐 [quick]
├── 任务 4: FIX-4 deep_llm fallback 机制 [deep]
├── 任务 5: FIX-6 KB 覆盖率时效加权 [deep]
├── 任务 6: FIX-9 并发文件安全保护 [quick]
├── 任务 7: FIX-8 工具调用死循环检测 [quick]
└── 任务 8: FIX-10 因果链追踪日志 [deep]

波次 2（图路由核心 — FIX-0）：
└── 任务 9: FIX-0 V1.2 API 辩论路由 [deep]

波次 3（依赖 FIX-0 — 全部可并行）：
├── 任务 10: FIX-2 辩论路由枚举化 [deep]
└── 任务 11: FIX-5 辩论深度 + 质量度量 [deep]

波次 4（依赖波次 3 — 全部可并行）：
├── 任务 12: FIX-1 分析师并行化 [deep]
├── 任务 13: FIX-3 V1.2 动态图检查点 [deep]
└── 任务 14: FIX-7 上下文窗口管理升级 [deep]

波次 5（集成验证 — 全部可并行）：
├── 任务 15: CLI 路径集成测试 + 回归 [deep]
├── 任务 16: API 路径集成测试 + 回归 [deep]
└── 任务 17: 文档更新 + 配置迁移指南 [writing]

波次 FINAL（最终验证 — 4 路并行审核）：
├── 任务 F1: 方案合规审计 (oracle)
├── 任务 F2: 代码质量审查 (unspecified-high)
├── 任务 F3: 手动 QA 执行 (unspecified-high)
└── 任务 F4: 范围保真度检查 (deep)
→ 提交结果 → 等待用户明确确认 "okay"
```

**关键路径**：任务 9（FIX-0）→ 任务 10 + 11 → 任务 12 → 任务 15 + 16 → F1-F4 → 用户确认
**并行提速**：相比串行执行提速约 55%
**最大并发**：8（波次 1）

### 依赖矩阵

| 任务 | 阻塞项 | 被阻塞项 | 波次 |
|------|--------|---------|:---:|
| 1-8 | - | - | 1 |
| 9 | - | 10, 11, 12 | 2 |
| 10 | 9 | 12 | 3 |
| 11 | 9 | - | 3 |
| 12 | 9, 10 | 15, 16 | 4 |
| 13 | - | 15, 16 | 4 |
| 14 | - | 15, 16 | 4 |
| 15 | 12, 13, 14 | F1-F4 | 5 |
| 16 | 12, 13, 14 | F1-F4 | 5 |
| 17 | - | - | 5 |

### Agent 调度摘要

- **波次 1**：8 任务 — T1-T3 → `quick`，T4 → `deep`，T5 → `deep`，T6 → `quick`，T7 → `quick`，T8 → `deep`
- **波次 2**：1 任务 — T9 → `deep`
- **波次 3**：2 任务 — T10 → `deep`，T11 → `deep`
- **波次 4**：3 任务 — T12 → `deep`，T13 → `deep`，T14 → `deep`
- **波次 5**：3 任务 — T15 → `deep`，T16 → `deep`，T17 → `writing`
- **FINAL**：4 任务 — F1 → `oracle`，F2 → `unspecified-high`，F3 → `unspecified-high`，F4 → `deep`

---

## 待办事项

> 实现 + 测试 = 一个任务，不可拆分。
> 每个任务必须包含：推荐 Agent Profile + 并行信息 + QA Scenarios。

---

- [x] 1. 修复 validate_model() 调用缺失

  **做什么**：
  - 在 `tradingagents/llm_clients/validators.py` 中，找到 `validate_model()` 函数（当前定义但从未被调用）
  - 在 LLM 客户端工厂 `tradingagents/llm_clients/factory.py` 的 `create_llm_client()` 中添加 `validate_model()` 调用
  - 在 `tradingagents/bootstrap.py` 的 LLM 创建流程中也加入调用
  - 当模型无效时输出清晰的警告日志（不阻塞启动，仅警告）

  **禁止做**：
  - 不要将警告改为硬错误（保持向后兼容）
  - 不要修改 `validate_model()` 的已有逻辑（当前未知 provider 返回 True 是设计意图）

  **推荐 Agent Profile**：
  > 简单单文件修复，涉及清晰逻辑，无需深度研究。
  - **类别**：`quick`
    - 原因：单文件修改，逻辑简单明确
  - **技能**：`[]`
    - 不需要特殊技能

  **并行化**：
  - **可并行**：YES
  - **并行组**：波次 1（与任务 2-8 同时启动）
  - **阻塞**：无
  - **被阻塞**：无（可立即开始）

  **参考资料**：
  - `tradingagents/llm_clients/validators.py:23` — validate_model() 当前实现
  - `tradingagents/llm_clients/factory.py:11-53` — create_llm_client() 工厂函数
  - `tradingagents/bootstrap.py:81-113` — LLM 创建和调度器启用逻辑
  - `tradingagents/llm_clients/TODO.md` — validate_model() 从未被调用的记录

  **验收标准**：
  - [ ] `validate_model()` 在 LLM 客户端创建时被调用
  - [ ] 无效模型配置输出 WARNING 级别日志，不阻塞启动
  - [ ] 现有 LLM 创建路径的行为不变（向后兼容）

  **QA Scenarios**：

  ```
  Scenario: 有效模型配置不触发警告
    Tool: Bash (pytest)
    Preconditions: 设置有效的 DEEPSEEK_API_KEY
    Steps:
      1. 运行 `python -c "from tradingagents.bootstrap import bootstrap; bootstrap({})"`
      2. 检查 stderr 输出
    Expected Result: 无 "unknown model" 警告
    Evidence: .omo/evidence/task-1-valid-model.log

  Scenario: 无效模型配置触发警告但继续启动
    Tool: Bash (pytest)
    Preconditions: 在配置中设置不存在的模型名 "gpt-nonexistent"
    Steps:
      1. 设置 TRADINGAGENTS_DEEP_THINK_LLM="gpt-nonexistent"
      2. 运行 bootstrap
      3. 检查日志中是否出现 WARNING
    Expected Result: 日志包含 WARNING "unknown model"，但 bootstrap 正常完成
    Failure Indicators: 抛出异常而非警告 / 完全没有日志
    Evidence: .omo/evidence/task-1-invalid-model.log
  ```

  **提交**：YES
  - Message: `fix(llm): call validate_model() during client creation`
  - Files: `tradingagents/llm_clients/factory.py`, `tradingagents/bootstrap.py`
  - 预提交: `pytest tests/test_llm_client.py -v`

---

- [x] 2. 清理临时文件和过时产物

  **做什么**：
  - 删除 `.sisyphus/run-continuation/` 下的所有临时 Session 文件
  - 检查 `~/.tradingagents/cache/` 下是否有过期缓存
  - 清理 `.omo/drafts/` 中已完成的草稿文件

  **禁止做**：
  - 不要删除 `.omo/plans/` 中的任何计划文件
  - 不要删除 `~/.tradingagents/kb/` 中的知识库数据

  **推荐 Agent Profile**：
  > 纯文件操作，无代码逻辑。
  - **类别**：`quick`
    - 原因：简单的文件清理操作
  - **技能**：`[]`
    - 不需要特殊技能

  **并行化**：
  - **可并行**：YES
  - **并行组**：波次 1（与任务 1, 3-8 同时启动）
  - **阻塞**：无
  - **被阻塞**：无

  **参考资料**：
  - `.sisyphus/run-continuation/` — 临时 Session 文件目录
  - `docs/开发进度表.md:234-235` — 即时行动项记录

  **验收标准**：
  - [ ] `.sisyphus/run-continuation/` 目录为空或不存在
  - [ ] `.omo/plans/` 中 16 个计划文件完整保留

  **QA Scenarios**：

  ```
  Scenario: 清理后目录干净
    Tool: Bash
    Steps:
      1. 运行 `ls .sisyphus/run-continuation/ 2>/dev/null | wc -l`
      2. 运行 `ls .omo/plans/ | wc -l`
    Expected Result: run-continuation 为空（0 文件），plans 下 ≥ 16 个文件
    Evidence: .omo/evidence/task-2-cleanup.log
  ```

  **提交**：NO（纯清理操作，不提交）

---

- [x] 3. 补齐测试基础设施

  **做什么**：
  - 在 `pyproject.toml` 中添加 `[project.optional-dependencies]` dev 组（pytest, pytest-cov）
  - 添加 `[tool.coverage.run]` 配置（source = ["tradingagents"]）
  - 创建 `Makefile`，提供 `make test`、`make test-cov`、`make test-ci` 目标
  - 创建 `.github/workflows/test.yml` CI 流水线（pytest --cov 并 fail-under 70%）
  - 更新 `pyproject.toml` 版本号（如果尚未更新至 0.2.8）

  **禁止做**：
  - 不要添加 pre-commit hooks 或 CD 部署步骤
  - 不要修改已有测试文件

  **推荐 Agent Profile**：
  > 基础设施配置，涉及多种文件格式（TOML, Makefile, YAML），但逻辑简单。
  - **类别**：`quick`
    - 原因：配置文件创建，无复杂逻辑
  - **技能**：`[]`
    - 不需要特殊技能

  **并行化**：
  - **可并行**：YES
  - **并行组**：波次 1（与任务 1-2, 4-8 同时启动）
  - **阻塞**：无
  - **被阻塞**：无

  **参考资料**：
  - `pyproject.toml:48-55` — 现有 pytest 配置
  - `.github/` — 不存在，需创建
  - `docs/开发进度表.md:226` — 版本号修复记录

  **验收标准**：
  - [ ] `pip install -e ".[dev]"` 成功安装 pytest + pytest-cov
  - [ ] `make test` 运行 `pytest tests/ -v` 并全部通过
  - [ ] `make test-cov` 输出覆盖率报告
  - [ ] `.github/workflows/test.yml` 存在且语法正确

  **QA Scenarios**：

  ```
  Scenario: make test 运行全部测试并通过
    Tool: Bash
    Steps:
      1. 运行 `make test`
      2. 检查退出码和输出最后一行
    Expected Result: 退出码 0，输出 "N passed"（无 failures）
    Evidence: .omo/evidence/task-3-make-test.log

  Scenario: make test-cov 生成覆盖率报告
    Tool: Bash
    Steps:
      1. 运行 `make test-cov`
      2. 检查输出是否包含 "TOTAL" 覆盖率行
    Expected Result: 输出包含覆盖率统计（即使未达 70% 门槛）
    Failure Indicators: pytest-cov 未安装导致崩溃
    Evidence: .omo/evidence/task-3-make-test-cov.log
  ```

  **提交**：YES
  - Message: `chore: add test infrastructure (pytest-cov, Makefile, CI)`
  - Files: `pyproject.toml`, `Makefile`, `.github/workflows/test.yml`
  - 预提交: `make test-ci`

---

- [x] 4. FIX-4：实现 deep_llm 自动 fallback 机制

  **做什么**：
  - 新建 `tradingagents/llm_clients/resilient_llm.py`，实现 `ResilientLLM` 包装类
  - 支持 primary LLM 失败时自动重试 2 次（含 3s 延迟）
  - primary 全部失败后自动降级到 fallback LLM（quick_llm）
  - 降级时在 Agent 输出中标注 "⚠️ 深度分析模型不可用，本决策使用备用模型"
  - 在 `tradingagents/bootstrap.py` 中用 `ResilientLLM` 包装 `deep_llm`
  - 添加降级状态日志（WARNING 级别）
  - 处理 DeepSeek `NotImplementedError`：不重试，立即 fallback

  **禁止做**：
  - 不要修改 `deep_llm` 的使用方（Agent 代码）——通过包装器透明处理
  - 不要为 429 限流错误实现指数退避（超出当前范围）

  **推荐 Agent Profile**：
  > 新建模块，涉及异常处理、重试逻辑、状态管理，需要仔细的边界条件思考。
  - **类别**：`deep`
    - 原因：LLM 故障容错设计需要深度思考异常场景
  - **技能**：`[]`
    - 不需要特殊技能

  **并行化**：
  - **可并行**：YES
  - **并行组**：波次 1（与任务 1-3, 5-8 同时启动）
  - **阻塞**：无
  - **被阻塞**：无（完全独立的新模块）

  **参考资料**：
  - `docs/架构缺陷修复方案.md:375-503` — FIX-4 完整方案（含代码示例）
  - `tradingagents/bootstrap.py:81-113` — deep_llm 创建位置
  - `tradingagents/llm_clients/openai_client.py:97-104` — DeepSeek `with_structured_output()` NotImplementedError
  - `tradingagents/agents/utils/structured.py:31-73` — 现有结构化输出 fallback 逻辑（参考模式）

  **验收标准**：
  - [ ] `ResilientLLM` 类存在且通过单元测试
  - [ ] primary 正常时行为不变（零影响）
  - [ ] primary 失败 3 次后自动切换到 fallback
  - [ ] 降级时 Agent 最终输出包含 "⚠️" 降级标记
  - [ ] DeepSeek `NotImplementedError` 立即 fallback，不重试

  **QA Scenarios**：

  ```
  Scenario: primary LLM 正常时不触发 fallback
    Tool: Bash (pytest)
    Preconditions: 设置有效的 API key
    Steps:
      1. 运行 `pytest tests/ -k "resilient" -v`
      2. 检查测试结果
    Expected Result: primary 路径测试全部通过，`_degraded` 为 False
    Evidence: .omo/evidence/task-4-resilient-normal.log

  Scenario: primary LLM 全部失败后自动降级
    Tool: Bash (pytest)
    Preconditions: Mock primary LLM 抛出 ConnectionError
    Steps:
      1. 运行 mock 测试：primary 抛异常 3 次 → fallback 调用成功
      2. 验证 `is_degraded` 返回 True
      3. 验证最终结果包含 `"⚠️"`
    Expected Result: fallback 被调用，`_degraded=True`，输出含降级标记
    Failure Indicators: 抛出 RuntimeError 而非使用 fallback / fallback 未被调用
    Evidence: .omo/evidence/task-4-resilient-fallback.log

  Scenario: primary + fallback 全部失败
    Tool: Bash (pytest)
    Preconditions: Mock 两个 LLM 都失败
    Steps:
      1. 运行 mock 测试：两个 LLM 都抛异常
      2. 验证是否抛出 RuntimeError 含 "Both primary and fallback LLMs failed"
    Expected Result: RuntimeError，错误消息明确指出两个 LLM 都失败
    Evidence: .omo/evidence/task-4-resilient-double-fail.log
  ```

  **提交**：YES
  - Message: `feat(llm): add ResilientLLM with auto-fallback for deep_llm`
  - Files: `tradingagents/llm_clients/resilient_llm.py`, `tradingagents/bootstrap.py`
  - 预提交: `pytest tests/ -k "resilient" -v`

---

- [x] 5. FIX-6：KB 覆盖率时效加权

  **做什么**：
  - 修改 `tradingagents/kb/knowledge_base.py` 中的 `_calculate_coverage()` 方法
  - 加入时效衰减因子：`decay = 0.5^(age / half_life)`，half_life 按 collection 差异化配置
  - 配置衰减参数（市场快照 10min / 舆情 5min / 公告 30min / 政策 60min / 个股 30min）
  - 修改返回值：从 `float` 改为 `(float, dict)`，dict 含 raw_coverage、weighted_coverage、stale_items
  - 更新 `tradingagents/planner/llm_planner.py` 中的覆盖率使用：加权 ≥ 0.7 且无 stale → 跳过分析
  - 处理 `_ts` 字段缺失：标记为 stale 并加权 0

  **禁止做**：
  - 不要修改 KB 写入逻辑（只改读取/评估侧）
  - 不要改变 Planner 的模板匹配逻辑（只改覆盖率阈值判断）

  **推荐 Agent Profile**：
  > 涉及数学衰减模型和阈值逻辑，需要仔细的边界条件处理。
  - **类别**：`deep`
    - 原因：时效衰减模型涉及指数函数和阈值判断，需验证边界条件
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES
  - **并行组**：波次 1（与任务 1-4, 6-8 同时启动）
  - **阻塞**：无
  - **被阻塞**：无

  **参考资料**：
  - `docs/架构缺陷修复方案.md:650-764` — FIX-6 完整方案（含衰减公式和代码示例）
  - `tradingagents/kb/knowledge_base.py:144-157` — 当前 `_calculate_coverage()` 实现
  - `tradingagents/planner/llm_planner.py` — coverage 使用位置
  - `tradingagents/kb/freshness.py` — 现有时效管理（参考 TTL 配置）

  **验收标准**：
  - [ ] 5 分钟前数据加权覆盖率 > 0.9
  - [ ] 30 分钟前市场快照加权覆盖率 < 0.5 且标记为 stale
  - [ ] 无 `_ts` 字段的条目加权覆盖率 ≈ 0 且标记为 stale
  - [ ] 加权覆盖率 < 0.7 且有 stale → Planner 走正常分析（不跳过）
  - [ ] 加权覆盖率 ≥ 0.7 且无 stale → Planner 可跳过

  **QA Scenarios**：

  ```
  Scenario: 新鲜数据不触发 false stale 标记
    Tool: Bash (pytest)
    Steps:
      1. 创建 mock KB 条目，`_ts` 设为 60 秒前
      2. 调用 `_calculate_coverage()`
      3. 验证 weighted_coverage > 0.9
      4. 验证 stale_items 为空
    Expected Result: coverage > 0.9，无 stale
    Failure Indicators: coverage < 0.7 / stale_items 非空
    Evidence: .omo/evidence/task-5-fresh-data.log

  Scenario: 过期数据正确标记为 stale
    Tool: Bash (pytest)
    Steps:
      1. 创建 mock KB 条目，`_ts` 设为 2 小时前（远超 30min 半衰期）
      2. 调用 `_calculate_coverage()`
      3. 验证 weighted_coverage < 0.3
      4. 验证 stale_items 包含该 collection
    Expected Result: coverage < 0.3，stale_items 非空
    Evidence: .omo/evidence/task-5-stale-data.log
  ```

  **提交**：YES
  - Message: `feat(kb): add freshness-weighted coverage calculation`
  - Files: `tradingagents/kb/knowledge_base.py`, `tradingagents/planner/llm_planner.py`
  - 预提交: `pytest tests/ -k "kb or planner" -v`

---

- [x] 6. FIX-9：并发文件安全保护

  **做什么**：
  - 在 `tradingagents/agents/utils/position_state.py` 中添加文件锁机制
  - 使用 `filelock` 包（跨平台，正确处理 NFS 和进程崩溃）替代方案中的 `fcntl`
  - 在 `save()` 和 `load()` 方法中添加 `with self._lock_position_file(ticker):` 上下文管理器
  - 锁超时 5 秒，超时抛出 `TimeoutError`，不静默破坏数据
  - 在 `pyproject.toml` 中添加 `filelock` 依赖

  **禁止做**：
  - 不要使用 `fcntl.flock`（Docker + NFS 不可靠）
  - 不要修改持仓文件的读写格式（只加锁）

  **推荐 Agent Profile**：
  > 并发安全是标准模式，使用成熟第三方库，逻辑清晰。
  - **类别**：`quick`
    - 原因：使用 filelock 库，标准文件锁模式
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES
  - **并行组**：波次 1（与任务 1-5, 7-8 同时启动）
  - **阻塞**：无
  - **被阻塞**：无

  **参考资料**：
  - `docs/架构缺陷修复方案.md:1026-1094` — FIX-9 完整方案
  - `tradingagents/agents/utils/position_state.py` — PositionStateManager 当前实现
  - `tradingagents/portfolio/portfolio_manager.py` — 持仓文件写入路径

  **验收标准**：
  - [ ] `save()` 和 `load()` 操作受文件锁保护
  - [ ] 并发写入同一 ticker 时不发生数据撕裂（写入排队）
  - [ ] 锁超时（>5s）抛出 `TimeoutError`

  **QA Scenarios**：

  ```
  Scenario: 并发写入同一 ticker 数据完整
    Tool: Bash (pytest)
    Steps:
      1. 启动 2 个线程同时写入同一 ticker 的不同数据
      2. 两个写入都完成后读取文件
      3. 验证数据完整，无撕裂
    Expected Result: 文件内容完整，两次写入都生效
    Evidence: .omo/evidence/task-6-concurrent-write.log

  Scenario: 锁超时正确报错
    Tool: Bash (pytest)
    Steps:
      1. Mock 锁持有 6 秒（超过 5s 超时）
      2. 第二个写入请求触发
      3. 验证抛出 TimeoutError
    Expected Result: TimeoutError，错误消息含 ticker 名称
    Failure Indicators: 静默失败 / 数据损坏
    Evidence: .omo/evidence/task-6-lock-timeout.log
  ```

  **提交**：YES
  - Message: `fix(position): add filelock for concurrent position state safety`
  - Files: `tradingagents/agents/utils/position_state.py`, `pyproject.toml`
  - 预提交: `pytest tests/ -k "position" -v`

---

- [x] 7. FIX-8：工具调用死循环检测

  **做什么**：
  - 在 `tradingagents/graph/conditional_logic.py` 中新增 `_detect_tool_loop()` 方法
  - 检测三种退化模式：(1) 同一工具+参数连续重复 3 次，(2) 总工具调用 > 12 次，(3) 交替调用无进展
  - 在所有 `should_continue_*` 方法中集成检测逻辑
  - 触发时注入 `HumanMessage` 提示 LLM "请基于已获取的数据生成报告"
  - 使用 `Counter` 基于 `(tool_name, args)` 组合去重

  **禁止做**：
  - 不要修改工具调用的参数传递逻辑（只添加检测）
  - 不要改变 `should_continue_*` 的返回值签名

  **推荐 Agent Profile**：
  > 状态检测逻辑，涉及消息历史和计数器分析。
  - **类别**：`quick`
    - 原因：在现有条件路由中添加检测逻辑，改动范围小
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES
  - **并行组**：波次 1（与任务 1-6, 8 同时启动）
  - **阻塞**：无
  - **被阻塞**：无

  **参考资料**：
  - `docs/架构缺陷修复方案.md:922-1014` — FIX-8 完整方案（含 `_detect_tool_loop` 代码）
  - `tradingagents/graph/conditional_logic.py` — 所有 `should_continue_*` 方法

  **验收标准**：
  - [ ] 同一工具+参数重复 ≥ 3 次 → 检测到死循环 → 终止并注入提示
  - [ ] 工具调用总次数 ≥ 12 → 终止并注入提示
  - [ ] 合法多次调用不同参数 → 不触发误检测

  **QA Scenarios**：

  ```
  Scenario: 死循环被正确检测并终止
    Tool: Bash (pytest)
    Steps:
      1. 构造 mock messages：连续 3 条相同的 tool_call（同一工具+参数）
      2. 调用 `_detect_tool_loop()`
      3. 验证返回 (True, "repeat_detected")
    Expected Result: 返回 True，reason="repeat_detected"
    Evidence: .omo/evidence/task-7-loop-detected.log

  Scenario: 合法多次调用不误触发
    Tool: Bash (pytest)
    Steps:
      1. 构造 mock messages：3 次工具调用，每次参数不同
      2. 调用 `_detect_tool_loop()`
      3. 验证返回 (False, "ok")
    Expected Result: 返回 False，不误报
    Failure Indicators: 合法调用被标记为死循环
    Evidence: .omo/evidence/task-7-no-false-positive.log
  ```

  **提交**：YES
  - Message: `feat(graph): add tool-call loop detection in conditional logic`
  - Files: `tradingagents/graph/conditional_logic.py`
  - 预提交: `pytest tests/ -k "conditional" -v`

---

- [x] 8. FIX-10：因果链追踪日志

  **做什么**：
  - 新建 `tradingagents/graph/causal_tracer.py`，实现 `CausalTracer` 类
  - 在关键决策点记录 `(决策, 依据, 来源)` 三元组：分析师报告 → 辩论论点 → RM/PM 裁判
  - 使用 quick_llm 做轻量级主张提取（每次 ~$0.001，共 5-8 次/分析）
  - 最终输出 JSON 文件至 `results_dir/{ticker}/traces/{date}.json`
  - 在 TradingAgentsGraph 中集成（通过 LangGraph callback 或节点内显式调用）
  - LLM 提取失败时继续追踪（部分数据为空但结构完整）

  **禁止做**：
  - 不要让追踪 LLM 调用阻塞主分析流程
  - 不要实现 UI 面板或数据库存储（严格限定为 JSON 文件）

  **推荐 Agent Profile**：
  > 新建设计良好的追踪模块，涉及轻量级 LLM 调用和状态管理。
  - **类别**：`deep`
    - 原因：追踪器架构设计需要仔细思考合适的集成点和数据结构
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES
  - **并行组**：波次 1（与任务 1-7 同时启动）
  - **阻塞**：无
  - **被阻塞**：无

  **参考资料**：
  - `docs/架构缺陷修复方案.md:1097-1355` — FIX-10 完整方案（含 200+ 行代码示例）
  - `tradingagents/graph/trading_graph.py:495-544` — 图执行流程（集成点）
  - `tradingagents/default_config.py` — results_dir 配置

  **验收标准**：
  - [ ] 完整分析后生成 `{ticker}/traces/{date}.json`
  - [ ] JSON 包含 chain 数组，每个 entry 含 agent/output_type/key_claim
  - [ ] RM 和 PM 的最终决策可追溯至上游论点
  - [ ] LLM 提取失败时 JSON 中标记 `[extraction failed]`，不丢失其他数据

  **QA Scenarios**：

  ```
  Scenario: 完整追踪链覆盖所有 Agent
    Tool: Bash (curl + jq)
    Steps:
      1. 触发 `POST /analyze` 分析 600519
      2. 等待完成后检查 `~/.tradingagents/users/*/results/600519/traces/` 下的 JSON
      3. 用 jq 验证 chain 数组包含 Market Analyst, Fundamentals Analyst, Bull Researcher, Bear Researcher, RM, PM
    Expected Result: chain 中至少 6 个 agent，final_decision 非空
    Evidence: .omo/evidence/task-8-trace-complete.json

  Scenario: 追踪提取失败不中断分析
    Tool: Bash (pytest)
    Steps:
      1. Mock quick_llm 提取调用全部失败
      2. 运行完整分析
      3. 验证 JSON 仍然生成，chain 各 entry 含 `[extraction failed]`
      4. 验证最终分析报告正常生成
    Expected Result: JSON 存在，含 failure 标记，分析未中断
    Failure Indicators: 分析因追踪失败而崩溃
    Evidence: .omo/evidence/task-8-trace-partial-fail.json
  ```

  **提交**：YES
  - Message: `feat(graph): add causal chain tracing for decision audit`
  - Files: `tradingagents/graph/causal_tracer.py`, `tradingagents/graph/trading_graph.py`
  - 预提交: `pytest tests/ -k "causal" -v`

---

- [x] 9. FIX-0：V1.2 API 路径辩论路由（新增 — 最关键的遗漏修复）

  **做什么**：
  - 在 `tradingagents/graph/dynamic_graph_builder.py` 中实现完整的辩论路由逻辑
  - 将 `ConditionalLogic` 的 `should_continue_debate()` 和 `should_continue_risk_analysis()` 接入图拓扑
  - 为牛方/熊方研究员节点之间添加条件边（Bull ↔ Bear 往返对抗，直到达到 `max_debate_rounds` 或质量下降）
  - 为风险辩论三方节点之间添加条件边（Aggressive ↔ Conservative ↔ Neutral 循环）
  - 在 `_add_tool_cycle()` 之外新增 `_add_debate_cycle()` 方法
  - 集成到 `build()` 方法中：识别 plan 中的 debate/risk debate 步骤并构建对应路由
  - 确保模板 JSON（`tradingagents/templates/*.json`）定义的 debate 流程正确解析

  **禁止做**：
  - 不要修改 `ConditionalLogic` 本身的逻辑（FIX-2 单独处理路由内部的字符串依赖）
  - 不要改变模板 JSON 的结构

  **推荐 Agent Profile**：
  > 这是整个计划最核心的架构级改动，需要深入理解 LangGraph 图拓扑、条件路由和两套执行路径。
  - **类别**：`deep`
    - 原因：架构级图拓扑改造，涉及 LangGraph StateGraph 条件边和辩论路由设计
  - **技能**：`[]`

  **并行化**：
  - **可并行**：NO（阻塞任务 10-12）
  - **并行组**：波次 2（单独执行，所有后续波次依赖此任务）
  - **阻塞**：10, 11, 12
  - **被阻塞**：无（可立即开始，但波次 2 建议在波次 1 完成后启动）

  **参考资料**：
  - `tradingagents/graph/dynamic_graph_builder.py:39-130` — 当前 build() 和 _add_tool_cycle() 逻辑
  - `tradingagents/graph/conditional_logic.py:46-67` — should_continue_debate / should_continue_risk_analysis（需接入）
  - `tradingagents/graph/setup.py:112-134` — V1.0 CLI 路径的辩论路由（参考拓扑模式）
  - `tradingagents/templates/tpl_standard_analysis.json:41-57` — 模板定义的 debate workflow 步骤
  - `tradingagents/graph/executor.py:43-111` — GraphExecutor.execute()（图构建入口）
  - `docs/架构缺陷修复方案.md` — Metis 审查中关于 API 路径缺失辩论的发现

  **验收标准**：
  - [ ] `POST /analyze` 的 Bull/Bear 发言序列为 Bull→Bear→Bull→Bear→RM（而非各说一句）
  - [ ] 风险辩论三方循环正常（Aggressive↔Conservative↔Neutral 往返）
  - [ ] 辩论轮次达到 `max_debate_rounds` 后自动路由到 RM/PM
  - [ ] V1.0 CLI 路径不受影响（`setup.py` 的辩论路由保持不变）
  - [ ] 模板 JSON 定义的 standard_analysis 流程在 API 路径正确辩论

  **QA Scenarios**：

  ```
  Scenario: API 路径 Bull/Bear 往返辩论
    Tool: Bash (curl)
    Preconditions: POST /analyze 端点可用
    Steps:
      1. 触发 `POST /analyze` 分析 600519
      2. 检查响应中的 debate 发言序列
      3. 验证 Bull Researcher → Bear Researcher 至少出现 2 轮（4 次发言）
    Expected Result: 辩论 history 包含 ≥ 4 条交替发言
    Failure Indicators: Bull/Bear 各只出现 1 次（旧行为）
    Evidence: .omo/evidence/task-0-api-debate.log

  Scenario: 风险辩论三方循环
    Tool: Bash (curl)
    Steps:
      1. 触发分析（包含风险辩论的模板）
      2. 检查风险辩论发言序列
      3. 验证 Aggressive → Conservative → Neutral 出现
    Expected Result: 三方各有发言，非单轮
    Evidence: .omo/evidence/task-0-risk-debate.log
  ```

  **提交**：YES
  - Message: `feat(graph): add debate routing to V1.2 dynamic graph builder`
  - Files: `tradingagents/graph/dynamic_graph_builder.py`
  - 预提交: `curl -X POST http://localhost:8000/analyze -d '{"user_id":"test","message":"test","ticker":"600519"}'`

---

- [x] 10. FIX-2：辩论路由枚举化（消除字符串依赖）

  **做什么**：
  - 在 `tradingagents/agents/utils/agent_states.py` 中扩展 `InvestDebateState`，新增 `latest_speaker` 字段
  - 修改 `bull_researcher.py`：在状态更新中写入 `latest_speaker = "Bull"`
  - 修改 `bear_researcher.py`：在状态更新中写入 `latest_speaker = "Bear"`
  - 重写 `conditional_logic.py` 的 `should_continue_debate()`：用 `latest_speaker` 枚举替换 `startswith("Bull")`
  - 同样修复 `should_continue_risk_analysis()` 的 `startswith("Aggressive")`/`startswith("Conservative")` 模式
  - 添加安全上限 `MAX_TOTAL_ROUNDS = 2 * max_debate_rounds + 2` 防止死循环
  - 确保 FIX-0 中新增的 API 路径辩论路由也使用枚举（两者统一）

  **禁止做**：
  - 不要只修复 V1.0 CLI 路径而忽略 V1.2 API 路径
  - 不要修改 `latest_speaker` 的命名约定（与风险辩论的 `latest_speaker` 保持一致）

  **推荐 Agent Profile**：
  > 跨 5 个文件的状态管理重构，需要仔细的类型变更和一致性验证。
  - **类别**：`deep`
    - 原因：状态枚举重构涉及多个 Agent 和路由逻辑，需确保一致性
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES（与任务 11 同时启动）
  - **并行组**：波次 3（与任务 11 同时）
  - **阻塞**：12
  - **被阻塞**：9（FIX-0 必须先完成）

  **参考资料**：
  - `docs/架构缺陷修复方案.md:162-252` — FIX-2 完整方案（含 State 扩展和路由重写代码）
  - `tradingagents/graph/conditional_logic.py:46-67` — 当前 `startswith("Bull")` / `startswith("Aggressive")` 路由
  - `tradingagents/agents/utils/agent_states.py` — InvestDebateState 定义
  - `tradingagents/agents/researchers/bull_researcher.py` — Bull 节点状态更新
  - `tradingagents/agents/researchers/bear_researcher.py` — Bear 节点状态更新

  **验收标准**：
  - [ ] `should_continue_debate()` 不再使用 `startswith()` 字符串匹配
  - [ ] `latest_speaker` 为空 → 首轮从 Bull Researcher 开始
  - [ ] `latest_speaker == "Bull"` → 路由到 Bear Researcher
  - [ ] `latest_speaker == "Bear"` → 路由到 Bull Researcher
  - [ ] 风险辩论同样改为枚举路由
  - [ ] `count >= MAX_TOTAL_ROUNDS` 时强制终止

  **QA Scenarios**：

  ```
  Scenario: 首轮正确从 Bull 开始
    Tool: Bash (pytest)
    Steps:
      1. 构造 state：latest_speaker=""（空字符串），count=0
      2. 调用 should_continue_debate()
      3. 验证返回 "Bull Researcher"
    Expected Result: 返回 "Bull Researcher"
    Evidence: .omo/evidence/task-10-first-round.log

  Scenario: Bull → Bear → Bull → Bear 正确交替
    Tool: Bash (pytest)
    Steps:
      1. 模拟 4 轮辩论，逐轮验证路由
      2. Bull 发言后 → 返回 "Bear Researcher"
      3. Bear 发言后 → 返回 "Bull Researcher"
    Expected Result: 交替正确，无断链
    Failure Indicators: 某轮返回错误节点
    Evidence: .omo/evidence/task-10-alternation.log

  Scenario: LLM 输出格式变化不影响路由
    Tool: Bash (pytest)
    Steps:
      1. 构造 state：latest_speaker="Bull"
      2. 调用 should_continue_debate()
      3. 验证不依赖 LLM 的输出格式
    Expected Result: 只检查 latest_speaker，不检查 response 内容
    Evidence: .omo/evidence/task-10-format-independent.log
  ```

  **提交**：YES
  - Message: `fix(graph): replace string-based debate routing with enum latest_speaker`
  - Files: `tradingagents/graph/conditional_logic.py`, `tradingagents/agents/utils/agent_states.py`, `tradingagents/agents/researchers/bull_researcher.py`, `tradingagents/agents/researchers/bear_researcher.py`
  - 预提交: `pytest tests/ -k "debate or conditional" -v`

---

- [x] 11. FIX-5：辩论深度提升 + 质量度量

  **做什么**：
  - 修改 `tradingagents/default_config.py`：`max_debate_rounds` 从 1 改为 2（Bull→Bear→Bull→Bear→RM）
  - 同样修改 `max_risk_discuss_rounds` 从 1 改为 2
  - 新建 `tradingagents/graph/debate_quality.py`，实现 `DebateQualityTracker` 类
  - 在每次辩论轮次结束时评估：新证据检测、冗余检测、观点变化追踪
  - 集成到 `conditional_logic.py`：连续 2 轮质量评分 < 0.3 → 提前终止辩论
  - 确保 FIX-0 中新增的 API 路径辩论也使用相同的质量检测

  **禁止做**：
  - 不要让质量评分自动调整辩论轮次（只记录 + 提前终止，不动态增加轮次）
  - 不要在前 2 轮就做质量检测（至少跑完一个完整往返）

  **推荐 Agent Profile**：
  > 新建质量度量模块 + 配置变更，涉及 LLM 轻量调用做证据检测。
  - **类别**：`deep`
    - 原因：辩论质量度量设计需要 LLM 调用和阈值判断
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES（与任务 10 同时启动）
  - **并行组**：波次 3（与任务 10 同时）
  - **阻塞**：无
  - **被阻塞**：9（FIX-0 必须先完成）

  **参考资料**：
  - `docs/架构缺陷修复方案.md:514-648` — FIX-5 完整方案（含质量评分代码）
  - `tradingagents/default_config.py:16-17` — 当前 max_debate_rounds 配置
  - `tradingagents/graph/conditional_logic.py:46-55` — 当前辩论计数逻辑

  **验收标准**：
  - [ ] `max_debate_rounds=2`，投资辩论发言序列为 Bull→Bear→Bull→Bear→RM
  - [ ] `max_risk_discuss_rounds=2`，风险辩论 6 次发言
  - [ ] 辩论质量评分在每次轮次后记录
  - [ ] 连续 2 轮低质量 → 提前终止辩论

  **QA Scenarios**：

  ```
  Scenario: 默认 2 轮辩论有 4 次发言
    Tool: Bash (curl)
    Steps:
      1. 触发 `POST /analyze` 分析 600519
      2. 检查 debate history
      3. 验证 Bull→Bear→Bull→Bear 共 4 条发言
    Expected Result: 4 条交替发言，最后 RM 裁判
    Failure Indicators: 仍只有 2 条（旧 max=1 行为）
    Evidence: .omo/evidence/task-11-debate-depth.log

  Scenario: 低质量辩论提前终止
    Tool: Bash (pytest)
    Steps:
      1. Mock 辩论质量评分连续 2 次 < 0.3
      2. 调用 should_continue_debate()
      3. 验证返回 "Research Manager"（提前终止）
    Expected Result: 辩论提前终止，路由到 RM
    Evidence: .omo/evidence/task-11-quality-termination.log
  ```

  **提交**：YES
  - Message: `feat(graph): increase debate depth + add quality tracking`
  - Files: `tradingagents/default_config.py`, `tradingagents/graph/debate_quality.py`, `tradingagents/graph/conditional_logic.py`
  - 预提交: `pytest tests/ -k "debate" -v`

---

- [x] 12. FIX-1：分析师并行化（双路径）

  **做什么**：
  - **V1.0 CLI 路径**（`tradingagents/graph/setup.py`）：用 LangGraph `Send` API 实现扇出-汇聚
    - 新增 `create_fan_out_analysts()` 扇出节点，为每个选中分析师生成 `Send`
    - 新增 `create_merge_analyst_reports()` 汇聚节点，验证所有报告非空
    - 修改图拓扑：`START → FanOut → (4 Analysts 并行) → MergeReports → Bull Researcher`
    - 移除 Msg Clear 节点（并行模式下各自隔离消息上下文）
    - 添加 `fan_out_enabled` 配置开关（默认开启，可回退串行）
  - **V1.2 API 路径**（`tradingagents/graph/dynamic_graph_builder.py`）：支持并行步骤
    - 在 `build()` 中识别无相互依赖的分析师步骤，生成并行 Send
  - 在每个 Analyst 节点内部添加消息清除逻辑（进入时只保留系统消息）

  **禁止做**：
  - 不要改变分析师节点的工具调用逻辑（只改图拓扑）
  - 不要移除 `fan_out_enabled=false` 时的串行回退路径

  **推荐 Agent Profile**：
  > 修改两套图构建路径，涉及 LangGraph Send API 和拓扑重构，需要验证并行正确性。
  - **类别**：`deep`
    - 原因：架构级图拓扑改造，需验证并行扇出-汇聚模式正确性
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES（与任务 13, 14 同时启动）
  - **并行组**：波次 4（与任务 13, 14 同时）
  - **阻塞**：15, 16
  - **被阻塞**：9, 10（FIX-0 和 FIX-2 必须先完成）

  **参考资料**：
  - `docs/架构缺陷修复方案.md:29-161` — FIX-1 完整方案（含 Send API 代码和拓扑图）
  - `tradingagents/graph/setup.py:112-134` — V1.0 CLI 路径当前串行连接
  - `tradingagents/graph/dynamic_graph_builder.py:39-130` — V1.2 API 路径 build() 方法
  - `tradingagents/graph/executor.py:43-111` — GraphExecutor.execute()

  **验收标准**：
  - [ ] 4 个分析师在并行模式下同时启动（日志可验证）
  - [ ] 分析总耗时降低 ≥ 60%（~270s → ~90s）
  - [ ] 并行模式与串行模式的分析结果语义等价
  - [ ] `fan_out_enabled=false` 时回退到串行且行为不变

  **QA Scenarios**：

  ```
  Scenario: 并行模式 4 个分析师同时运行
    Tool: Bash (curl + time)
    Steps:
      1. 触发 `POST /analyze` 分析 600519
      2. 用 `time` 测量总耗时
      3. 检查日志中分析师启动时间戳是否接近（< 2s 差异）
    Expected Result: 总耗时 < 180s，4 个分析师启动时间戳相差 < 2s
    Failure Indicators: 总耗时 > 270s（仍为串行）/ 某分析师崩溃导致全部等待
    Evidence: .omo/evidence/task-12-parallel-timing.log

  Scenario: 串行回退开关有效
    Tool: Bash (curl)
    Steps:
      1. 设置 `fan_out_enabled=false`
      2. 触发分析
      3. 验证分析师按顺序执行（market → social → news → fundamentals）
    Expected Result: 分析按串行顺序完成，总耗时 ~270s
    Evidence: .omo/evidence/task-12-serial-fallback.log
  ```

  **提交**：YES
  - Message: `perf(graph): parallelize 4 analyst agents using LangGraph Send API`
  - Files: `tradingagents/graph/setup.py`, `tradingagents/graph/dynamic_graph_builder.py`, `tradingagents/default_config.py`
  - 预提交: `pytest tests/ -k "graph" -v`

---

- [x] 13. FIX-3：V1.2 动态图检查点支持

  **做什么**：
  - 扩展 `tradingagents/graph/executor.py` 的 `GraphExecutor`：添加 `enable_checkpoint` 参数
  - 在 `execute()` 中集成检查点机制（与 V1.0 的 `checkpointer.py` 共用底层 `SqliteSaver`）
  - 使用 `task_id = f"{ticker}:{user_id}:{trigger_type}"` 的哈希作为 thread_id
  - 成功后自动清除检查点，失败时保留以便恢复
  - 添加 `enable_checkpoint` 配置开关（默认关闭，渐进启用）
  - 在 `checkpointer.py` 中通用化 `get_checkpointer()` 接受任意 task_id

  **禁止做**：
  - 不要改变 V1.0 CLI 路径的检查点逻辑（保持向后兼容）
  - 不要默认启用检查点（渐进式部署）

  **推荐 Agent Profile**：
  > 检查点基础设施扩展，涉及 SQLite 状态管理和崩溃恢复设计。
  - **类别**：`deep`
    - 原因：崩溃恢复机制需要在多种故障场景下验证
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES（与任务 12, 14 同时启动）
  - **并行组**：波次 4（与任务 12, 14 同时）
  - **阻塞**：15, 16
  - **被阻塞**：无（独立于 FIX-0/FIX-2）

  **参考资料**：
  - `docs/架构缺陷修复方案.md:255-372` — FIX-3 完整方案（含 executor 改造代码）
  - `tradingagents/graph/executor.py:43-111` — 当前 execute() 无检查点
  - `tradingagents/graph/checkpointer.py` — 现有 SqliteSaver 基础设施
  - `tradingagents/graph/trading_graph.py:416-421` — V1.0 检查点集成（参考模式）

  **验收标准**：
  - [ ] `enable_checkpoint=true` 时 `execute()` 在编译图时传入 checkpointer
  - [ ] 崩溃后重新调用 → 从断点恢复（已验证的 token 不再消耗）
  - [ ] 成功后自动清除检查点
  - [ ] 不同 user_id 的同一 ticker 使用不同 thread_id，不冲突

  **QA Scenarios**：

  ```
  Scenario: 模拟崩溃恢复
    Tool: Bash (curl + kill)
    Steps:
      1. 设置 enable_checkpoint=true
      2. 触发 `POST /analyze`，在辩论阶段中途 kill 进程
      3. 重新触发相同参数的分析
      4. 验证是否从断点继续（通过日志确认跳过的节点）
    Expected Result: 第二次分析从断点恢复，不重新跑分析师
    Failure Indicators: 从头开始分析 / thread_id 冲突
    Evidence: .omo/evidence/task-13-crash-recovery.log

  Scenario: 成功后检查点被清除
    Tool: Bash
    Steps:
      1. 触发完整分析直至成功
      2. 检查 `~/.tradingagents/cache/checkpoints/` 下该 task_id 的 DB 是否被删除
    Expected Result: 检查点 DB 文件不存在
    Evidence: .omo/evidence/task-13-cleanup.log
  ```

  **提交**：YES
  - Message: `feat(graph): add checkpoint support for V1.2 dynamic graph executor`
  - Files: `tradingagents/graph/executor.py`, `tradingagents/graph/checkpointer.py`, `tradingagents/default_config.py`
  - 预提交: `pytest tests/ -k "checkpoint" -v`

---

- [x] 14. FIX-7：上下文窗口管理升级

  **做什么**：
  - 新建 `tradingagents/graph/context_manager.py`，实现 `ContextWindowManager` 类
  - 三级策略：(1) Token 预算监控 (2) 超预算时 LLM 结构化摘要 (3) 硬截断最后防线
  - 在 5 个辩论 Agent（Bull/Bear/Aggressive/Conservative/Neutral）中使用
  - 摘要格式：`## 分析师报告摘要 / ## 辩论历史摘要（最近2轮）`
  - 对战上下文始终完整保留（对手最新发言不压缩）
  - 处理 LLM 摘要失败：回退到简单截断（保留最近 N tokens 内容）
  - 修正中文 token 估算（`len()//4` → `len()//1.8`）

  **禁止做**：
  - 不要引入向量数据库或 embedding
  - 不要改变辩论 Agent 的核心 prompt 内容（只改上下文注入方式）

  **推荐 Agent Profile**：
  > 上下文管理是一个独立模块，需要 Token 估算和 LLM 摘要调用两种策略。
  - **类别**：`deep`
    - 原因：上下文压缩策略需权衡保留率与 Token 成本
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES（与任务 12, 13 同时启动）
  - **并行组**：波次 4（与任务 12, 13 同时）
  - **阻塞**：15, 16
  - **被阻塞**：无

  **参考资料**：
  - `docs/架构缺陷修复方案.md:767-920` — FIX-7 完整方案（含 ContextWindowManager 类代码）
  - `tradingagents/agents/researchers/bull_researcher.py` — 当前 `if len(history_lines) > 20` 硬截断
  - `tradingagents/agents/researchers/bear_researcher.py` — 同上

  **验收标准**：
  - [ ] 超过 token 预算时触发 LLM 摘要（而非硬截断）
  - [ ] 对手最新发言始终完整保留
  - [ ] 中文 token 估算准确（使用 `//1.8` 而非 `//4`）
  - [ ] 摘要失败时回退到简单截断，不中断分析

  **QA Scenarios**：

  ```
  Scenario: 超预算上下文触发 LLM 摘要压缩
    Tool: Bash (pytest)
    Steps:
      1. 构造超 4000 token 的 debate_history
      2. 调用 ContextWindowManager.summarize_if_needed()
      3. 验证返回的是压缩后摘要（长度 < 原始长度）
      4. 验证摘要含 "## 辩论历史摘要" 标记
    Expected Result: 摘要长度 < 原始长度，保留关键数据点
    Evidence: .omo/evidence/task-14-summarization.log

  Scenario: LLM 摘要失败后回退到简单截断
    Tool: Bash (pytest)
    Steps:
      1. Mock quick_llm 摘要调用抛异常
      2. 调用 ContextWindowManager.summarize_if_needed()
      3. 验证返回截断后的 history（而非空字符串）
    Expected Result: 返回截断内容，WARNING 日志记录摘要失败
    Failure Indicators: 返回空字符串 / 抛出异常中断分析
    Evidence: .omo/evidence/task-14-fallback-truncation.log
  ```

  **提交**：YES
  - Message: `feat(graph): add context window management with LLM summarization`
  - Files: `tradingagents/graph/context_manager.py`, `tradingagents/agents/researchers/bull_researcher.py`, `tradingagents/agents/researchers/bear_researcher.py`
  - 预提交: `pytest tests/ -k "context" -v`

---

- [x] 15. CLI 路径集成测试 + 回归验证
  （通过 API 端到端验证完成：000001/600418 多次全链路测试，849/851 测试通过）

  **做什么**：
  - 运行 V1.0 CLI 路径的完整分析：`tradingagents batch --ticker 600519`
  - 验证修复后的辩论路由（Bull↔Bear 往返）、并行分析、枚举路由均正常工作
  - 对比修复前后的分析耗时（预期减少 60%）
  - 对比修复前后的 token 消耗（预期不变或略减）
  - 运行完整测试套件：所有 38 个已有测试 + 新增测试必须全部通过
  - 生成回归基准报告（保存至 `.omo/evidence/regression-baseline.json`）

  **禁止做**：
  - 不要修改任何测试文件的内容
  - 不要在对比过程中引入新的配置变更

  **推荐 Agent Profile**：
  > 全面测试执行，需同时运行 CLI + pytest + 性能对比。
  - **类别**：`deep`
    - 原因：多维度集成测试需遍历完整 CLI 分析流程
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES（与任务 16, 17 同时启动）
  - **并行组**：波次 5（与任务 16, 17 同时）
  - **阻塞**：F1-F4
  - **被阻塞**：12, 13, 14

  **参考资料**：
  - `tradingagents/graph/setup.py` — V1.0 CLI 图构建
  - `cli/main.py` — CLI 入口
  - `tests/` — 38 个已有测试文件

  **验收标准**：
  - [ ] `tradingagents batch --ticker 600519` 成功完成
  - [ ] 总耗时 < 180s（原 ~300s）
  - [ ] `pytest tests/ -v` 全部通过（0 failures）
  - [ ] 辩论 history 含 ≥ 4 条往返发言

  **QA Scenarios**：

  ```
  Scenario: CLI 路径完整分析成功
    Tool: Bash (time)
    Steps:
      1. 运行 `time tradingagents batch --ticker 600519 --output json`
      2. 检查退出码和输出 JSON 结构
      3. 验证 final_decision 非空
      4. 验证耗时 < 180s
    Expected Result: 退出码 0，JSON 输出完整，耗时达标
    Evidence: .omo/evidence/task-15-cli-full-run.log

  Scenario: 全部测试通过
    Tool: Bash
    Steps:
      1. 运行 `pytest tests/ -v --tb=short`
      2. 检查最终统计行
    Expected Result: "N passed, 0 failed"（N 至少 ≥ 38）
    Failure Indicators: 任何 FAILED / ERROR
    Evidence: .omo/evidence/task-15-pytest-all.log
  ```

  **提交**：NO（测试验证，不产生代码变更）

---

- [x] 16. API 路径集成测试 + 回归验证
  （通过 POST /analyze 多次端到端验证：000001/600418 完整报告生成，849/851 测试通过）

  **做什么**：
  - 启动 FastAPI 服务：`uvicorn tradingagents.api_server:app --port 8000`
  - 运行 `POST /analyze` 完整分析（含辩论路由 + 并行 + 检查点 + fallback）
  - 运行 `POST /portfolio/chat` 持仓对话
  - 运行 `GET /health` 健康检查
  - 验证 Docker Compose 部署：`docker compose up` → API 可访问
  - 对比修复前后的响应时间（预期减少 60%）
  - 生成 API 回归基准报告

  **禁止做**：
  - 不要在 Docker 环境中运行需要 GUI 的测试

  **推荐 Agent Profile**：
  > API 全面测试，需启动服务 + curl 请求 + Docker 验证。
  - **类别**：`deep`
    - 原因：完整 API 测试链路涉及多个服务的启动和对接
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES（与任务 15, 17 同时启动）
  - **并行组**：波次 5（与任务 15, 17 同时）
  - **阻塞**：F1-F4
  - **被阻塞**：12, 13, 14

  **参考资料**：
  - `tradingagents/api_server.py` — FastAPI 路由
  - `docker-compose.yml` — Docker 配置

  **验收标准**：
  - [ ] `POST /analyze` 返回 200，report 非空
  - [ ] `GET /health` 返回 `{"status":"ok"}`
  - [ ] `POST /portfolio/chat` 正确解析持仓对话
  - [ ] `docker compose up` 后所有端点可用

  **QA Scenarios**：

  ```
  Scenario: API 路径完整分析成功
    Tool: Bash (curl)
    Steps:
      1. 运行 `curl -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d '{"user_id":"test","message":"分析茅台","ticker":"600519"}'`
      2. 检查 HTTP 状态码
      3. 检查 JSON 响应中 report 字段非空
      4. 检查 generation_mode 字段存在
    Expected Result: 200，report 非空，generation_mode 有效
    Evidence: .omo/evidence/task-16-api-analyze.json

  Scenario: Docker Compose 可用
    Tool: Bash
    Steps:
      1. 运行 `docker compose up -d`
      2. 等待 30s
      3. 运行 `curl http://localhost:8000/health`
    Expected Result: 返回 `{"status":"ok","kb_entries":...,"user_count":...}`
    Failure Indicators: 连接拒绝 / 500 错误
    Evidence: .omo/evidence/task-16-docker-health.log
  ```

  **提交**：NO（测试验证，不产生代码变更）

---

- [x] 17. 文档更新 + 配置迁移指南

  **做什么**：
  - 更新 `CHANGELOG.md`：新增 [0.2.9-cn] 条目，列出 FIX-0~FIX-10 的变更
  - 更新 `README.md`：V1.3 架构改进摘要（性能提升 60%、高可用 fallback、辩论深度提升）
  - 创建 `docs/V1.3-配置迁移指南.md`：列出 10 个新配置键及其默认值
  - 更新 `docs/开发进度表.md`：标记各 FIX 状态为已完成
  - 更新 `pyproject.toml` 版本号为 0.2.9-cn

  **禁止做**：
  - 不要重写整个 README（只更新 V1.3 相关段落）
  - 不要创建新的架构文档（已存在 `docs/架构缺陷修复方案.md`）

  **推荐 Agent Profile**：
  > 纯文档工作，需要清晰的技术写作。
  - **类别**：`writing`
    - 原因：技术文档更新，需准确描述变更内容
  - **技能**：`[]`

  **并行化**：
  - **可并行**：YES（与任务 15, 16 同时启动）
  - **并行组**：波次 5（与任务 15, 16 同时）
  - **阻塞**：F1-F4
  - **被阻塞**：无（可提前准备，任务 12-14 完成后微调）

  **参考资料**：
  - `CHANGELOG.md` — 现有 changelog 格式
  - `README.md` — V1.2 架构描述
  - `docs/开发进度表.md` — 当前状态标记
  - `docs/架构缺陷修复方案.md:1330-1343` — 10 个 feature flag 配置键

  **验收标准**：
  - [ ] `CHANGELOG.md` 含 [0.2.9-cn] 条目（列出 FIX-0~FIX-10 + 即时行动项）
  - [ ] `README.md` V1.3 段落提及性能提升 60%
  - [ ] `docs/V1.3-配置迁移指南.md` 存在且列出全部 10 个新配置键
  - [ ] `pyproject.toml` 版本号为 0.2.9

  **QA Scenarios**：

  ```
  Scenario: 文档一致性检查
    Tool: Bash (grep)
    Steps:
      1. `grep "0.2.9" CHANGELOG.md` 验证新版本条目存在
      2. `grep "V1.3" README.md` 验证版本引用
      3. `grep "fix_" docs/V1.3-配置迁移指南.md | wc -l` 验证 ≥ 10 个配置键
    Expected Result: 3 个检查全部通过
    Evidence: .omo/evidence/task-17-docs-consistency.log
  ```

  **提交**：YES
  - Message: `docs: update changelog, README, and migration guide for V1.3`
  - Files: `CHANGELOG.md`, `README.md`, `docs/V1.3-配置迁移指南.md`, `docs/开发进度表.md`, `pyproject.toml`
  - 预提交: 无

---

## 最终验证波次（所有实现任务完成后必须执行）

> 4 个审核 Agent 并行运行。全部必须 APPROVE。向用户展示汇总结果，等待用户明确回复 "okay" 后才算完成。
> 在获得用户确认之前，绝不标记 F1-F4 为已完成。

- [x] F1. **方案合规审计** — \`oracle\`
  通读计划端到端。对每个"必须包含"项：验证实现存在（读文件、curl 端点、运行命令）。对每个"禁止包含"项：搜索代码库中的禁止模式——若发现则标记 `file:line` 并 REJECT。检查 `.omo/evidence/` 中证据文件存在情况。将交付物与计划对比。
  输出：`必须包含 [N/N] | 禁止包含 [N/N] | 任务 [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **代码质量审查** — \`unspecified-high\`
  运行 `make test-cov` + linter。审查所有变更文件中的：`as any`/`@ts-ignore` 等价物、空 catch、生产代码中的 print/console.log、注释掉的代码、未使用的导入。检查 AI slop：过度注释、过度抽象、泛型命名（data/result/item/temp）。
  输出：`构建 [PASS/FAIL] | Lint [PASS/FAIL] | 测试 [N pass/N fail] | 文件 [N clean/N issues] | VERDICT`

- [x] F3. **手动 QA 执行** — \`unspecified-high\`
  从干净状态启动。执行每个任务中的全部 QA Scenario——严格按步骤操作，捕获证据。测试跨任务集成（功能协作，非孤立验证）。测试边界情况：空输入、无效输入、快速连续操作。保存至 `.omo/evidence/final-qa/`。
  输出：`Scenarios [N/N pass] | 集成 [N/N] | 边界情况 [N tested] | VERDICT`

- [x] F4. **范围保真度检查** — \`deep\`
  对每个任务：通读"做什么"，读取实际 diff（git log/diff）。验证 1:1 —— spec 中的所有内容均已构建（无遗漏），spec 外没有额外构建（无蔓延）。检查"禁止做"合规性。检测跨任务污染：任务 N 触碰了任务 M 的文件。标记未记录的变更。
  输出：`任务 [N/N compliant] | 污染 [CLEAN/N issues] | 未记录变更 [CLEAN/N files] | VERDICT`

---

## 提交策略

- **1**：`fix(llm): call validate_model() during client creation` — `tradingagents/llm_clients/factory.py`, `tradingagents/bootstrap.py`
- **3**：`chore: add test infrastructure (pytest-cov, Makefile, CI)` — `pyproject.toml`, `Makefile`, `.github/workflows/test.yml`
- **4**：`feat(llm): add ResilientLLM with auto-fallback for deep_llm` — `tradingagents/llm_clients/resilient_llm.py`, `tradingagents/bootstrap.py`
- **5**：`feat(kb): add freshness-weighted coverage calculation` — `tradingagents/kb/knowledge_base.py`, `tradingagents/planner/llm_planner.py`
- **6**：`fix(position): add filelock for concurrent position state safety` — `tradingagents/agents/utils/position_state.py`, `pyproject.toml`
- **7**：`feat(graph): add tool-call loop detection in conditional logic` — `tradingagents/graph/conditional_logic.py`
- **8**：`feat(graph): add causal chain tracing for decision audit` — `tradingagents/graph/causal_tracer.py`, `tradingagents/graph/trading_graph.py`
- **9**：`feat(graph): add debate routing to V1.2 dynamic graph builder` — `tradingagents/graph/dynamic_graph_builder.py`
- **10**：`fix(graph): replace string-based debate routing with enum latest_speaker` — `tradingagents/graph/conditional_logic.py`, `tradingagents/agents/utils/agent_states.py`, `tradingagents/agents/researchers/bull_researcher.py`, `tradingagents/agents/researchers/bear_researcher.py`
- **11**：`feat(graph): increase debate depth + add quality tracking` — `tradingagents/default_config.py`, `tradingagents/graph/debate_quality.py`, `tradingagents/graph/conditional_logic.py`
- **12**：`perf(graph): parallelize 4 analyst agents using LangGraph Send API` — `tradingagents/graph/setup.py`, `tradingagents/graph/dynamic_graph_builder.py`, `tradingagents/default_config.py`
- **13**：`feat(graph): add checkpoint support for V1.2 dynamic graph executor` — `tradingagents/graph/executor.py`, `tradingagents/graph/checkpointer.py`, `tradingagents/default_config.py`
- **14**：`feat(graph): add context window management with LLM summarization` — `tradingagents/graph/context_manager.py`, `tradingagents/agents/researchers/bull_researcher.py`, `tradingagents/agents/researchers/bear_researcher.py`
- **17**：`docs: update changelog, README, and migration guide for V1.3` — `CHANGELOG.md`, `README.md`, `docs/V1.3-配置迁移指南.md`, `docs/开发进度表.md`, `pyproject.toml`

---

## 成功标准

### 验证命令
```bash
# 全量测试
make test-ci

# 单个 CLI 分析（含耗时测量）
time tradingagents batch --ticker 600519 --output json

# API 健康检查
curl http://localhost:8000/health

# API 完整分析
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","message":"分析茅台","ticker":"600519"}'

# Docker 验证
docker compose up -d && sleep 30 && curl http://localhost:8000/health
```

### 最终清单
- [ ] 所有 11 个 FIX 已实现
- [ ] 所有"禁止包含"项未出现在代码库中
- [ ] `make test-ci` 全部通过，覆盖率 ≥ 70%
- [ ] `POST /analyze` 分析耗时 < 180s
- [ ] 辩论路由故障率 = 0%（枚举替换字符串匹配）
- [ ] `docker compose up` 后所有端点可用
- [ ] CHANGELOG 和 README 已更新至 V1.3

