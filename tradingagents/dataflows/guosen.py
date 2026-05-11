"""
国信证券 (Guosen Securities) 数据源模块 for TradingAgents.

基于国信证券专业接口，覆盖 A股/港股/美股 行情查询、财务三表、宏观经济、
智能选股、基金对比、ETF筛选等能力。

所有对外函数返回 `str` 类型，兼容 TradingAgents 工具系统。

依赖:
    - requests: HTTP 库 (已在项目 pyproject.toml 中)

环境变量:
    - GS_API_KEY: 国信 API 密钥 (行情/财务/宏观/选股共用)
    - COZE_GUOSEN_API_KEY_7627085587157205043: 基金对比专用
    - COZE_GUOSEN_API_KEY_7627056463827140634: ETF筛选器专用
"""

from __future__ import annotations

import json
import os
import ssl
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

# ============================================================================
# 常量与配置
# ============================================================================

BASE_URL = "https://dgzt.guosen.com.cn/skills"
SOFT_NAME = "goldsun_skills"
TIMEOUT = 30

_GS_API_KEY = os.environ.get("GS_API_KEY", "")
_FUND_CMP_KEY = os.environ.get("COZE_GUOSEN_API_KEY_7627085587157205043", "")
_ETF_FLT_KEY = os.environ.get("COZE_GUOSEN_API_KEY_7627056463827140634", "")

# 市场代码映射
_MARKET_CODE_MAP: Dict[str, tuple] = {
    # first_digit → (set_code, market_str)
    "5": (1, "SH"),   # 上海 ETF
    "6": (1, "SH"),   # 上海主板
    "0": (0, "SZ"),   # 深圳主板
    "1": (0, "SZ"),   # 深圳（15/16 开头 ETF）
    "2": (0, "SZ"),   # 深圳（中小板残留）
    "3": (0, "SZ"),   # 深圳创业板
    "8": (2, "SZ"),   # 北交所
    "4": (1, "SH"),   # 老三板
}

# 涨跌幅查询 setDomain 映射
_RANK_SET_DOMAIN = {
    "上证A股": 0,
    "深证A股": 2,
    "沪深A股": 6,
    "创业板": 14,
    "北交所": 14515,
    "沪深ETF": 11005,
}


# ============================================================================
# SSL / Session 工厂 — 兼容国信旧版 TLS
# ============================================================================

class _LegacyTLSAdapter(HTTPAdapter):
    """requests adapter: 禁用证书校验 + 允许旧版 TLS 重协商。"""

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        try:
            ctx.set_ciphers("ALL:@SECLEVEL=0")
        except Exception:
            pass
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def _create_session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", _LegacyTLSAdapter())
    return s


_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _create_session()
    return _session


# ============================================================================
# 内部辅助
# ============================================================================

def _ensure_gs_api_key() -> str:
    """校验 GS_API_KEY，未配置时抛出明确的错误提示。"""
    key = os.environ.get("GS_API_KEY", "")
    if not key:
        raise RuntimeError(
            "缺少 GS_API_KEY 环境变量。请创建 .env 文件并添加:\n"
            "  GS_API_KEY=your_api_key_here"
        )
    return key


def _ensure_fund_cmp_key() -> str:
    key = os.environ.get("COZE_GUOSEN_API_KEY_7627085587157205043", "")
    if not key:
        raise RuntimeError("缺少 COZE_GUOSEN_API_KEY_7627085587157205043 环境变量")
    return key


def _ensure_etf_key() -> str:
    key = os.environ.get("COZE_GUOSEN_API_KEY_7627056463827140634", "")
    if not key:
        raise RuntimeError("缺少 COZE_GUOSEN_API_KEY_7627056463827140634 环境变量")
    return key


def _make_request(
    url: str,
    params: Dict[str, Any],
    timeout: int = TIMEOUT,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """统一请求层：注入公共参数、发送请求、返回 JSON。"""
    if api_key is None:
        api_key = os.environ.get("GS_API_KEY", "")

    params.setdefault("softName", SOFT_NAME)
    if api_key and "apiKey" not in params:
        params["apiKey"] = api_key

    try:
        resp = _get_session().get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.Timeout:
        return {"error": f"请求超时 ({timeout}s): {url}"}
    except requests.RequestException as e:
        return {"error": str(e)}


def _code_to_market(symbol: str) -> tuple:
    """将6位A股代码映射到 (set_code, market_str)。"""
    symbol = symbol.strip()
    first = symbol[0]
    return _MARKET_CODE_MAP.get(first, (0, "SZ"))


def _format_json_result(data: Any, title: str = "") -> str:
    """格式化 JSON 结果为易读字符串。"""
    parts = []
    if title:
        parts.append(f"# {title}")
        parts.append(f"# 数据来源: 国信证券")
        parts.append(f"# 请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        parts.append("")

    if isinstance(data, dict):
        if "error" in data:
            return f"错误: {data['error']}"
        # 尝试美化输出
        parts.append(json.dumps(data, ensure_ascii=False, indent=2))
    elif isinstance(data, str):
        parts.append(data)
    else:
        parts.append(str(data))

    return "\n".join(parts)


# ============================================================================
# 1. 行情查询 (Stock Market Query)
# ============================================================================

def get_real_time_quote(
    symbol: Annotated[str, "A股6位代码 (如 600519, 000001)"],
) -> str:
    """查询单个证券实时行情。

    返回最新价、涨跌幅、成交量等实时数据。
    非交易时段返回上一交易日收盘价。
    """
    try:
        _ensure_gs_api_key()
        code, set_code, _ = _code_to_market(symbol)

        url = f"{BASE_URL}/gsnews/market/agentbot/queryHQInfo/1.0"
        params = {
            "code": code,
            "setCode": set_code,
            "target": 0,
        }
        result = _make_request(url, params)
        return _format_json_result(result, f"实时行情: {symbol}")
    except Exception as e:
        return f"查询行情失败 ({symbol}): {str(e)}"


def get_multi_quote(
    symbols: Annotated[str, "股票代码列表，逗号分隔 (如 '600519,000858')"],
) -> str:
    """查询多个证券实时行情（不返回关联指数信息）。

    单次最多 10 个证券。
    """
    try:
        _ensure_gs_api_key()
        codes = [s.strip() for s in symbols.split(",") if s.strip()]
        markets = [_code_to_market(c) for c in codes]

        url = f"{BASE_URL}/gsnews/market/agentbot/queryCombHQ/1.0"
        params = {
            "code": ",".join(codes),
            "setCode": ",".join(str(m[1]) for m in markets),
            "target": 0,
        }
        result = _make_request(url, params)
        return _format_json_result(result, f"批量行情: {len(codes)} 只股票")
    except Exception as e:
        return f"批量查询失败: {str(e)}"


def get_fund_flow(
    symbol: Annotated[str, "A股6位代码"],
    period: Annotated[int, "查询周期(日)，最多60日"] = 60,
) -> str:
    """查询个股资金流向，包括主力/大户/散户资金进出。

    仅支持沪深市场。
    """
    try:
        _ensure_gs_api_key()
        code, set_code, _ = _code_to_market(symbol)

        url = f"{BASE_URL}/gsnews/market/agentbot/queryFundFlow/1.0"
        params = {
            "code": code,
            "setCode": str(set_code),
            "period": str(min(period, 60)),
        }
        result = _make_request(url, params)
        return _format_json_result(result, f"资金流向: {symbol} (近{min(period, 60)}日)")
    except Exception as e:
        return f"资金流向查询失败 ({symbol}): {str(e)}"


def get_rankings(
    set_domain: Annotated[int, "查询类型: 0-上证A股, 2-深证A股, 6-沪深A股(默认), 14-创业板"] = 6,
    want_num: Annotated[int, "返回数量，最多80"] = 10,
    sort_type: Annotated[int, "排序: 1-涨幅(默认), 2-跌幅"] = 1,
) -> str:
    """查询涨跌幅排名。

    示例: get_rankings(6, 20, 1) → 沪深A股涨幅前20
    """
    try:
        _ensure_gs_api_key()
        url = f"{BASE_URL}/gsnews/market/agentbot/queryMultiHQ/1.0"
        params = {
            "setDomain": set_domain,
            "wantNum": min(want_num, 80),
            "sortType": sort_type,
            "target": 0,
        }
        result = _make_request(url, params)
        sort_name = "涨幅" if sort_type == 1 else "跌幅"
        return _format_json_result(result, f"{sort_name}排名 (前{min(want_num, 80)})")
    except Exception as e:
        return f"排名查询失败: {str(e)}"


def get_historical_hq(
    symbol: Annotated[str, "A股6位代码"],
    days: Annotated[int, "近N个交易日 (默认20)"] = 20,
) -> str:
    """查询历史 K 线数据（日K）。

    返回近 N 个交易日的开高低收量，可选 MA 均线。
    """
    try:
        _ensure_gs_api_key()
        code, set_code, _ = _code_to_market(symbol)

        url = f"{BASE_URL}/gsnews/market/agentbot/queryPastHQ/1.0"
        params = {
            "code": code,
            "setCode": set_code,
            "wantNums": days,
            "target": 0,
        }
        result = _make_request(url, params)
        return _format_json_result(result, f"历史行情: {symbol} (近{days}日)")
    except Exception as e:
        return f"历史行情查询失败 ({symbol}): {str(e)}"


# ============================================================================
# 2. 财务数据 (Stock Financial Query)
# ============================================================================

def get_balance_sheet(
    symbol: Annotated[str, "A股6位代码"],
    report_type: Annotated[str, "财报类型: Q0-最新, Q4-年报, Q2-半年报, Q3-三季报, Q1-一季报"] = "Q0",
    report_year: Annotated[Optional[str], "财报年份 (如 '2024')"] = None,
    count: Annotated[int, "财报数量"] = 1,
) -> str:
    """查询A股资产负债表。

    返回总资产、总负债、股东权益等核心科目。
    """
    try:
        _ensure_gs_api_key()
        code, set_code, market = _code_to_market(symbol)

        url = f"{BASE_URL}/gsnews/gsf10/financial/balanceSheet/1.0"
        params: Dict[str, Any] = {
            "code": code,
            "market": market,
            "reportType": report_type,
            "count": str(count),
        }
        if report_year:
            params["reportYear"] = report_year

        result = _make_request(url, params)
        return _format_json_result(result, f"资产负债表: {symbol}")
    except Exception as e:
        return f"资产负债表查询失败 ({symbol}): {str(e)}"


def get_income_statement(
    symbol: Annotated[str, "A股6位代码"],
    report_type: Annotated[str, "财报类型: Q0-最新, Q4-年报, Q2-半年报, Q3-三季报, Q1-一季报"] = "Q0",
    report_year: Annotated[Optional[str], "财报年份"] = None,
    count: Annotated[int, "财报数量"] = 1,
) -> str:
    """查询A股利润表。

    返回营业收入、净利润、毛利率、EPS 等核心指标。
    """
    try:
        _ensure_gs_api_key()
        code, set_code, market = _code_to_market(symbol)

        url = f"{BASE_URL}/gsnews/gsf10/financial/incomeStatement/1.0"
        params: Dict[str, Any] = {
            "code": code,
            "market": market,
            "reportType": report_type,
            "count": str(count),
        }
        if report_year:
            params["reportYear"] = report_year

        result = _make_request(url, params)
        return _format_json_result(result, f"利润表: {symbol}")
    except Exception as e:
        return f"利润表查询失败 ({symbol}): {str(e)}"


def get_cashflow_statement(
    symbol: Annotated[str, "A股6位代码"],
    report_type: Annotated[str, "财报类型: Q0-最新, Q4-年报, Q2-半年报, Q3-三季报, Q1-一季报"] = "Q0",
    report_year: Annotated[Optional[str], "财报年份"] = None,
    count: Annotated[int, "财报数量"] = 1,
) -> str:
    """查询A股现金流量表。

    返回经营/投资/筹资活动现金流。
    """
    try:
        _ensure_gs_api_key()
        code, set_code, market = _code_to_market(symbol)

        url = f"{BASE_URL}/gsnews/gsf10/financial/cashFlowStatement/1.0"
        params: Dict[str, Any] = {
            "code": code,
            "market": market,
            "reportType": report_type,
            "count": str(count),
        }
        if report_year:
            params["reportYear"] = report_year

        result = _make_request(url, params)
        return _format_json_result(result, f"现金流量表: {symbol}")
    except Exception as e:
        return f"现金流量表查询失败 ({symbol}): {str(e)}"


# ============================================================================
# 3. 宏观经济数据 (Economy Query)
# ============================================================================

def get_macro_data(
    query: Annotated[str, "自然语言查询 (如 '中国近五年GDP同比增速')"],
) -> str:
    """查询全球宏观经济数据。

    覆盖指标: GDP, CPI, PPI, PMI, M2, 社融, 利率, 汇率, 大宗商品价格等。
    支持中国及全球主要经济体。
    """
    try:
        _ensure_gs_api_key()
        url = f"{BASE_URL}/agent/adapter/query"
        params = {
            "text": query,
        }
        result = _make_request(url, params, timeout=60)
        return _format_json_result(result, f"宏观经济: {query}")
    except Exception as e:
        return f"宏观数据查询失败: {str(e)}"


# ============================================================================
# 4. 智能选股 (Smart Stock Picking)
# ============================================================================

def screen_stocks(
    conditions: Annotated[str, "选股条件 (如 '市盈率小于20的银行股')"],
    search_type: Annotated[str, "类型: stock(默认)/fund/HK_stock/US_stock/NEEQ/index"] = "stock",
) -> str:
    """根据财务/技术指标/市场条件筛选股票。

    支持条件: 市盈率、市净率、净利润、均线、MACD、KDJ、市值、行业等。
    """
    try:
        api_key = _ensure_gs_api_key()
        url = f"{BASE_URL}/agent/mcp/smart_stock_picking"
        params = {
            "searchstring": conditions,
            "searchtype": search_type,
            "apiKey": api_key,
        }
        result = _make_request(url, params, api_key=api_key)
        return _format_json_result(result, f"智能选股: {conditions}")
    except Exception as e:
        return f"智能选股失败: {str(e)}"


# ============================================================================
# 5. 基金对比 (Fund Compare)
# ============================================================================

def compare_funds(
    fund_codes: Annotated[str, "基金代码列表，逗号分隔 (如 '000001,161039')，2-4只"],
) -> str:
    """对比场外基金的多维度业绩与风险指标。

    对比维度: 基本信息、阶段/年度/季度业绩、风险控制(最大回撤/夏普/波动率)、
    资产配置、基金经理、费率等。
    """
    try:
        api_key = _ensure_fund_cmp_key()
        codes = [c.strip() for c in fund_codes.split(",") if c.strip()]

        if len(codes) < 2:
            return "提示: 基金对比建议输入 2-4 只基金代码"

        # 逐个获取基金详情（接口支持单只）
        results: List[str] = []
        for code in codes:
            url = f"{BASE_URL}/gsfinancing/fundinfo/getfunddetail/1.0"
            params = {
                "ofcode": code,
                "apiKey": api_key,
            }
            resp = _make_request(url, params, api_key=api_key)
            if "error" not in resp:
                results.append(f"## {code}\n{json.dumps(resp, ensure_ascii=False, indent=2)}")
            else:
                results.append(f"## {code}\n错误: {resp['error']}")

        header = (
            f"# 基金对比: {', '.join(codes)}\n"
            f"# 数据来源: 国信证券\n"
            f"# 请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        return header + "\n\n".join(results)
    except Exception as e:
        return f"基金对比失败: {str(e)}"


# ============================================================================
# 6. ETF 筛选 (ETF Filter)
# ============================================================================

# ETF 专业榜单配置
_ETF_PRO_LISTS = {
    (1, 11): "热点赛道",
    (1, 13): "T+0短线突破",
    (2, 21): "高分红低波动",
    (2, 22): "能涨又能跌",
    (2, 23): "低估且优质",
    (2, 24): "低估且弹性大",
    (2, 25): "稳做绩优生",
    (3, 31): "全市场热门",
    (3, 32): "平衡资产配置",
}


def filter_etf_pro(
    class_id: Annotated[int, "榜单分类: 1-短线热榜, 2-中长期精选, 3-特色品种"],
    list_id: Annotated[int, "榜单ID: 见 SKILL.md 完整映射表"],
) -> str:
    """使用专业榜单筛选 ETF。

    示例: filter_etf_pro(2, 21) → 高分红低波动 ETF 榜单
    """
    try:
        api_key = _ensure_etf_key()
        list_name = _ETF_PRO_LISTS.get((class_id, list_id), f"榜单({class_id},{list_id})")

        url = f"{BASE_URL}/gsfinancing/selected/ETF/46.18"
        params: Dict[str, Any] = {
            "classId": class_id,
            "listId": list_id,
            "apiKey": api_key,
        }
        result = _make_request(url, params, api_key=api_key)
        return _format_json_result(result, f"ETF榜单: {list_name}")
    except Exception as e:
        return f"ETF榜单筛选失败: {str(e)}"


def filter_etf_custom(
    class1: Annotated[Optional[str], "一级类型: 1-行业, 2-宽基, 3-风格策略, 4-跨境, 5-债券, 6-黄金, 7-货币"] = None,
    endamt: Annotated[Optional[str], "规模区间(亿): 如 '10,50' 表示10-50亿"] = None,
    is_t0: Annotated[bool, "是否 T+0 交易"] = False,
    order_col: Annotated[str, "排序字段 (默认: nowrange-实时涨跌)"] = "nowrange",
    **kwargs: Any,
) -> str:
    """自定义多维条件筛选 ETF。

    支持7大维度24个指标的筛选：
    基本信息（类型/规模/年限/费率）、交易属性（T+0/两融/涨跌幅限制）、
    收益表现（净值涨跌/定投回测）、风险波动（最大回撤/夏普/波动率）、
    行情指标（成交额/溢价率）、基本面（估值/景气度/股息率）、趋势热度（人气/趋势度）。

    示例: filter_etf_custom(class1="1", endamt="10,100000", is_t0=True)
    """
    try:
        api_key = _ensure_etf_key()
        url = f"{BASE_URL}/gsfinancing/selected/ETF/46.20"
        params: Dict[str, Any] = {
            "apiKey": api_key,
            "orderCol": order_col,
            "orderType": "0",
        }
        if class1:
            params["class1"] = class1
        if endamt:
            params["endamt"] = endamt
        if is_t0:
            params["isT0"] = "1"

        # 透传其他 kwargs 参数
        for k, v in kwargs.items():
            if v is not None and v != "":
                params[k] = str(v)

        result = _make_request(url, params, api_key=api_key)
        desc = f"ETF自定义筛选: class1={class1}" if class1 else "ETF自定义筛选"
        return _format_json_result(result, desc)
    except Exception as e:
        return f"ETF自定义筛选失败: {str(e)}"
