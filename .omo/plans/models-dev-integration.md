# models.dev 动态模型目录集成

## TL;DR

> **Quick Summary**: 将 models.dev (137 provider 的 AI 模型规格数据库) 集成为 tradingagents-cn 的动态模型目录源，替换当前硬编码的 MODEL_OPTIONS，同时保留硬编码目录作为 fallback。
>
> **Deliverables**:
> - `tradingagents/llm_clients/models_dev_fetcher.py` — HTTP fetch + 磁盘缓存
> - `tradingagents/llm_clients/provider_mapper.py` — provider 名称映射
> - `tradingagents/llm_clients/dynamic_catalog.py` — 动态生成 MODEL_OPTIONS
> - 修改 `model_catalog.py` — 动态优先，硬编码 fallback
> - 修复 `cli/research_report.py` 和 `cli/notice.py` 的 `model_name=` bug
> - 3 个测试文件，覆盖率 ≥85%
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 2 waves (第一波 3 并行，第二波 4 并行)
> **Critical Path**: Task 1 (Fetcher) → Task 4 (Generator) → Task 6 (model_catalog 集成)

---

## Context

### Original Request
用户要求分析 `https://github.com/anomalyco/models.dev` 能否作为当前项目 tradingagents-cn 的模型库。经过深入分析确认可行后，要求生成集成计划。

### Interview Summary
**Key Discussions**:
- **集成级别**: Level 2（中等侵入度）— 新增 fetcher/mapper/generator，修改 model_catalog.py，保持 factory 不变
- **Provider 映射**: 已确认 9 个当前 provider 全部可映射至 models.dev（8 个直接映射，ollama 为本地 runner 无需映射）
- **模型分类**: 使用复合启发式（cost + capability + 名称），**禁止**仅用 `reasoning=true` 作为 deep/quick 标准
- **API Key 策略**: models.dev 提供 `env` 和 `api` 字段告知 key 变量名和端点 URL，但不提供 key 本身

**Research Findings**:
- models.dev API: `https://models.dev/api.json` (137 providers, ~2.1MB JSON)
- 返回格式: `{provider_id: {env, npm, api, models: {model_id: {...}}}}`
- 当前项目硬编码目录有 9 个 provider、约 70 个模型 — 已部分过时（e.g., gpt-5.2 已升级到 gpt-5.5）
- 发现 bug: `cli/research_report.py:30` 和 `cli/notice.py:30` 传递 `model_name=` 而非 `model=` 到 `create_llm_client()`
- `_DEFAULT_ENV_OVERRIDES` 为空是有意设计（bootstrap.py 直接处理 env 覆盖），不是 bug

### Metis Review
**Identified Gaps** (addressed):
- **`reasoning=true` 作为唯一分类标准危险**: 采用复合分类（cost > $1/M 或 family 含 "pro"/"opus"/"max" → deep；其余 → quick），且硬编码目录的既有分类保持不变
- **Provider 映射未验证**: 已全部通过 models.dev API 实际数据验证（9/9）
- **边界情况缺失**: 已涵盖网络故障、JSON 畸形、schema 变更、并发访问、启动性能、废弃模型过滤
- **测试策略未定**: 确定 Tests-after + Agent QA（pytest 8.0.0 + pytest-cov，46 个已有测试文件）

---

## Work Objectives

### Core Objective
用 models.dev 动态数据驱动 `MODEL_OPTIONS` 生成，消除手动维护模型目录的负担，同时保持完全的向后兼容性。

### Concrete Deliverables
- `tradingagents/llm_clients/models_dev_fetcher.py` — 新文件
- `tradingagents/llm_clients/provider_mapper.py` — 新文件
- `tradingagents/llm_clients/dynamic_catalog.py` — 新文件
- `tradingagents/llm_clients/model_catalog.py` — 修改（动态优先 + fallback）
- `tests/test_models_dev_fetcher.py` — 新测试文件
- `tests/test_dynamic_catalog.py` — 新测试文件
- `tests/test_provider_mapper.py` — 新测试文件
- `cli/research_report.py` — 修复 (1 line)
- `cli/notice.py` — 修复 (1 line)

### Definition of Done
- [ ] `pytest tests/test_models_dev_fetcher.py tests/test_dynamic_catalog.py tests/test_provider_mapper.py -v` → ALL PASS
- [ ] `python -c "from tradingagents.llm_clients.model_catalog import get_model_options; print(get_model_options('openai','quick'))"` → 离线时返回硬编码目录（非空）
- [ ] `python -c "from tradingagents.llm_clients.model_catalog import get_known_models; assert 'openai' in get_known_models()"` → PASS
- [ ] `pytest tests/ -k "resilient_llm" -v` → 既有行为不变

### Must Have
- 磁盘缓存 + TTL (24h)
- 网络故障时的优雅降级（使用缓存或 fallback 到硬编码数据）
- 向后兼容的 `get_model_options()` / `get_known_models()` 返回类型
- 复合 deep/quick 分类（禁止仅用 `reasoning=true`）
- `validate_model()` 不收紧 — 未知模型仍通过

### Must NOT Have (Guardrails)
- **禁止**: 仅用 `reasoning=true` 作为 deep/quick 分类（会使 Claude Opus 和 GPT-5.4 误分类为 quick）
- **禁止**: 因 models.dev 不可用而阻止启动（优雅降级）
- **禁止**: 改变 `validate_model()` 的行为（未知模型必须仍通过）
- **禁止**: 删除或修改硬编码 `MODEL_OPTIONS` 字典
- **禁止**: 预调用成本估算（独立功能，本次排除）
- **禁止**: 能力感知模型分发（独立功能，本次排除）
- **禁止**: 自动刷新调度器（独立功能，本次排除）
- **禁止**: 修改 factory.py 分发逻辑（除非 provider 映射需要新条目）

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest 8.0.0 + pytest-cov, 46 个已有测试文件)
- **Automated tests**: Tests-after (新代码先实现，然后补充测试覆盖)
- **Framework**: pytest (bun test / vitest 不适用于 Python 项目)
- **Pattern**: `tests/test_*.py`，使用 `unittest.mock.patch` 模拟 HTTP 调用

### QA Policy
按 TODO 模板要求，每个任务必须包含 agent 执行的 QA 场景。
证据保存到 `.omo/evidence/task-{N}-{scenario-slug}.{ext}`。

- **Backend/Python**: 使用 Bash 运行 pytest，捕获输出和退出码
- **CLI**: 使用 Bash 运行 CLI 命令，验证输出内容
- **HTTP Mock**: 测试中 mock `httpx.get`，不访问真实 API

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately - foundation, all independent):
├── Task 1: models_dev_fetcher.py [deep]
├── Task 2: provider_mapper.py [quick]
├── Task 3: 测试文件 scaffolding [quick]
└── Task 4: 修复 model_name= bug [quick]

Wave 2 (After Wave 1 - core + integration, MAX PARALLEL):
├── Task 5: dynamic_catalog.py (depends: 1, 2) [deep]
├── Task 6: model_catalog.py 集成 (depends: 5) [unspecified-high]
├── Task 7: 完整测试套件 (depends: 5, 6) [unspecified-high]
└── Task 8: CLI/集成验证 (depends: 6) [unspecified-high]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan Compliance Audit (oracle)
├── Task F2: Code Quality Review (unspecified-high)
├── Task F3: Real Manual QA (unspecified-high)
└── Task F4: Scope Fidelity Check (deep)
-> Present results -> Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 5 | 1 |
| 2 | — | 5 | 1 |
| 3 | — | 5,7 | 1 |
| 4 | — | — | 1 |
| 5 | 1,2 | 6,7,8 | 2 |
| 6 | 5 | 7,8 | 2 |
| 7 | 5,6 | — | 2 |
| 8 | 6 | — | 2 |

### Agent Dispatch Summary

- **Wave 1**: **4** — T1→`deep`, T2→`quick`, T3→`quick`, T4→`quick`
- **Wave 2**: **4** — T5→`deep`, T6→`unspecified-high`, T7→`unspecified-high`, T8→`unspecified-high`
- **FINAL**: **4** — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

- [ ] 1. `models_dev_fetcher.py` — HTTP fetch + disk cache module

  **What to do**:
  - Create `tradingagents/llm_clients/models_dev_fetcher.py`
  - Implement `ModelsDevFetcher` class:
    - `__init__(cache_dir="~/.tradingagents/cache/", cache_ttl_hours=24)`: 设置缓存路径和 TTL
    - `fetch() -> Optional[dict]`: 获取 models.dev 数据（缓存优先，过期后重新拉取）
    - `_fetch_from_api() -> dict`: 通过 `httpx` 调用 `https://models.dev/api.json`（30s 超时）
    - `_load_cache() -> Optional[dict]`: 从磁盘读取缓存（`~/.tradingagents/cache/models_dev.json`）
    - `_save_cache(data: dict) -> None`: 原子写入缓存（先写临时文件，再 `os.replace()`）
    - `_is_cache_fresh(cache_path: str) -> bool`: 检查缓存是否在 TTL 内
  - 错误处理：
    - 网络故障 → 返回缓存（即使过期）→ 无缓存时返回 None → 绝不抛异常
    - JSON 解析失败 → 记录警告 → 返回 None（使用缓存或 fallback）
  - 添加 module-level `fetch_models_dev() -> Optional[dict]` 便捷函数
  - 使用 `logging.getLogger(__name__)` 记录所有错误为 WARNING 级别（非 ERROR）
  - 类型注解覆盖所有公开 API

  **Must NOT do**:
  - 不添加后台刷新线程或调度器
  - 不在 fetch 失败时抛出异常（返回 None）
  - 不使用 `requests` 库（使用 `httpx`，与项目已有的 LangChain 生态一致）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 涉及 HTTP 客户端、文件 I/O、原子操作、多层 fallback 逻辑，需要稳健的错误处理设计
  - **Skills**: []
    - 纯 Python 标准库 + httpx，无需特殊技能
  - **Skills Evaluated but Omitted**:
    - `git-master`: 无需 git 操作

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4)
  - **Blocks**: Task 5 (dynamic_catalog.py 依赖 fetcher)
  - **Blocked By**: None (can start immediately)

  **References** (CRITICAL - Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `tradingagents/dashboard/cost_tracker.py:26-31` - SQLite DB 初始化模式（`Path.expanduser()`, `mkdir(parents=True)`)
  - `tradingagents/analysis_archive.py:_empty_index()` - 原子文件写入模式（`tmp + os.replace()`）
  - `tradingagents/dataflows/akshare.py` - HTTP 调用包装风格（异常捕获 + 日志）

  **API/Type References** (contracts to implement against):
  - models.dev API 响应格式: `{provider_id: {env: [...], npm: "", api: "", models: {model_id: {id, name, reasoning, tool_call, structured_output, temperature, cost: {...}, limit: {...}, modalities: {...}}}}}`
  - 返回类型: `Optional[dict]` — None 表示不可用，dict 是完整 JSON

  **External References** (libraries and frameworks):
  - `httpx` 文档: `https://www.python-httpx.org/quickstart/` — HTTP 客户端（同步 `httpx.get()`）
  - `os.replace()` 原子性: Python 标准库 — POSIX 保证的原子 rename

  **Acceptance Criteria**:

  **If TDD (tests enabled):**
  - [ ] Test file: `tests/test_models_dev_fetcher.py`
  - [ ] `pytest tests/test_models_dev_fetcher.py -v` → PASS（≥5 tests, 0 failures）

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Fetch from cache hit (fresh cache)
    Tool: Bash (pytest)
    Preconditions: 预先创建有效的缓存文件（<24h old）
    Steps:
      1. 创建 ~/.tradingagents/cache/models_dev.json 包含 {"openai": {"models": {"gpt-5.5": {}}}} 
      2. 设置缓存文件 mtime 为当前时间
      3. 实例化 ModelsDevFetcher(cache_ttl_hours=24) 并调用 fetch()
      4. 断言返回 dict 且不需要网络调用（mock httpx.get 确保不被调用）
    Expected Result: 返回缓存数据，httpx.get 未被调用
    Failure Indicators: 返回 None；或进行了网络调用
    Evidence: .omo/evidence/task-1-cache-hit.txt (pytest output)

  Scenario: Network failure returns stale cache
    Tool: Bash (pytest)
    Preconditions: 存在过期缓存文件（>24h old），mock httpx.get 抛出 httpx.ConnectError
    Steps:
      1. 创建过期缓存文件
      2. Mock httpx.get 为 side_effect=httpx.ConnectError("Connection refused")
      3. 调用 fetch()
      4. 断言返回缓存数据（即使过期）
    Expected Result: 返回过期缓存，日志包含 WARNING 级别网络错误
    Failure Indicators: 返回 None 或抛出异常
    Evidence: .omo/evidence/task-1-stale-cache.txt

  Scenario: No cache + network failure returns None
    Tool: Bash (pytest)
    Preconditions: 无缓存文件，mock httpx.get 抛出异常
    Steps:
      1. 确保缓存文件不存在
      2. Mock httpx.get 为 side_effect=httpx.ConnectError
      3. 调用 fetch()
      4. 断言返回 None
    Expected Result: 返回 None，日志包含 WARNING
    Failure Indicators: 抛出未捕获异常
    Evidence: .omo/evidence/task-1-no-cache-fail.txt

  Scenario: Malformed JSON response returns None
    Tool: Bash (pytest)
    Preconditions: mock httpx.get 返回内容为 "not valid json{{{"
    Steps:
      1. Mock httpx.get 返回 status=200, text="not valid json{{{"
      2. 调用 fetch()
      3. 断言返回 None
    Expected Result: 返回 None，日志包含 WARNING 级别 JSON 错误
    Failure Indicators: 抛出未捕获异常
    Evidence: .omo/evidence/task-1-malformed-json.txt
  ```

  **Evidence to Capture:**
  - [ ] `task-1-cache-hit.txt` — pytest 输出
  - [ ] `task-1-stale-cache.txt` — pytest 输出
  - [ ] `task-1-malformed-json.txt` — pytest 输出

  **Commit**: YES
  - Message: `feat(llm): add models_dev_fetcher with disk cache and graceful fallback`
  - Files: `tradingagents/llm_clients/models_dev_fetcher.py`, `tests/test_models_dev_fetcher.py`
  - Pre-commit: `pytest tests/test_models_dev_fetcher.py -v`

- [ ] 2. `provider_mapper.py` — Provider 名称映射模块

  **What to do**:
  - Create `tradingagents/llm_clients/provider_mapper.py`
  - Implement `ProviderMapper` class:
    - `_MAPPINGS` 类变量（dict）：已确认的 provider ID 映射
      ```python
      _MAPPINGS: ClassVar[Dict[str, Optional[str]]] = {
          "openai": "openai",
          "anthropic": "anthropic",
          "google": "google",
          "deepseek": "deepseek",
          "xai": "xai",
          "minimax": "minimax",
          "qwen": "alibaba-cn",
          "glm": "zhipuai",
          "ollama": None,    # 本地 runner，不在 models.dev 中
          "openrouter": None, # 聚合器，不在 models.dev 中
          "azure": None,      # 非模型 provider
      }
      ```
    - `map_to_models_dev(internal_name: str) -> Optional[str]`: 返回 models.dev provider ID 或 None
    - `reverse_map(models_dev_name: str) -> Optional[str]`: 反向映射
    - `get_env_var_name(internal_name: str) -> Optional[str]`: 从 models.dev 数据获取 env var 名
    - `get_base_url(internal_name: str) -> Optional[str]`: 从 models.dev 数据获取 API URL
    - `get_all_mapped() -> Dict[str, Optional[str]]`: 返回全部映射
  - Module-level `PROVIDER_MAPPER = ProviderMapper()` 单例

  **Must NOT do**:
  - 不硬编码 base URL 或 API key 变量名（应从 models.dev 数据动态获取）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的字典查找 + 类型转换，无复杂逻辑
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4)
  - **Blocks**: Task 5 (dynamic_catalog.py 依赖映射)
  - **Blocked By**: None (can start immediately)

  **References** (CRITICAL - Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `tradingagents/llm_clients/openai_client.py:162-170` — `_PROVIDER_CONFIG` 字典模式

  **Acceptance Criteria**:
  - [ ] Test file: `tests/test_provider_mapper.py`
  - [ ] `pytest tests/test_provider_mapper.py -v` → PASS（≥4 tests, 0 failures）

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Identity mapping works for standard providers
    Tool: Bash (pytest)
    Preconditions: ProviderMapper 已实例化
    Steps:
      1. 对 "openai"/"anthropic"/"google"/"deepseek"/"xai"/"minimax" 调用 map_to_models_dev()
      2. 断言每个返回相同的字符串
    Expected Result: 所有 6 个 provider 的输入输出一致
    Failure Indicators: 任何映射返回 None 或不同值
    Evidence: .omo/evidence/task-2-identity-map.txt

  Scenario: Alias mapping works for qwen and glm
    Tool: Bash (pytest)
    Preconditions: ProviderMapper 已实例化
    Steps:
      1. 调用 map_to_models_dev("qwen")
      2. 调用 map_to_models_dev("glm")
      3. 断言分别返回 "alibaba-cn" 和 "zhipuai"
    Expected Result: qwen→alibaba-cn, glm→zhipuai
    Failure Indicators: 返回 None 或错误映射
    Evidence: .omo/evidence/task-2-alias-map.txt

  Scenario: Local/aggregator providers return None
    Tool: Bash (pytest)
    Preconditions: ProviderMapper 已实例化
    Steps:
      1. 对 "ollama", "openrouter", "azure" 调用 map_to_models_dev()
      2. 断言全部返回 None
    Expected Result: 三个全部返回 None（确认没有 models.dev 对应）
    Failure Indicators: 返回非 None 值
    Evidence: .omo/evidence/task-2-none-map.txt

  Scenario: All 9 current catalog providers are mapped
    Tool: Bash (pytest)
    Preconditions: ProviderMapper 已实例化
    Steps:
      1. 遍历 ["openai","anthropic","google","deepseek","xai","minimax","qwen","glm","ollama"]
      2. 断言 map_to_models_dev(p) 不被 KeyError 中断（允许返回 None）
    Expected Result: 所有 9 个均正常处理，无异常
    Failure Indicators: KeyError 或未捕获异常
    Evidence: .omo/evidence/task-2-all-mapped.txt
  ```

  **Evidence to Capture:**
  - [ ] `task-2-identity-map.txt`
  - [ ] `task-2-alias-map.txt`
  - [ ] `task-2-none-map.txt`
  - [ ] `task-2-all-mapped.txt`

  **Commit**: YES (与 Tasks 3 为一组)
  - Message: `feat(llm): add ProviderMapper for models.dev provider name resolution`
  - Files: `tradingagents/llm_clients/provider_mapper.py`, `tests/test_provider_mapper.py`
  - Pre-commit: `pytest tests/test_provider_mapper.py -v`

- [ ] 3. 测试文件 scaffolding + conftest

  **What to do**:
  - Create `tests/conftest.py`（若不存在）或同等 fixture 文件
  - 添加共享 fixtures:
    - `sample_models_dev_response()`: 返回最小有效 JSON（包含 3 个 provider 样例数据）
    - `mock_httpx_get(mocker)`: pytest-mock fixture，替换 `httpx.get` 为 mock
    - `temp_cache_dir(tmp_path)`: 临时缓存目录 fixture
  - Create `tests/test_models_dev_fetcher.py` — 带导入占位和 TODO 注释（Task 1 完成后填充测试用例）
  - Create `tests/test_dynamic_catalog.py` — 带导入占位和 TODO 注释
  - Create `tests/test_provider_mapper.py` — 带导入占位和 TODO 注释
  - 确保 `pytest` 能发现所有三个测试文件（即使测试用例尚未填充）
  - 验证 pytest 配置 `pyproject.toml` 中的 `[tool.pytest.ini_options]` 支持 `tests/` 目录

  **Must NOT do**:
  - 不预先填充完整的测试断言（留给后续任务）
  - 不修改 `pyproject.toml` 的现有 pytest 配置

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 创建文件结构 + 简单 fixture，无复杂逻辑
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4)
  - **Blocks**: Task 5 (需测试文件存在), Task 7 (测试填充)
  - **Blocked By**: None (can start immediately)

  **References** (CRITICAL - Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `tests/test_resilient_llm.py` — 已有测试文件结构（导入、pytest.mark、断言风格）
  - `pyproject.toml` — `[tool.pytest.ini_options]` 配置段

  **Acceptance Criteria**:
  - [ ] `pytest tests/ --collect-only -q | grep -E "test_models_dev_fetcher|test_dynamic_catalog|test_provider_mapper"` → 显示 3 个文件
  - [ ] `pytest tests/ --collect-only -q` → 无错误（即使测试用例为空或 skip）

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Test collection discovers all 3 new test files
    Tool: Bash (pytest)
    Preconditions: 三个测试文件已创建
    Steps:
      1. 运行 pytest tests/ --collect-only -q
      2. 在输出中搜索 "test_models_dev_fetcher"
      3. 在输出中搜索 "test_dynamic_catalog"
      4. 在输出中搜索 "test_provider_mapper"
      5. 退出码应为 0（即使无测试用例运行）
    Expected Result: 所有三个文件名出现在收集结果中，exit code 0
    Failure Indicators: 任何文件名不在输出中；exit code 非 0
    Evidence: .omo/evidence/task-3-test-collection.txt

  Scenario: Shared fixtures are importable
    Tool: Bash (python)
    Preconditions: conftest.py 包含 sample_models_dev_response fixture
    Steps:
      1. 运行 `python -c "from tests.conftest import sample_models_dev_response; print('import OK')"`
      2. 若无独立 conftest，使用 `python -c "import tests.test_models_dev_fetcher; print('import OK')"`
    Expected Result: import OK（无 ImportError）
    Failure Indicators: ImportError 或 ModuleNotFoundError
    Evidence: .omo/evidence/task-3-fixture-import.txt
  ```

  **Evidence to Capture:**
  - [ ] `task-3-test-collection.txt`
  - [ ] `task-3-fixture-import.txt`

  **Commit**: YES (与 Task 2 为一组)
  - Message: `test: add scaffolding for models.dev integration tests`
  - Files: `tests/conftest.py`, `tests/test_models_dev_fetcher.py`, `tests/test_dynamic_catalog.py`, `tests/test_provider_mapper.py`

- [ ] 4. 修复 `model_name=` bug in cli/research_report.py and cli/notice.py

  **What to do**:
  - 修复 `cli/research_report.py:30`: `model_name=` → `model=`
  - 修复 `cli/notice.py:30`: `model_name=` → `model=`
  - 验证 `create_llm_client()` 签名接受 `model` 参数（factory.py:16-18 确认 `model: str`）
  - 验证修复后文件无语法错误（`python -m py_compile cli/research_report.py cli/notice.py`）

  **Must NOT do**:
  - 不修改 `create_llm_client()` 签名（保持 factory 不变）
  - 不修改这两个文件的其他逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 两行参数重命名，无逻辑变更
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3)
  - **Blocks**: Task 8 (CLI 验证)
  - **Blocked By**: None (can start immediately)

  **References** (CRITICAL - Be Exhaustive):

  **API/Type References** (contracts to implement against):
  - `tradingagents/llm_clients/factory.py:15-20` — `create_llm_client(provider, model, base_url=None, **kwargs)` 签名
  - `cli/research_report.py:28-31` — bug 所在位置
  - `cli/notice.py:28-31` — bug 所在位置

  **Acceptance Criteria**:
  - [ ] `python -m py_compile cli/research_report.py cli/notice.py` → exit 0
  - [ ] `grep -n "model_name=" cli/research_report.py cli/notice.py` → 无匹配（bug 已消除）

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Both files compile clean after fix
    Tool: Bash
    Preconditions: 已完成 model_name= → model= 修复
    Steps:
      1. python -m py_compile cli/research_report.py
      2. python -m py_compile cli/notice.py
      3. 断言 exit code 均为 0
    Expected Result: 两个文件都编译成功，无 SyntaxError
    Failure Indicators: exit code 非 0；编译错误输出
    Evidence: .omo/evidence/task-4-compile-check.txt

  Scenario: model_name= no longer present
    Tool: Bash (grep)
    Preconditions: 已完成修复
    Steps:
      1. grep -rn "model_name=" cli/research_report.py cli/notice.py
      2. 断言无输出（exit code 非 0）
    Expected Result: 无匹配行
    Failure Indicators: grep 返回匹配行
    Evidence: .omo/evidence/task-4-grep-clean.txt
  ```

  **Evidence to Capture:**
  - [ ] `task-4-compile-check.txt`
  - [ ] `task-4-grep-clean.txt`

  **Commit**: YES
  - Message: `fix(cli): correct model_name= to model= in create_llm_client calls`
  - Files: `cli/research_report.py`, `cli/notice.py`
  - Pre-commit: `python -m py_compile cli/research_report.py cli/notice.py`

- [ ] 5. `dynamic_catalog.py` — 从 models.dev 数据生成 MODEL_OPTIONS

  **What to do**:
  - Create `tradingagents/llm_clients/dynamic_catalog.py`
  - Implement `DynamicCatalogGenerator` class:
    - `generate(models_dev_data: dict) -> ProviderModeOptions`: 将 models.dev JSON 转换为 `ProviderModeOptions` 格式（与 `MODEL_OPTIONS` 兼容）
    - `_classify_deep(model_entry: dict) -> bool`: **复合分类**（关键禁则：不得仅用 `reasoning=true`）
      - Deep 判定: `cost_input > 1.0` **或** `reasoning == True` **或** family/name 含 `"pro"`/`"opus"`/`"max"`
      - Quick 判定: 前述条件均不满足
    - `_build_model_options(models: dict) -> List[Tuple[str, str]]`: 生成 `[(label, model_id), ...]`
      - Label 格式: `"{name} - {short_description}"`（从 models.dev 的 name + family 组合）
      - Deep 列表取 top 5（按 context window → cost 降序）
      - Quick 列表取 top 8（按 cost 升序）
    - `_filter_usable_models(models: dict) -> dict`: 过滤：
      - 排除 `status` 为 `"alpha"`/`"beta"`/`"deprecated"` 的模型
      - 仅保留 OpenAI-compatible 或已知 SDK 的 provider（通过 `npm` 字段判断）
  - 对 provider_mapper 中映射为 `None` 的 provider（ollama/openrouter/azure），**不**生成条目
  - Module-level `generate_dynamic_catalog(models_dev_data) -> ProviderModeOptions` 便捷函数

  **Must NOT do**:
  - **禁止**仅用 `reasoning=true` 分类（Claude Opus、GPT-5.4 会误分类）
  - **禁止**修改已有的硬编码 `MODEL_OPTIONS` 结构
  - **禁止**为 ollama/openrouter/azure 生成动态条目

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 涉及数据转换算法、分类逻辑、过滤规则、schema 兼容性验证，需要仔细设计
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (与 Tasks 6, 7, 8，但以下依赖链存在)
  - **Blocks**: Tasks 6, 7, 8
  - **Blocked By**: Tasks 1, 2

  **References** (CRITICAL - Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `tradingagents/llm_clients/model_catalog.py:11-128` — `MODEL_OPTIONS` 目标格式（`Dict[str, Dict[str, List[Tuple[str,str]]]]`）
  - `tradingagents/llm_clients/provider_mapper.py` — 通过 `PROVIDER_MAPPER` 单例获取映射

  **API/Type References** (contracts to implement against):
  - `model_catalog.py:7-8`: `ModelOption = Tuple[str, str]`, `ProviderModeOptions = Dict[str, Dict[str, List[ModelOption]]]`

  **External References** (libraries and frameworks):
  - models.dev 数据结构（参考已缓存的 API 响应）: `provider.models[model_id].cost.input`, `.reasoning`, `.limit.context`

  **Acceptance Criteria**:
  - [ ] `generate(mock_data)` 返回的结构与 `MODEL_OPTIONS` schema 完全兼容
  - [ ] 分类逻辑: Claude Opus（reasoning=false, cost=$5）→ deep ✓
  - [ ] 分类逻辑: GPT-5.4 Mini（reasoning=false, cost=$0.75）→ quick ✓
  - [ ] 分类逻辑: Grok 4.1 Fast Reasoning（reasoning=true, cost=$1.25）→ deep ✓
  - [ ] Test file: `tests/test_dynamic_catalog.py`
  - [ ] `pytest tests/test_dynamic_catalog.py -v` → PASS

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Generated catalog has correct schema
    Tool: Bash (pytest)
    Preconditions: sample_models_dev_response fixture 包含 openai, anthropic, deepseek 数据
    Steps:
      1. 调用 generate_dynamic_catalog(sample_data)
      2. 断言结果类型为 dict
      3. 对每个 provider，断言有 "quick" 和 "deep" 两个 key
      4. 断言每个 model 条目为 (str, str) tuple
    Expected Result: 返回的 dict 结构完全匹配 ProviderModeOptions schema
    Failure Indicators: 缺少 "quick"/"deep" key；tuple 格式错误
    Evidence: .omo/evidence/task-5-schema-compat.txt

  Scenario: Claude Opus classified as deep (NOT quick)
    Tool: Bash (pytest)
    Preconditions: sample data 包含 anthropic/claude-opus-4-6（reasoning=false, cost_input=$5）
    Steps:
      1. 调用 generate_dynamic_catalog(sample_data)
      2. 在 anthropic["deep"] 中搜索 "claude-opus"
      3. 断言在 deep 列表中找到；在 quick 列表中找不到
    Expected Result: claude-opus-4-6 在 deep 列表中（即使在 models.dev 中 reasoning=false）
    Failure Indicators: 在 quick 列表中出现；两个列表都出现或都未出现
    Evidence: .omo/evidence/task-5-opus-deep.txt

  Scenario: GPT-5.4 Mini classified as quick (NOT deep)
    Tool: Bash (pytest)
    Preconditions: sample data 包含 openai/gpt-5.4-mini（reasoning=false, cost_input=$0.75）
    Steps:
      1. 调用 generate_dynamic_catalog(sample_data)
      2. 在 openai["quick"] 中搜索 "gpt-5.4-mini"
      3. 断言在 quick 列表中找到；在 deep 列表中找不到
    Expected Result: gpt-5.4-mini 在 quick 列表中
    Failure Indicators: 在 deep 列表中出现
    Evidence: .omo/evidence/task-5-mini-quick.txt

  Scenario: Alpha/beta/deprecated models excluded
    Tool: Bash (pytest)
    Preconditions: sample data 包含 status="deprecated" 的模型
    Steps:
      1. 调用 generate_dynamic_catalog(sample_data)
      2. 搜索所有 provider 的 quick + deep 列表
      3. 断言无 status="deprecated" 的模型 ID 出现
    Expected Result: 废弃模型不出现在任何列表中
    Failure Indicators: 废弃模型出现在生成结果中
    Evidence: .omo/evidence/task-5-filter-deprecated.txt
  ```

  **Evidence to Capture:**
  - [ ] `task-5-schema-compat.txt`
  - [ ] `task-5-opus-deep.txt`
  - [ ] `task-5-mini-quick.txt`
  - [ ] `task-5-filter-deprecated.txt`

  **Commit**: YES (与 Task 6 为一组)
  - Message: `feat(llm): add DynamicCatalogGenerator from models.dev data`
  - Files: `tradingagents/llm_clients/dynamic_catalog.py`, `tests/test_dynamic_catalog.py`
  - Pre-commit: `pytest tests/test_dynamic_catalog.py -v`

- [ ] 6. 修改 `model_catalog.py` — 动态优先 + 硬编码 fallback

  **What to do**:
  - 修改 `tradingagents/llm_clients/model_catalog.py`:
    - 保留现有 `MODEL_OPTIONS` 硬编码字典 **不变**
    - 新增 `_DYNAMIC_CATALOG_CACHE: Optional[ProviderModeOptions] = None` module-level 变量
    - 新增 `_init_dynamic_catalog() -> ProviderModeOptions` 函数:
      1. 调用 `fetch_models_dev()` → 若返回 None → return `MODEL_OPTIONS`
      2. 调用 `generate_dynamic_catalog(data)` → 若失败 → return `MODEL_OPTIONS`
      3. **合并策略**: 硬编码 `MODEL_OPTIONS` 中的 provider 条目 **覆盖** 动态生成的同 provider 条目（硬编码目录是分类权威）
      4. 对硬编码目录中不存在的 provider，动态条目直接采用
      5. 缓存结果到 `_DYNAMIC_CATALOG_CACHE`
    - 修改 `get_model_options(provider, mode)`:
      1. 若 `_DYNAMIC_CATALOG_CACHE` 为空 → 调用 `_init_dynamic_catalog()`
      2. 从 dynamic cache 按 `provider` + `mode` 查找
      3. Fallback: 若找不到 → 降级到 `MODEL_OPTIONS[provider][mode]`
    - 修改 `get_known_models()`:
      1. 从 dynamic cache 提取所有已知模型
      2. 合并硬编码字典中的模型（去重）
  - 确保功能标识：所有 `import model_catalog` 的代码**不受影响**

  **Must NOT do**:
  - **禁止**删除或修改 `MODEL_OPTIONS` 硬编码字典
  - **禁止**改变 `get_model_options()` 和 `get_known_models()` 的返回类型签名
  - **禁止**因动态 catalog 不可用而抛出异常

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 涉及现有模块修改、合并策略、fallback 链，需要理解代码依赖关系
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (与 Tasks 7, 8 部分依赖)
  - **Blocks**: Tasks 7, 8
  - **Blocked By**: Task 5

  **References** (CRITICAL - Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `tradingagents/llm_clients/model_catalog.py` — 完整修改目标
  - `tradingagents/llm_clients/validators.py:13-26` — `validate_model()` 调用 `get_known_models()`，不得破坏

  **API/Type References** (contracts to implement against):
  - `model_catalog.py:131-133`: `get_model_options(provider, mode) -> List[ModelOption]`
  - `model_catalog.py:136-147`: `get_known_models() -> Dict[str, List[str]]`
  - `cli/utils.py:222-229`: `select_shallow_thinking_agent()` / `select_deep_thinking_agent()` 调用 `get_model_options()`

  **Why Each Reference Matters**:
  - `model_catalog.py` 是直接修改目标 — 必须理解现有逻辑
  - `validators.py` 消费 `get_known_models()` — 修改后必须不变
  - `cli/utils.py` 是主要消费方 — 返回类型变化会破坏 CLI

  **Acceptance Criteria**:
  - [ ] 离线时 `get_model_options("openai", "quick")` 返回硬编码数据（非空）
  - [ ] `get_known_models()` 包含 `"openai"` 等已知 provider（离线情况）
  - [ ] 现有测试 `pytest tests/ -k "resilient" -v` → 不被破坏
  - [ ] 现有 CLI 命令 `echo "1" | timeout 5 python -m cli.main 2>&1 | head -5` → 无 traceback

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Offline fallback returns hardcoded data
    Tool: Bash
    Preconditions: 无网络连接或 mock 网络故障
    Steps:
      1. python -c "
  from unittest.mock import patch
  import httpx
  with patch('httpx.get', side_effect=httpx.ConnectError('offline')):
      from tradingagents.llm_clients.model_catalog import get_model_options
      result = get_model_options('openai', 'quick')
      assert len(result) > 0, 'should return hardcoded data'
      print(f'OK: {len(result)} models')
  "
    Expected Result: 输出 "OK: N models" 且无 traceback
    Failure Indicators: AssertionError（空列表）或 traceback
    Evidence: .omo/evidence/task-6-offline-fallback.txt

  Scenario: get_known_models still works
    Tool: Bash
    Preconditions: get_known_models 未被修改破坏
    Steps:
      1. python -c "from tradingagents.llm_clients.model_catalog import get_known_models; m = get_known_models(); assert 'openai' in m; print('openai models:', m['openai'][:3])"
    Expected Result: 输出包含 "openai models: [...]"
    Failure Indicators: KeyError 或 AssertionError
    Evidence: .omo/evidence/task-6-known-models.txt

  Scenario: Dynamic catalog merges without overwriting hardcoded authority
    Tool: Bash (pytest)
    Preconditions: mock models.dev 数据包含额外的 openai 模型
    Steps:
      1. 调用 _init_dynamic_catalog()（mock 网络）
      2. 断言硬编码 openai 模型仍然存在（在动态结果中）
      3. 断言动态引入的新 provider（如 moonshotai）也出现在结果中
    Expected Result: 硬编码模型保留 + 新 provider 出现 = 并集
    Failure Indicators: 硬编码条目被替换或消失
    Evidence: .omo/evidence/task-6-merge-strategy.txt
  ```

  **Evidence to Capture:**
  - [ ] `task-6-offline-fallback.txt`
  - [ ] `task-6-known-models.txt`
  - [ ] `task-6-merge-strategy.txt`

  **Commit**: YES (与 Task 5 为一组)
  - Message: `feat(llm): integrate dynamic catalog from models.dev with hardcoded fallback`
  - Files: `tradingagents/llm_clients/model_catalog.py`
  - Pre-commit: `pytest tests/ -k "resilient" -v`

- [ ] 7. 完整测试套件 — 填充所有测试文件

  **What to do**:
  - 填充 `tests/test_models_dev_fetcher.py`（若 Task 1 期间未完成）:
    - `test_fetch_cache_hit()`: 新鲜缓存 → 无网络调用
    - `test_fetch_cache_miss_network_ok()`: 无缓存 → 网络调用成功 → 写入缓存
    - `test_fetch_network_failure_stale_cache()`: 网络故障 → 返回过期缓存
    - `test_fetch_no_cache_network_failure()`: 无缓存 + 网络故障 → 返回 None
    - `test_fetch_malformed_json()`: JSON 解析失败 → 返回 None
    - `test_cache_write_atomic()`: 原子写入（临时文件 → rename）
    - `test_cache_freshness_ttl()`: TTL 检查逻辑
  - 填充 `tests/test_dynamic_catalog.py`:
    - `test_generated_schema_compatible()`: 返回结构匹配 ProviderModeOptions
    - `test_classify_deep_by_cost()`: cost>$1 → deep
    - `test_classify_deep_by_reasoning()`: reasoning=true → deep
    - `test_classify_deep_by_name()`: "pro"/"opus"/"max" → deep
    - `test_classify_quick_by_default()`: 非 deep 条件 → quick
    - `test_exclude_deprecated()`: status="deprecated" → 排除
    - `test_exclude_alpha_beta()`: status="alpha"/"beta" → 排除
    - `test_no_duplicates()`: 无模型同时在 deep 和 quick 中出现
    - `test_ollama_excluded()`: ollama provider 不生成条目
  - 填充 `tests/test_provider_mapper.py`:
    - `test_identity_mappings()`: 标准 provider 返回自身
    - `test_alias_mappings()`: qwen→alibaba-cn, glm→zhipuai
    - `test_local_providers_none()`: ollama/openrouter/azure→None
    - `test_all_catalog_providers_mapped()`: 所有 9 个均处理
    - `test_reverse_map()`: 反向映射
  - 确保所有测试使用 `pytest.mark` 和 `assert`（非 print-based checks）
  - Mock 所有 HTTP 调用（`unittest.mock.patch('httpx.get')`）
  - 目标覆盖率: ≥85%（f`pytest --cov=tradingagents/llm_clients tests/ --cov-report=term`）

  **Must NOT do**:
  - 不在测试中访问真实 models.dev API（必须 mock）
  - 不跳过测试（`@pytest.mark.skip` 仅在无法 mock 的场景下使用）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 需要填充多个测试文件，覆盖边界条件，需要系统性的测试设计
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (与 Tasks 6, 8)
  - **Blocks**: None
  - **Blocked By**: Tasks 5, 6

  **References** (CRITICAL - Be Exhaustive):

  **Test References** (testing patterns to follow):
  - `tests/test_resilient_llm.py` — 现有测试文件（断言风格、mock 模式、pytest 约定）

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_models_dev_fetcher.py tests/test_dynamic_catalog.py tests/test_provider_mapper.py -v` → ALL PASS（≥20 tests total, 0 failures）
  - [ ] `pytest --cov=tradingagents/llm_clients/models_dev_fetcher --cov=tradingagents/llm_clients/dynamic_catalog --cov=tradingagents/llm_clients/provider_mapper tests/ --cov-report=term` → ≥85% 覆盖率

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All tests pass with coverage threshold
    Tool: Bash
    Preconditions: 所有测试已填充
    Steps:
      1. pytest tests/test_models_dev_fetcher.py tests/test_dynamic_catalog.py tests/test_provider_mapper.py -v --tb=short
      2. 断言 exit code 0
      3. 断言测试总数 ≥ 20
      4. pytest --cov=tradingagents/llm_clients/models_dev_fetcher --cov=tradingagents/llm_clients/dynamic_catalog --cov=tradingagents/llm_clients/provider_mapper --cov-report=term tests/
      5. 断言覆盖率 ≥ 85%
    Expected Result: 所有测试 PASS，覆盖率 ≥85%
    Failure Indicators: 任何 FAIL；测试数 <20；覆盖率 <85%
    Evidence: .omo/evidence/task-7-all-tests.txt
  ```

  **Evidence to Capture:**
  - [ ] `task-7-all-tests.txt` — 完整 pytest 输出 + 覆盖率报告

  **Commit**: YES
  - Message: `test: complete test suite for models.dev integration with >=85% coverage`
  - Files: `tests/test_models_dev_fetcher.py`, `tests/test_dynamic_catalog.py`, `tests/test_provider_mapper.py`, `tests/conftest.py`
  - Pre-commit: `pytest tests/test_models_dev_fetcher.py tests/test_dynamic_catalog.py tests/test_provider_mapper.py -v`

- [ ] 8. CLI + 集成端到端验证

  **What to do**:
  - 验证 CLI 在改动后仍正常工作:
    - `tradingagents --help` → 无 crash
    - CLI provider 选择菜单 → 无 traceback
  - 验证端到端 bootstrap:
    - 在有 API key 或无 API key 的情况下，bootstrap 均应无 fatal error
  - 验证 `validate_model()` 行为不变:
    - 已知模型仍通过验证
    - 未知模型仍通过验证（警告但不阻止）
  - 验证既有测试未被破坏:
    - `pytest tests/ -k "resilient_llm" -v` → PASS
    - `pytest tests/ -k "knowledge" -v` → PASS
  - 确认 models.dev 缓存文件存在于 `~/.tradingagents/cache/models_dev.json`
  - 运行 `python -c "from tradingagents.llm_clients.model_catalog import get_model_options; print(len(get_model_options('openai','quick')))"` → 输出 ≥5（有模型可用）

  **Must NOT do**:
  - 不修改任何 CLI 入口逻辑（仅验证）
  - 不修改 bootstrap.py 或 api_server.py

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 跨模块集成验证，需要运行多个命令并验证结果
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (与 Tasks 7)
  - **Blocks**: None
  - **Blocked By**: Task 6

  **References** (CRITICAL - Be Exhaustive):

  **Pattern References** (existing code to follow):
  - `tradingagents/bootstrap.py:75-149` — bootstrap 流程，理解 LLM 创建步骤
  - `tradingagents/llm_clients/validators.py:13-26` — validate_model 逻辑

  **Acceptance Criteria**:
  - [ ] `tradingagents --help 2>&1 | head -5` → 显示 CLI 帮助无 traceback
  - [ ] `pytest tests/ -k "resilient_llm" -v` → PASS
  - [ ] `python -c "from tradingagents.llm_clients.model_catalog import get_model_options; assert len(get_model_options('openai','quick')) >= 5"` → PASS
  - [ ] `python -c "from tradingagents.llm_clients.validators import validate_model; assert validate_model('openai', 'gpt-5.4')"` → True

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: CLI help works without crash
    Tool: Bash
    Preconditions: 所有改动已完成
    Steps:
      1. PYTHONPATH=. python -m cli.main --help 2>&1 | head -10
      2. 断言 exit code 0
      3. 断言输出包含 "Usage" 或 "Commands"
    Expected Result: CLI 帮助正常显示
    Failure Indicators: exit code 非 0；输出为 traceback
    Evidence: .omo/evidence/task-8-cli-help.txt

  Scenario: Existing tests not broken
    Tool: Bash
    Preconditions: 所有改动已完成
    Steps:
      1. pytest tests/ -k "resilient_llm" -v
      2. 断言 exit code 0
    Expected Result: 既有测试全部 PASS
    Failure Indicators: 既有测试出现 FAIL（回归）
    Evidence: .omo/evidence/task-8-regression-tests.txt

  Scenario: Model validation still permissive
    Tool: Bash
    Preconditions: 所有改动已完成
    Steps:
      1. python -c "
from tradingagents.llm_clients.validators import validate_model
assert validate_model('openai', 'gpt-5.5'), 'known model should pass'
assert validate_model('openai', 'unknown-model-xyz'), 'unknown model should still pass'
print('validation: OK')
"
    Expected Result: 输出 "validation: OK"
    Failure Indicators: AssertionError（模型验证被收紧）
    Evidence: .omo/evidence/task-8-validation-ok.txt

  Scenario: Model options return data offline
    Tool: Bash
    Preconditions: 无网络或 mock 离线
    Steps:
      1. python -c "
from tradingagents.llm_clients.model_catalog import get_model_options
opts = get_model_options('openai', 'quick')
assert len(opts) > 0, f'got {len(opts)} options, expected >0'
print(f'openai quick models: {len(opts)}')
"
    Expected Result: 输出 "openai quick models: N"，N≥5
    Failure Indicators: AssertionError（空列表）
    Evidence: .omo/evidence/task-8-models-offline.txt

  Scenario: Cache file created on first fetch
    Tool: Bash
    Preconditions: 清除现有缓存
    Steps:
      1. rm -f ~/.tradingagents/cache/models_dev.json
      2. python -c "from tradingagents.llm_clients.models_dev_fetcher import fetch_models_dev; fetch_models_dev()"
      3. ls -la ~/.tradingagents/cache/models_dev.json
      4. 断言文件存在
    Expected Result: 缓存文件成功创建
    Failure Indicators: 文件不存在
    Evidence: .omo/evidence/task-8-cache-file.txt
  ```

  **Evidence to Capture:**
  - [ ] `task-8-cli-help.txt`
  - [ ] `task-8-regression-tests.txt`
  - [ ] `task-8-validation-ok.txt`
  - [ ] `task-8-models-offline.txt`
  - [ ] `task-8-cache-file.txt`

  **Commit**: NO（仅验证，不产生代码变更）

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run pytest). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .omo/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `python -m py_compile` on all new files. Run `pytest tests/test_models_dev_fetcher.py tests/test_dynamic_catalog.py tests/test_provider_mapper.py -v`. Check coverage ≥85%. Review all changed files for: `except: pass`, `print()` in prod, hardcoded API keys, unused imports, AI slop patterns. Verify type annotations on public APIs.
  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | Coverage [X%] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state (no cache file). Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration: fetcher → generator → model_catalog. Test edge cases: empty cache, network down, malformed JSON, schema mismatch. Save to `.omo/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Wave 1 (T1-4)**: 4 commits, 可单独合并
  - `feat(llm): add models_dev_fetcher with disk cache and graceful fallback` — `tradingagents/llm_clients/models_dev_fetcher.py`, `tests/test_models_dev_fetcher.py`
  - `feat(llm): add ProviderMapper + test scaffolding` — `tradingagents/llm_clients/provider_mapper.py`, `tests/test_provider_mapper.py`, `tests/conftest.py`, `tests/test_dynamic_catalog.py`
  - `fix(cli): correct model_name= to model= in create_llm_client calls` — `cli/research_report.py`, `cli/notice.py`
- **Wave 2 (T5-8)**: 3 commits
  - `feat(llm): add DynamicCatalogGenerator + integrate into model_catalog` — `tradingagents/llm_clients/dynamic_catalog.py`, `tests/test_dynamic_catalog.py`, `tradingagents/llm_clients/model_catalog.py`
  - `test: complete test suite with >=85% coverage` — all test files (final versions)
  - No commit for Task 8 (verification only)

---

## Success Criteria

### Verification Commands
```bash
# Core tests
pytest tests/test_models_dev_fetcher.py tests/test_dynamic_catalog.py tests/test_provider_mapper.py -v
# Expected: ALL PASS, >=20 tests

# Coverage
pytest --cov=tradingagents/llm_clients/models_dev_fetcher --cov=tradingagents/llm_clients/dynamic_catalog --cov=tradingagents/llm_clients/provider_mapper tests/ --cov-report=term
# Expected: >=85%

# Offline fallback
python -c "from tradingagents.llm_clients.model_catalog import get_model_options; assert len(get_model_options('openai','quick')) >= 5"
# Expected: no AssertionError

# Regression
pytest tests/ -k "resilient_llm" -v
# Expected: ALL PASS
```

### Final Checklist
- [ ] All "Must Have" present (7 items)
- [ ] All "Must NOT Have" absent (8 items)
- [ ] All tests pass (≥20 tests, 0 failures)
- [ ] Coverage ≥85%
- [ ] CLI not broken (`tradingagents --help` works)
- [ ] Hardcoded MODEL_OPTIONS preserved as fallback
- [ ] `validate_model()` still permissive
- [ ] Offline fallback returns hardcoded data
