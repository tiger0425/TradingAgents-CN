# 行业框架体系技术文档

> **文档类型**: 技术参考  
> **日期**: 2026-06-02  
> **状态**: 已实现  
> **关联模块**: `tradingagents/industry/`  
> **关联文档**: `CHANGELOG.md`、`README.md`  
> **版本**: 0.2.10-cn

---

## 1. 概述

### 1.1 问题背景

在 TauricResearch TradingAgents 原版框架中，LLM Agent 分析不同行业公司时**缺乏行业感知能力**。Agent 常将某个行业的分析指标错误地套用到另一个行业——例如为光纤光缆制造商（永鼎股份）生成含"1.6T 光模块 ASP"和"CPO 技术路线"的分析报告，而这些指标实际适用于光通信下游器件公司（中际旭创、新易盛）。

初始方案（v0.2.10）通过手工定义的 5 个行业框架（汽车、银行、科技SaaS、消费品、医药）提供了基本的行业匹配和反模式检测能力。但面对 A 股 300+ 个行业分类，手工穷举不可行；依赖 LLM 自动生成时，`_AUTO_GEN_PROMPT` 仅要求包含 SaaS 反模式，LLM 对其他跨行业误用指标缺乏约束，生成质量不稳定。

### 1.2 解决方案

建立**两层行业框架体系**：

```
┌──────────────────────────────────────────────────────┐
│                   Layer 1: 行业类型规则                │
│                  (_type_rules)                        │
│  6 种行业类型，每种预定义通用 anti_patterns             │
│  解决：所有行业自动继承其类型的不适用指标                │
├──────────────────────────────────────────────────────┤
│                   Layer 2: 具体行业框架                │
│                  (frameworks)                         │
│  已知行业的精细化框架定义                               │
│  解决：模糊匹配 → 精确匹配 + 反模式扫描                  │
└──────────────────────────────────────────────────────┘
```

### 1.3 核心设计原则

| 原则 | 实现 |
|------|------|
| **不穷举** | 不为每个行业手工写框架 — Layer 2 覆盖高频行业，Layer 1 兜底 |
| **继承不覆盖** | `anti_patterns = type_rules.anti_patterns ∪ industry_specific.anti_patterns`（并集） |
| **向后兼容** | `_load()` 同时支持新旧 JSON 格式，旧版本数据可无缝迁移 |
| **关键字防御** | 具体框架 keywords 使用复合词（如"通信线缆"）而非短词（"通信"），防止模糊匹配劫持 |
| **确定性优先** | Layer 1 规则为硬约束（代码级）；Layer 2 缺失时降级为 LLM 自动生成（软约束） |

---

## 2. 架构设计

### 2.1 模块结构

```
tradingagents/industry/
├── __init__.py           # 对外导出：IndustryClassifier, IndustryResult, IndustryFramework, IndustryVerifier
├── classifier.py         # L1: 行业分类器（封装 get_industry() → 结构化 IndustryResult）
├── frameworks.py         # L2: 框架查询引擎（模糊匹配 + LLM 自动生成）
├── verifier.py           # L3: 一致性校验器（规则扫描 + LLM 语义 fallback）
└── config/
    ├── industry_frameworks.json      # 手工定义：_type_rules (6) + frameworks (6)
    └── generated_frameworks.json     # 自动生成缓存（持久化 LLM 生成结果）
```

### 2.2 数据流

```
股票代码 (e.g. "600105")
  │
  ├─→ IndustryClassifier.classify(code)
  │     └─→ get_industry() [a_stock_data/mootdx/F10]
  │           └─→ IndustryResult { primary, secondary, confidence, source }
  │
  ├─→ IndustryFramework.lookup(industry)
  │     │
  │     ├─ 1. _fuzzy_match() ─ 4 级匹配（精确 → 子串 → 反向子串 → token 分割）
  │     │     └─→ 返回 Layer 2 框架 dict（如果命中）
  │     │
  │     ├─ 2. generated cache ─ 检查运行时生成的缓存
  │     │
  │     └─ 3. _auto_generate() ─ LLM 现场生成
  │           └─→ _AUTO_GEN_PROMPT (3 步：判定类型 → 继承反模式 → 生成框架)
  │                 └─→ 缓存到 generated_frameworks.json
  │
  └─→ build_instrument_context()
        └─→ Agent 系统提示词注入：
              "**行业分析框架（必须遵守）：**
               - 核心指标：G.652.D散纤现货价、运营商年度光缆集采价格...
               - 不适用指标：1.6T光模块ASP、CPO技术路线、ARR..."
```

### 2.3 Layer 1 — 行业类型规则

6 种行业类型定义在 `_type_rules` 中，每种包含 `anti_patterns`（该类型绝对不能出现的指标）和 `correct_metrics_examples`（该类型典型指标示例）。

| 类型 Key | 中文名 | anti_patterns 数量 | 典型禁止指标 |
|----------|--------|-------------------|-------------|
| `manufacturing` | 制造业/重资产 | 15 | 光模块ASP、CPO、AI算力需求、续约率、LTV/CAC、ARR、NRR、MAU |
| `financial` | 金融/银行/保险 | 11 | 月度销量、GMV、续约率、产能利用率、经销商库存 |
| `consumer` | 消费品/白酒/食品 | 12 | 续约率、ARR、NRR、不良贷款率、净息差 |
| `pharma` | 医药/生物医药 | 12 | 续约率、ARR、月度销量、批价、经销商库存 |
| `tech_saas` | 科技/SaaS/软件 | 7 | 光缆集采价、铜铝成本、光棒产能、运营商集采招标量 |
| `telecom_operator` | 运营商/通信基础设施 | 6 | 月度销量、产能利用率、原材料成本占比 |

> **设计依据**：每种类型的 `anti_patterns` 基于对 A 股 5 大类行业标准分析框架的通用排除规则。例如制造业不应出现 SaaS 指标（按次付费/续约/MAU），金融业不应出现制造业实物指标（月度销量/产能利用率）。

### 2.4 Layer 2 — 具体行业框架

| 框架 Key | 行业名 | correct_metrics | anti_patterns | 类型归属 |
|----------|--------|----------------|---------------|---------|
| `automotive` | 汽车与商用车 | 8 | 12 | manufacturing |
| `banking` | 银行与金融 | 10 | 11 | financial |
| `tech_saas` | 科技与SaaS | 15 | 0 (类型规则填平) | tech_saas |
| `consumer` | 消费品与白酒 | 10 | 12 | consumer |
| `pharma` | 医药与生物医药 | 9 | 12 | pharma |
| **`comm_cable`** | **通信线缆及配套** | **12** | **17** | manufacturing |

> **comm_cable 框架说明**：基于华泰证券（2026/4/24）、国盛证券（2026/3/15）、中信建投（2026/2/15）、天风证券（2026/2/28）等多家券商研报。12 项 correct_metrics 覆盖三层价格体系（散纤现货价→运营商集采价→长协价）、供给侧硬约束（光棒产能利用率、自给率）、成本结构（铜铝占比60-70%）、财务质量（经营现金流/净利润≥0.8）。17 项 anti_patterns 显式阻止 6 项光模块相关 + 11 项 SaaS/平台/消费品指标的跨行业误用。keywords 全部使用复合词（"通信线缆"而非"通信"），防止"通信设备"等不相关标的被误匹配。

### 2.5 JSON 结构

```json
{
  "_type_rules": {
    "manufacturing": {
      "name": "制造业与重资产",
      "anti_patterns": ["光模块ASP", "CPO技术路线", ...],
      "correct_metrics_examples": ["产能利用率", "毛利率", ...]
    },
    ...
  },
  "frameworks": {
    "comm_cable": {
      "name": "通信线缆及配套",
      "name_en": "comm_cable",
      "keywords": ["通信线缆", "光纤光缆", "光缆制造", ...],
      "correct_metrics": ["G.652.D散纤现货价", ...],
      "anti_patterns": ["1.6T光模块ASP", "CPO技术路线", ...],
      "peer_companies": ["永鼎股份", "亨通光电", ...],
      "context_instruction": "该企业属于通信线缆及配套行业..."
    },
    "automotive": { ... },
    ...
  }
}
```

---

## 3. 核心 API

### 3.1 IndustryFramework

`tradingagents.industry.frameworks.IndustryFramework`

行业框架查询引擎，负责模糊匹配 + LLM 自动生成。

```python
class IndustryFramework:
    def __init__(self, frameworks_path: str | Path | None = None)
    def lookup(self, industry_name: str, quick_llm: Any = None) -> FrameworkDict | None
    def list_frameworks(self) -> list[FrameworkDict]
    def get_type_rules(self) -> dict[str, FrameworkDict]
```

#### `lookup(industry_name, quick_llm=None) → FrameworkDict | None`

6 级查找流程：

1. **Exact keyword match** — `name` 直接命中 framework keywords 列表中的任何一项
2. **Substring match (keyword ⊂ input)** — `"通信"` in `"通信线缆及配套"` → 命中含有该 keyword 的框架
3. **Reverse substring match (input ⊂ keyword)** — `"汽车"` in `"新能源汽车"` → 命中
4. **Token split match** — 分割输入并用各 token 匹配
5. **Generated cache** — 查找运行时 LLM 生成的缓存
6. **LLM auto-generation** — 当 `quick_llm` 提供且无缓存命中时，通过 `_AUTO_GEN_PROMPT` 现场生成

#### `_AUTO_GEN_PROMPT` 三步流程

LLM 自动生成时，prompt 强制执行三步流程：

1. **判定行业类型** — 从 6 种类型中选择最匹配的一个
2. **继承类型通用 anti_patterns** — 强制包含该类型的全部不适用指标
3. **追加行业特有 anti_patterns + 生成 correct_metrics** — 并集合并，不覆盖

这确保了即使对新行业（如"航空制造"），LLM 也会继承 `manufacturing` 类型的通用反模式（排除光模块/SaaS指标），再补充航空行业特有的指标。

> **v0.2.10-cn 更新**：`_AUTO_GEN_PROMPT` 已改为动态生成方式。新增 `_build_auto_gen_prompt()` 方法，从 `self._type_rules` JSON 运行时构建 prompt 中的类型列表和反模式规则（同时注入 `anti_patterns` + `correct_metrics_examples`），彻底消除 JSON 与 prompt 间的硬编码重复。当 `_type_rules` 为空时自动回退到原硬编码常量，保证向后兼容。

### 3.2 IndustryClassifier

`tradingagents.industry.classifier.IndustryClassifier`

封装 `get_industry()` 调用，返回结构化结果。

```python
@dataclass
class IndustryResult:
    primary: str       # 一级行业分类
    secondary: str     # 二级行业分类
    confidence: float  # 0.0-1.0
    source: str        # 数据来源
    raw: Any           # 原始返回值

class IndustryClassifier:
    @staticmethod
    def classify(code: str) -> IndustryResult
```

### 3.3 IndustryVerifier

`tradingagents.industry.verifier.IndustryVerifier`

两层一致性校验：规则扫描 + LLM 语义 fallback。

```python
class IndustryVerifier:
    @staticmethod
    def is_known(result: IndustryResult) -> bool
    @staticmethod
    def is_confident(result: IndustryResult, threshold: float = 0.5) -> bool
    @staticmethod
    def verify_industry_consistency(
        industry: str, report: str, quick_llm: Any = None
    ) -> dict  # {"consistent": bool, "issues": [...], "severity": str, "method": str}
```

#### 校验流程

```
report text
  │
  ├─ Tier 1: Rule-based anti-pattern keyword scan
  │     │  获取 framework 的 anti_patterns 列表
  │     │  对每条 anti_pattern 在 report 中做 case-insensitive 子串匹配
  │     └─ 命中 → consistent=False, severity="error" → 立即返回
  │
  └─ Tier 2: LLM semantic fallback
        │  (仅在 Tier 1 未命中时触发)
        │  截取前 2000 字符 → 送入 LLM 做语义一致性校验
        └─ 异常时优雅降级为 consistent=True
```

### 3.4 build_instrument_context()

`tradingagents.agents.utils.agent_utils.build_instrument_context()`

将行业框架注入 Agent system prompt。7 个 Agent（4 个分析师 + trader + portfolio_manager + research_manager）均通过此函数接收行业约束。

```python
def build_instrument_context(
    ticker: str,
    industry: str = "",
    company_name: str = "",
    quick_llm: Any = None
) -> str
```

当 `industry` 非空时，输出格式为：

```
**行业背景：** 该股票属于 通信线缆及配套 行业。分析时请关注该行业的核心指标和竞争格局。

**行业分析框架（必须遵守）：**
- 核心指标：G.652.D散纤现货价、运营商年度光缆集采价格及招标量、...
- 不适用指标：1.6T光模块ASP、光模块出货量、CPO技术路线、...

分析指导：该企业属于通信线缆及配套行业。核心变量是三层价格体系...
```

---

## 4. 配置

### 4.1 手工定义框架

文件：`tradingagents/industry/config/industry_frameworks.json`

**结构**：

```json
{
  "_type_rules": {
    "<type_key>": {
      "name": "中文名称",
      "anti_patterns": ["禁止指标1", ...],
      "correct_metrics_examples": ["示例指标1", ...]
    }
  },
  "frameworks": {
    "<framework_key>": {
      "name": "中文行业名",
      "name_en": "english_name",
      "keywords": ["匹配关键词1", ...],
      "correct_metrics": ["核心指标1", ...],
      "anti_patterns": ["不适用指标1", ...],
      "peer_companies": ["同行公司1", ...],
      "context_instruction": "50-80字中文分析指导"
    }
  }
}
```

**添加新行业框架**：

1. 确定行业归属的类型（从 6 种中选择）
2. 在 `frameworks` 中添加新 entry，填写全部字段
3. `anti_patterns` 至少包含该类型的所有通用 anti_patterns + 行业特有项
4. `keywords` 避免使用过于宽泛的短词

**添加新行业类型**：

1. 在 `_type_rules` 中添加新 entry
2. 更新 `_AUTO_GEN_PROMPT` 中第二步的类型列表
3. `anti_patterns` 至少 5 项

### 4.2 自动生成缓存

文件：`tradingagents/industry/config/generated_frameworks.json`

运行时自动维护，存储 LLM 生成的框架，避免重复调用。手动添加框架后，同名 industry 将优先匹配手工框架，缓存条目自然失效。

### 4.3 向后兼容

`_load()` 方法通过双重 key 检测机制兼容新旧 JSON 格式：

```python
if "_type_rules" in raw and "frameworks" in raw:
    # 新格式：嵌套结构
    self._type_rules = raw["_type_rules"]
    self._frameworks = raw["frameworks"]
else:
    # 旧格式：扁平 dict
    self._type_rules = {}
    self._frameworks = raw
```

这意味着现有的扁平格式 JSON 文件可以不做任何修改直接使用，只是不会享受类型规则带来的 Layer 1 保护。

---

## 5. 部署集成

### 5.1 API 服务调用链

```
POST /analyze
  │
  ├─ 1. get_industry(ticker) → 行业分类
  │
  ├─ 2. IndustryFramework.lookup(industry, quick_llm=llm)
  │     └─→ 返回 framework dict 或 None
  │
  ├─ 3. build_instrument_context(industry=industry, quick_llm=llm)
  │     └─→ 注入 Agent system prompt
  │
  ├─ 4. Agent 分析（约束在行业框架内）
  │
  └─ 5. IndustryVerifier.verify_industry_consistency() [TODO]
```

### 5.2 7 个 Agent 的行业注入

| Agent | 注入方式 | 特有上下文 |
|-------|---------|-----------|
| `fundamentals_analyst` | `build_instrument_context()` | 行业估值框架指导 |
| `market_analyst` | `build_instrument_context()` | 行业技术面特征 |
| `news_analyst` | `build_instrument_context()` | 行业政策关注点 |
| `social_media_analyst` | `build_instrument_context()` | 行业舆情特征 |
| `trader` | `build_instrument_context()` | 行业交易特征 |
| `portfolio_manager` | `build_instrument_context()` | 行业基准参考 |
| `research_manager` | `build_instrument_context()` | 行业基准参考 |
| `bull_researcher` | 独立 prompt 注入 | "行业锚定约束" |
| `bear_researcher` | 独立 prompt 注入 | "行业锚定约束" |

---

## 6. 测试

### 6.1 测试覆盖

| 测试文件 | 测试数量 | 覆盖范围 |
|---------|---------|---------|
| `test_industry_framework.py` | 8 | 框架匹配正确性、全框架向后兼容、list_frameworks 过滤 |
| `test_industry_verifier.py` | 13 | 规则扫描、LLM fallback、边界条件、优雅降级 |
| `test_industry_classifier.py` | 11 | 三层 fallback、结构化分类、置信度检查 |

### 6.2 关键测试场景

```
# 核心 bug 验证
fw.lookup("通信线缆及配套") → comm_cable (NOT tech_saas)

# 向后兼容
fw.lookup("汽车制造") → automotive
fw.lookup("银行") → banking
fw.lookup("白酒") → consumer
fw.lookup("SaaS") → tech_saas
fw.lookup("医药") → pharma

# 反模式扫描
verify_industry_consistency("汽车制造", "建议关注续约率和LTV/CAC...") → consistent=False

# 边界
"通信设备" → NOT comm_cable (匹配 tech_saas 是 OK 的)
"通信" alone → 不应匹配 comm_cable
```

---

## 7. 性能与成本

| 操作 | 成本 | 延迟 |
|------|------|------|
| `_fuzzy_match()` | 免费（纯本地） | <1ms |
| `_load()` | 免费（纯本地） | <10ms (JSON parse) |
| Tier 1 校验（规则扫描） | 免费（纯本地） | <1ms |
| `_auto_generate()` | ~$0.005（LLM 调用） | ~2s |
| Tier 2 校验（LLM fallback） | ~$0.001（LLM 调用） | ~1s |

> 绝大多数匹配在 Layer 1（机器学习 cost-free）；LLM 仅在未知行业首次出现时调用（Tier 1 auto-generation），后续从缓存读取。

---

## 8. 已知限制与未来改进

### 当前限制

1. ~~**IndustryVerifier 未接入生产流程**~~ ✅ **已解决** — `executor.py` 每次成功分析后自动调用 `verify_industry_consistency()`（flag-and-continue），检测到反模式时追加警告到报告并返回验证结果。`AnalyzeResponse` 新增 `industry_verification` 字段。
2. **tech_saas 框架 anti_patterns 为空** — 依赖 Layer 1 `_type_rules.tech_saas` 7 条 anti_patterns 补全
3. **`_AUTO_GEN_PROMPT` 中类型规则硬编码** — 与 `_type_rules` JSON 重复定义，存在维护一致性风险
4. **仅覆盖 6 个具体行业** — 扩展需要手工 JSON 配置或依赖 LLM 自动生成

### 改进方向

| 优先级 | 改进 | 说明 |
|--------|------|------|
| P1 | 接入 `IndustryVerifier` 到 `executor.py` | Agent 分析完成 → 校验 → 不通过则要求 Agent 修正 |
| P1 | `_AUTO_GEN_PROMPT` 从 JSON 动态注入类型规则 | 消除硬编码，单一真相源 |
| P2 | 扩展行业框架覆盖 | 至少补充：军工/航空航天、化工/石化、电力/能源 |
| P2 | Framework 版本管理 | `generated_frameworks.json` 增加 expire/version 字段 |
| P3 | 类型自动分类（无 LLM） | 基于 keywords 匹配实现冷启动类型判定 |

---

## 9. 参考资料

- [华泰证券] 王兴等.《光纤光缆进入历史大周期》. 2026-04-24
- [国盛证券] 《光纤光缆：AI驱动下的新周期》. 2026-03-15
- [中信建投] 《光纤光缆行业迎来景气周期》. 2026-02-15
- [天风证券] 《中天科技：光通信+海缆双轮驱动》. 2026-02-28
- [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
- [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
