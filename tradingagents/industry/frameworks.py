"""Industry framework lookup — maps Chinese industry descriptions to evaluation frameworks.

Usage:
    fw = IndustryFramework()
    framework = fw.lookup("汽车制造")   # -> automotive framework dict
    framework = fw.lookup("白酒")       # -> consumer framework dict
    framework = fw.lookup("不存在的")   # -> None
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent / "config"
_FRAMEWORKS_FILE = _CONFIG_DIR / "industry_frameworks.json"
_GENERATED_FILE = _CONFIG_DIR / "generated_frameworks.json"

_AUTO_GEN_PROMPT = """你是A股行业分析专家。请为【{industry}】行业生成分析框架。

## 第一步：判断行业类型
从以下6种类型中选择最匹配的一个：manufacturing(制造业)、financial(金融)、consumer(消费品)、pharma(医药)、tech_saas(科技/SaaS)、telecom_operator(运营商/通信基础设施)

## 第二步：继承类型通用anti_patterns
根据你判断的行业类型，必须继承该类型的所有通用anti_patterns（不适用指标）。每个类型对应的通用anti_patterns为：
- manufacturing: 光模块ASP、CPO技术路线、光模块出货量、AI算力需求、GPU需求、续约率、LTV/CAC、ACV、ARR、NRR、月活跃用户、云端订阅、客单价、GMV、DAU
- financial: 月度销量、新能源渗透率、客单价、GMV、月活跃用户、续约率、LTV/CAC、产能利用率、原材料成本占比、经销商库存、批价
- consumer: 续约率、LTV/CAC、ACV、ARR、NRR、云端订阅、月度销量、产能利用率、新能源渗透率、原材料成本占比、不良贷款率、净息差
- pharma: 续约率、LTV/CAC、ACV、ARR、NRR、月度销量、产能利用率、新能源渗透率、批价、经销商库存、净息差、不良贷款率
- tech_saas: 光缆集采价、铜铝原材料成本、光棒产能、运营商集采招标量、电力电缆在手订单、批价、经销商库存
- telecom_operator: 月度销量、产能利用率、新能源渗透率、原材料成本占比、批价、经销商库存

## 第三步：追加行业特有anti_patterns + 生成correct_metrics
在继承的类型通用anti_patterns基础上，追加该行业特有的跨行业误用指标。然后生成该行业最重要的8-10个分析指标。

按以下JSON格式返回（只返回JSON）：
{{
  "name": "{industry}",
  "name_en": "",
  "industry_type": "判断出的行业类型key",
  "keywords": ["{industry}", "列举5-10个同义词或子行业"],
  "correct_metrics": ["列举8-10个该行业最重要的分析指标"],
  "anti_patterns": ["继承的类型通用anti_patterns" + "该行业特有的anti_patterns（合并，不覆盖）"],
  "peer_companies": ["列举5-8家A股龙头公司"],
  "context_instruction": "50-80字中文分析指导"
}}

要求：
- anti_patterns必须是：类型通用anti_patterns ∪ 行业特有anti_patterns（并集合并，不覆盖）
- correct_metrics必须是该行业真实使用的核心指标
- peer_companies必须是A股真实上市公司"""


FrameworkDict = dict[str, Any]


class IndustryFramework:
    """Loads industry frameworks from JSON and provides fuzzy-name lookup."""

    def __init__(self, frameworks_path: str | Path | None = None) -> None:
        self._frameworks_path: Path = Path(frameworks_path) if frameworks_path else _FRAMEWORKS_FILE
        self._generated_path: Path = _GENERATED_FILE
        self._frameworks: dict[str, FrameworkDict] = {}
        self._type_rules: dict[str, FrameworkDict] = {}
        self._generated: dict[str, FrameworkDict] = {}
        self._load()
        self._load_generated()

    def lookup(self, industry_name: str, quick_llm: Any = None) -> FrameworkDict | None:
        if not industry_name:
            return None

        name = industry_name.strip()

        # 1-4. Existing fuzzy matching against hand-written frameworks
        result = self._fuzzy_match(name)
        if result is not None:
            return result

        # 5. Check generated cache (in-memory)
        result = self._generated.get(name)
        if result is not None:
            return result

        # 6. LLM auto-generation (only when quick_llm is provided)
        if quick_llm is not None:
            return self._auto_generate(name, quick_llm)

        return None

    def _fuzzy_match(self, name: str) -> FrameworkDict | None:
        # 1. Exact keyword match (fast path)
        for key, fw in self._frameworks.items():
            if name in fw.get("keywords", []):
                return fw

        # 2. Substring match — keyword is contained in the input
        matched = []
        for key, fw in self._frameworks.items():
            for kw in fw.get("keywords", []):
                if kw and kw in name:
                    matched.append((len(kw), key, fw))

        # 3. Substring match — input is contained in a keyword
        if not matched:
            for key, fw in self._frameworks.items():
                for kw in fw.get("keywords", []):
                    if kw and name in kw:
                        matched.append((len(kw), key, fw))

        if matched:
            matched.sort(key=lambda t: -t[0])
            return matched[0][2]

        # 4. Partial token match
        tokens = [t for sep in " /-–—,、;；" for part in [name.split(sep)] for t in part]
        if len(tokens) > 1:
            for token in tokens:
                token = token.strip()
                if not token:
                    continue
                for key, fw in self._frameworks.items():
                    if token in fw.get("keywords", []):
                        return fw
                    for kw in fw.get("keywords", []):
                        if kw and (kw in token or token in kw):
                            return fw

        return None

    def _auto_generate(self, industry_name: str, quick_llm: Any) -> FrameworkDict | None:
        """Generate a framework for an unknown industry via LLM, then cache it."""
        try:
            prompt = _AUTO_GEN_PROMPT.format(industry=industry_name)
            response = quick_llm.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            framework = _parse_json_response(text)
            if framework is None:
                logger.warning("LLM generated unparseable JSON for industry: %s", industry_name)
                return None

        except Exception as exc:
            logger.warning("LLM auto-generation failed for %s: %s", industry_name, exc)
            return None

        self._cache_generated(industry_name, framework)
        return framework

    def _cache_generated(self, key: str, framework: FrameworkDict) -> None:
        self._generated[key] = framework
        try:
            if self._generated_path.exists():
                with open(self._generated_path, encoding="utf-8") as f:
                    existing = json.load(f)
            else:
                existing = {}
            existing[key] = framework
            with open(self._generated_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            logger.info("Cached auto-generated framework for: %s", key)
        except Exception as exc:
            logger.warning("Failed to persist generated framework for %s: %s", key, exc)

    def _load_generated(self) -> None:
        if not self._generated_path.exists():
            return
        try:
            with open(self._generated_path, encoding="utf-8") as f:
                self._generated = json.load(f)
            logger.info("Loaded %d generated frameworks from cache", len(self._generated))
        except Exception as exc:
            logger.warning("Failed to load generated frameworks: %s", exc)
            self._generated = {}

    def list_frameworks(self) -> list[FrameworkDict]:
        """Return all registered frameworks (sorted by key), excluding type rules."""
        return [self._frameworks[k] for k in sorted(self._frameworks) if k != "_type_rules"]

    def get_type_rules(self) -> dict[str, FrameworkDict]:
        """Return all industry type rules."""
        return dict(self._type_rules)

    # ── internals ───────────────────────────────────────────────────────

    def _load(self) -> None:
        path = self._frameworks_path
        if not path.exists():
            logger.warning("Industry frameworks file not found: %s", path)
            self._frameworks = {}
            self._type_rules = {}
            return
        try:
            with open(path, encoding="utf-8") as f:
                raw: Any = json.load(f)
            if not isinstance(raw, dict):
                raise TypeError("Expected JSON object at top level")

            # Detect format: new nested vs old flat
            if "_type_rules" in raw and "frameworks" in raw:
                # New nested format
                self._type_rules = raw["_type_rules"]
                self._frameworks = raw["frameworks"]
            else:
                # Old flat format (backward compat)
                self._type_rules = {}
                self._frameworks = raw

            logger.info("Loaded %d industry frameworks and %d type rules from %s",
                         len(self._frameworks), len(self._type_rules), path)
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            logger.error("Failed to load industry frameworks from %s: %s", path, exc)
            self._frameworks = {}
            self._type_rules = {}


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Extract JSON from an LLM response that may contain markdown fences."""
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None
