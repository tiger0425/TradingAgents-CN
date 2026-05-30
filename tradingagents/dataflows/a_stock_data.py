"""
A股全栈数据供应商 — 基于 simonlin1212/a-stock-data

Upstream: simonlin1212/a-stock-data v3.1
Repository: https://github.com/simonlin1212/a-stock-data
Last synced: 2026-05-29

端点与上游锚点映射：
┌────────────────────────────────┬──────────────────────────────┐
│ 函数名                         │ 上游 SKILL.md 锚点             │
├────────────────────────────────┼──────────────────────────────┤
│ get_dragon_tiger_stock()       │ Layer 3.5 龙虎榜席位           │
│ get_dragon_tiger_market()      │ Layer 3.8 全市场龙虎榜          │
│ get_margin_trading()           │ Layer 4.1 融资融券明细         │
│ get_block_trade()              │ Layer 4.2 大宗交易             │
│ get_lockup_expiry()            │ Layer 3.6 限售解禁日历         │
│ get_shareholder_count()        │ Layer 4.3 股东户数变化          │
│ get_dividend_history()         │ Layer 4.4 分红送转历史         │
│ get_cls_flash()                │ Layer 5.2 财联社快讯           │
│ get_financial_statements()     │ Layer 6 新浪财报三表            │
│ get_f10_data()                 │ Layer 6 mootdx F10               │
│ get_cninfo_announcements()     │ Layer 7.1 巨潮公告             │
└────────────────────────────────┴──────────────────────────────┘

依赖:
    - requests: HTTP 库 (已在项目 pyproject.toml 中)
    - mootdx: 通达信行情接口 (可选，lazy import)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, List, Optional

import time

import pandas as pd
import requests

# ============================================================================
# Lazy import — mootdx 可选安装，不阻塞应用启动
# ============================================================================

try:
    from mootdx.quotes import Quotes
except ImportError:
    Quotes = None

# ============================================================================
# 常量与配置
# ============================================================================

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
PUSH2_URL = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
PUSH2HIS_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
STOCK_INFO_URL = "https://push2.eastmoney.com/api/qt/stock/get"

TIMEOUT = 30

# ============================================================================
# 内部辅助
# ============================================================================


def _eastmoney_datacenter(
    report_name: str,
    columns: str = "ALL",
    filter_str: str = "",
    page_size: int = 50,
    sort_columns: str = "",
    sort_types: str = "-1",
) -> List[Dict[str, Any]]:
    """直连东财 datacenter-web HTTP API 统一查询。

    参数:
        report_name: 报表名称（如 "RPT_DAILYBILLBOARD_DETAILSNEW"）
        columns: 返回字段列表，逗号分隔；默认 "ALL"
        filter_str: 过滤条件，如 '(SCODE="600519")'
        page_size: 每页条数
        sort_columns: 排序字段
        sort_types: 排序方向，"1" 升序，"-1" 降序

    返回:
        解析后的 data 列表（空列表表示无数据或请求失败）
    """
    params: Dict[str, Any] = {
        "reportName": report_name,
        "columns": columns,
        "filter": filter_str,
        "pageSize": page_size,
        "sortColumns": sort_columns,
        "sortTypes": sort_types,
        "source": "WEB",
        "client": "WEB",
    }
    try:
        resp = requests.get(
            DATACENTER_URL,
            params=params,
            headers={"User-Agent": UA},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json()
        return body.get("result", {}).get("data", [])
    except Exception:
        return []


def _format_result(data: List[Dict[str, Any]], title: str) -> str:
    """格式化查询结果为 Markdown 字符串。

    参数:
        data: 查询结果列表（每项一个 dict）
        title: 标题

    返回:
        Markdown 格式字符串
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: List[str] = [
        f"# {title}",
        "# 数据来源: a-stock-data",
        f"# 请求时间: {now}",
        "",
    ]

    if not data:
        lines.append("无数据")
        return "\n".join(lines)

    # 从第一行提取表头
    headers = list(data[0].keys())

    # Markdown 表格头
    header_row = "| " + " | ".join(str(h) for h in headers) + " |"
    separator_row = "| " + " | ".join(["---"] * len(headers)) + " |"
    lines.append(header_row)
    lines.append(separator_row)

    for row in data:
        values = []
        for h in headers:
            v = row.get(h, "")
            # 将值转为字符串，处理 None
            if v is None:
                v = ""
            elif not isinstance(v, (str, int, float)):
                v = str(v)
            values.append(str(v))
        lines.append("| " + " | ".join(values) + " |")

    return "\n".join(lines)


def _ensure_mootdx() -> None:
    """检查 mootdx 是否可用，不可用时抛出明确错误。"""
    missing = []
    if Quotes is None:
        missing.append("mootdx.quotes.Quotes（日线行情）")
    if missing:
        raise ImportError(
            f"缺少 mootdx 组件: {', '.join(missing)}。请安装:\n"
            "  pip install mootdx>=1.0.0\n\n"
            "mootdx 是通达信行情数据接口，用于获取 A 股数据。"
        )


def _load_ohlcv_mootdx(symbol: str, curr_date: str) -> pd.DataFrame:
    """使用 mootdx TCP 直连获取 A 股日线 OHLCV 数据。

    参数:
        symbol:  股票代码，如 "600519"
        curr_date: 截止日期（YYYY-MM-DD），用于防止前视偏差

    返回:
        包含 Date, Open, High, Low, Close, Volume 列的 DataFrame

    异常:
        RuntimeError: 数据获取或处理失败时抛出
    """
    _ensure_mootdx()
    try:
        client = Quotes.factory(market="std")

        # frequency=9 → 日线，start=0, offset=1200 ≈ 5年交易日
        bars = client.bars(symbol=symbol, frequency=9, start=0, offset=1200)

        if bars is None or bars.empty:
            raise ValueError(f"mootdx 未返回数据: {symbol}")

        # 列名映射：mootdx → 统一格式
        column_map = {
            "datetime": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        rename_map = {k: v for k, v in column_map.items() if k in bars.columns}
        data = bars.rename(columns=rename_map)

        # 只保留目标列
        target_cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
        data = data[[c for c in target_cols if c in data.columns]]

        # 日期转换（mootdx 返回 "20260529 09:00" 格式）
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
        data = data.dropna(subset=["Date"])

        # 价格列转数值
        price_cols = ["Open", "High", "Low", "Close", "Volume"]
        for c in price_cols:
            if c in data.columns:
                data[c] = pd.to_numeric(data[c], errors="coerce")

        # 清洗
        data = data.dropna(subset=["Close"])
        data[price_cols] = data[price_cols].ffill().bfill()

        # 防止前视偏差
        data = data[data["Date"] <= pd.Timestamp(curr_date)]

        return data
    except (ValueError, RuntimeError):
        raise
    except Exception as e:
        raise RuntimeError(f"mootdx OHLCV 数据获取失败 ({symbol}): {e}")


# ============================================================================
# 公开包装函数 — 供 interface.py route_to_vendor 调度
# ============================================================================


def get_stock_data_a(symbol: str, start_date: str, end_date: str) -> str:
    """获取 A 股日线 K 线数据（通过 mootdx TCP 直连）。

    参数:
        symbol:    股票代码，如 "600519"
        start_date: 起始日期 "YYYY-MM-DD"
        end_date:   截止日期 "YYYY-MM-DD"

    返回:
        Markdown 格式字符串，程序化行情数据
    """
    try:
        data = _load_ohlcv_mootdx(symbol, end_date)

        # 按 start_date 过滤
        data = data[data["Date"] >= pd.Timestamp(start_date)]
        data = data.sort_values("Date", ascending=False)

        # 转 dict 列表并处理日期格式
        rows = data.to_dict(orient="records")
        for row in rows:
            row["Date"] = str(row["Date"])[:10]
            for c in ("Open", "High", "Low", "Close", "Volume"):
                if c in row and row[c] is not None:
                    try:
                        row[c] = round(float(row[c]), 2)
                    except (ValueError, TypeError):
                        pass

        return _format_result(rows, f"K线数据 — {symbol}")
    except Exception as e:
        return f"行情查询失败: {str(e)}"


def get_fundamentals_a(ticker: str, curr_date: Optional[str] = None) -> str:
    """获取 A 股个股基本面信息（PE/市值/股东户数等）。

    委托给 get_stock_info（东财 push2 接口），curr_date 参数忽略。

    参数:
        ticker:    股票代码，如 "600519"
        curr_date: 忽略（腾讯财经/东财返回实时数据）

    返回:
        Markdown 格式字符串
    """
    try:
        return get_stock_info(ticker)
    except Exception as e:
        return f"基本面查询失败: {str(e)}"


def get_indicators_a(
    symbol: str,
    indicator: str,
    curr_date: str = "",
    look_back_days: int = 30,
) -> str:
    """获取 A 股技术指标（通过 mootdx + stockstats）。

    参数:
        symbol:         股票代码，如 "600519"
        indicator:      指标名，如 "rsi_14", "macd", "kdj_k", "sma_5"
        curr_date:      截止日期 "YYYY-MM-DD"，默认当天
        look_back_days: 回看天数（暂未使用，_load_ohlcv_mootdx 取约 5 年数据）

    返回:
        Markdown 格式字符串
    """
    try:
        if not curr_date:
            curr_date = datetime.now().strftime("%Y-%m-%d")

        data = _load_ohlcv_mootdx(symbol, curr_date)
        if data.empty:
            return f"指标查询失败: 未获取到 {symbol} 的行情数据"

        # stockstats 需要小写列名
        data = data.rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        data = data.sort_values("date")

        from stockstats import wrap as stockstats_wrap

        stock = stockstats_wrap(data)

        # 常用指标名 → stockstats 内部列名映射
        col_map = {
            "rsi_14": "rsi_14",
            "rsi": "rsi_14",
            "macd": "macd",
            "macd_diff": "macd_diff",
            "macd_dea": "macd_dea",
            "kdj_k": "kdjk_9_3_3",
            "kdj_d": "kdjd_9_3_3",
            "kdj_j": "kdjj_9_3_3",
            "boll_upper": "boll_upper_20_2",
            "boll_mid": "boll_mid_20_2",
            "boll_lower": "boll_lower_20_2",
            "sma_5": "close_5_sma",
            "sma_10": "close_10_sma",
            "sma_20": "close_20_sma",
            "sma_30": "close_30_sma",
        }

        col = col_map.get(indicator, indicator)

        if col not in stock.columns:
            return (
                f"指标查询失败: 不支持指标 '{indicator}'\n"
                f"可用指标: {', '.join(sorted(set(col_map.keys())))}\n"
            )

        latest_val = stock[col].iloc[-1]
        if isinstance(latest_val, (int, float)):
            val_str = f"{latest_val:.4f}"
        else:
            val_str = str(latest_val)

        return (
            f"## 技术指标 — {symbol}\n\n"
            f"- 指标: **{indicator}**\n"
            f"- 当前值: **{val_str}**\n"
            f"- 截止日期: {curr_date}"
        )
    except Exception as e:
        return f"指标查询失败: {str(e)}"


def get_current_price_a(symbol: str) -> str:
    """获取 A 股实时行情（通过腾讯财经 qt.gtimg.cn 直连）。

    腾讯财经固定字段（~分隔）：
      idx1=名称 idx3=现价 idx4=昨收 idx31=涨跌额 idx32=涨跌幅%
      idx38=换手率% idx39=PE(TTM) idx44=总市值(亿) idx46=PB
      idx47=涨停价 idx48=跌停价

    参数:
        symbol: 股票代码，如 "600519"

    返回:
        Markdown 格式字符串，包含实时行情数据
    """
    try:
        prefix = "sh" if symbol[0] in "69" else "sz"
        url = f"https://qt.gtimg.cn/q={prefix}{symbol}"
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        resp.encoding = "gbk"
        text = resp.text
        for line in text.split(";"):
            if "=" not in line:
                continue
            vals = line.split("=")[1].strip('"').split("~")
            if len(vals) < 50:
                continue
            rows = [{
                "名称": vals[1],
                "现价": vals[3],
                "昨收": vals[4],
                "涨跌额": vals[31],
                "涨跌幅%": vals[32],
                "换手率%": vals[38],
                "PE(TTM)": vals[39],
                "总市值(亿)": vals[44],
                "PB": vals[46],
                "涨停价": vals[47],
                "跌停价": vals[48],
            }]
            return _format_result(rows, f"实时行情 — {symbol}")
        return _format_result([], f"实时行情 — {symbol}")
    except Exception as e:
        return f"行情查询失败 ({symbol}): {str(e)}"


def get_balance_sheet_a(ticker: str, freq: str = "quarterly", curr_date: Optional[str] = None) -> str:
    """获取 A 股资产负债表。

    委托给 get_financial_statements(ticker, "balance")。
    freq 和 curr_date 参数忽略（新浪返回固定格式）。

    参数:
        ticker:    股票代码，如 "600519"
        freq:      忽略（保留兼容性）
        curr_date: 忽略（保留兼容性）

    返回:
        Markdown 格式字符串
    """
    try:
        return get_financial_statements(ticker, "balance")
    except Exception as e:
        return f"资产负债表查询失败 ({ticker}): {str(e)}"


def get_cashflow_a(ticker: str, freq: str = "quarterly", curr_date: Optional[str] = None) -> str:
    """获取 A 股现金流量表。

    委托给 get_financial_statements(ticker, "cashflow")。
    freq 和 curr_date 参数忽略（新浪返回固定格式）。

    参数:
        ticker:    股票代码，如 "600519"
        freq:      忽略（保留兼容性）
        curr_date: 忽略（保留兼容性）

    返回:
        Markdown 格式字符串
    """
    try:
        return get_financial_statements(ticker, "cashflow")
    except Exception as e:
        return f"现金流量表查询失败 ({ticker}): {str(e)}"


def get_income_statement_a(ticker: str, freq: str = "quarterly", curr_date: Optional[str] = None) -> str:
    """获取 A 股利润表。

    委托给 get_financial_statements(ticker, "income")。
    freq 和 curr_date 参数忽略（新浪返回固定格式）。

    参数:
        ticker:    股票代码，如 "600519"
        freq:      忽略（保留兼容性）
        curr_date: 忽略（保留兼容性）

    返回:
        Markdown 格式字符串
    """
    try:
        return get_financial_statements(ticker, "income")
    except Exception as e:
        return f"利润表查询失败 ({ticker}): {str(e)}"


def get_news_a(ticker: str, start_date: str = "", end_date: str = "") -> str:
    """获取 A 股个股相关新闻。

    委托给 get_stock_news(ticker, 10)。start_date 和 end_date 参数忽略。

    参数:
        ticker:     股票代码，如 "600519"
        start_date: 忽略（保留兼容性）
        end_date:   忽略（保留兼容性）

    返回:
        Markdown 格式字符串
    """
    try:
        return get_stock_news(ticker, 10)
    except Exception as e:
        return f"新闻查询失败 ({ticker}): {str(e)}"


def get_global_news_a(curr_date: str = "", look_back_days: int = 7, limit: int = 5) -> str:
    """获取全球财经资讯。

    委托给 get_global_news_em(limit)。curr_date 和 look_back_days 参数忽略。

    参数:
        curr_date:      忽略（保留兼容性）
        look_back_days: 忽略（保留兼容性）
        limit:          返回条数，默认 5

    返回:
        Markdown 格式字符串
    """
    try:
        return get_global_news_em(limit)
    except Exception as e:
        return f"全球资讯查询失败: {str(e)}"


# ============================================================================
# 0.5. 季报快照 — mootdx finance
# ============================================================================


def get_quarterly_snapshot(code: str) -> str:
    """查询季报快照（37 字段），使用 mootdx finance 接口。

    基于通达信财务数据库，返回最近一期季报的 EPS、ROE、净利润、主营收入等
    关键财务指标。

    参数:
        code: 股票代码，如 "600519"

    返回:
        Markdown 格式字符串，包含季报关键财务数据
        出错时返回错误描述字符串
    """
    _ensure_mootdx()
    try:
        client = Quotes.factory(market="std")
        df = client.finance(symbol=code)

        if df is None or df.empty:
            return _format_result([], f"季报快照 — {code}")

        # 选取关键字段
        key_fields = [
            "report_date",
            "基本每股收益",
            "净资产收益率",
            "净利润",
            "营业总收入(万元)",
            "净利润增长率(%)",
            "营业收入增长率(%)",
            "每股净资产",
            "每股经营现金流量",
        ]

        # 只保留实际存在的列
        available = [f for f in key_fields if f in df.columns]

        if not available:
            # 没有匹配的关键字段则返回全部列
            available = list(df.columns)

        # 取最近一期（第一行）
        rows = df[available].head(1).to_dict(orient="records")

        return _format_result(rows, f"季报快照 — {code}")
    except Exception as e:
        return f"季报查询失败 ({code}): {str(e)}"


# ============================================================================
# 0.6. F10 公司资料 — mootdx (Layer 6)
# ============================================================================


def get_f10_data(code: str, category: str = "gsjj") -> str:
    """查询个股 F10 公司资料（通达信 F10 接口）。

    基于 mootdx Quotes 的 finance 接口，获取上市公司基本面资料，
    如公司简介、主营业务、十大股东等。

    参数:
        code: 股票代码，如 "600519"
        category: F10 类别，常用值：
                  - "gsjj"  → 公司简介
                  - "zygc"  → 主营业务
                  - "gsgk"  → 公司概况
                  - "gdyg"  → 高管人员
                  - "sdgd"  → 十大股东
                  - "zcfzb" → 资产负债表
                  - "lrb"   → 利润表
                  - "xjllb" → 现金流量表

    返回:
        Markdown 格式字符串，包含 F10 公司资料数据
        出错时返回错误描述字符串
    """
    _ensure_mootdx()
    try:
        client = Quotes.factory(market="std")
        data = client.finance(code=code, name=category)

        if data is None:
            return _format_result([], f"公司资料({category}) — {code}")

        if isinstance(data, pd.DataFrame):
            if data.empty:
                return _format_result([], f"公司资料({category}) — {code}")
            rows = data.to_dict(orient="records")
        elif isinstance(data, dict):
            rows = [data]
        elif isinstance(data, list):
            rows = data
        else:
            rows = []

        return _format_result(rows, f"公司资料({category}) — {code}")
    except Exception as e:
        return f"公司资料查询失败 ({code}): {str(e)}"


# ============================================================================
# 1. 龙虎榜 — 个股席位 (Layer 3.5)
# ============================================================================


def get_dragon_tiger_stock(code: str, trade_date: str, look_back: int = 30) -> str:
    """查询个股龙虎榜上榜记录及买卖席位。"""
    try:
        start = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=look_back)).strftime("%Y-%m-%d")

        # 1. 上榜记录
        board_data = _eastmoney_datacenter(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            columns="ALL",
            filter_str=f"(TRADE_DATE>='{start}')(TRADE_DATE<='{trade_date}')(SECURITY_CODE=\"{code}\")",
            sort_columns="TRADE_DATE",
            sort_types="-1",
        )

        # 2. 买入席位 TOP5
        buy_data = _eastmoney_datacenter(
            "RPT_BILLBOARD_DAILYDETAILSBUY",
            columns="ALL",
            filter_str=f"(TRADE_DATE>='{start}')(TRADE_DATE<='{trade_date}')(SECURITY_CODE=\"{code}\")",
            sort_columns="TRADE_DATE",
            sort_types="-1",
        )

        # 3. 卖出席位 TOP5
        sell_data = _eastmoney_datacenter(
            "RPT_BILLBOARD_DAILYDETAILSSELL",
            columns="ALL",
            filter_str=f"(TRADE_DATE>='{start}')(TRADE_DATE<='{trade_date}')(SECURITY_CODE=\"{code}\")",
            sort_columns="TRADE_DATE",
            sort_types="-1",
        )

        # 4. 标记方向与机构席位 (OPERATEDEPT_CODE=="0")
        for item in buy_data:
            item["方向"] = "买入"
            item["机构席位"] = "是" if item.get("OPERATEDEPT_CODE") == "0" else "否"
        for item in sell_data:
            item["方向"] = "卖出"
            item["机构席位"] = "是" if item.get("OPERATEDEPT_CODE") == "0" else "否"

        # 5. 合并数据
        all_data = board_data + buy_data + sell_data

        return _format_result(all_data, f"龙虎榜席位 — {code}")
    except Exception as e:
        return f"龙虎榜查询失败 ({code}): {str(e)}"


# ============================================================================
# 2. 龙虎榜 — 全市场 (Layer 3.8)
# ============================================================================


def get_dragon_tiger_market(trade_date: str = "", min_net_buy: float = 0) -> str:
    """查询全市场龙虎榜。

    参数:
        trade_date: 交易日期（YYYY-MM-DD），默认当天
        min_net_buy: 最小净买入（万元），默认 0

    返回:
        Markdown 格式字符串
    """
    try:
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        raw = _eastmoney_datacenter(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            filter_str=f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')",
            page_size=500,
            sort_columns="BILLBOARD_NET_AMT",
            sort_types="-1",
        )

        # 按净买入金额过滤（万元）
        filtered = []
        for row in raw:
            net_buy = (row.get("BILLBOARD_NET_AMT") or 0) / 10000
            if net_buy >= min_net_buy:
                filtered.append(row)

        # 提取并重命名字段
        result = []
        for row in filtered:
            result.append(
                {
                    "code": row.get("SECUCODE", ""),
                    "name": row.get("SECURITY_NAME_ABBR", ""),
                    "reason": row.get("REASON", ""),
                    "close": row.get("CLOSE_PRICE", ""),
                    "change_pct": row.get("CHANGE_PCT", ""),
                    "net_buy_wan": round((row.get("BILLBOARD_NET_AMT") or 0) / 10000, 2),
                    "buy_wan": round((row.get("BUY_AMT") or 0) / 10000, 2),
                    "sell_wan": round((row.get("SELL_AMT") or 0) / 10000, 2),
                    "turnover_pct": row.get("TURNOVER_RATE", ""),
                }
            )

        title = f"全市场龙虎榜 — {trade_date}"
        return _format_result(result, title)
    except Exception as e:
        return f"全市场龙虎榜查询失败: {str(e)}"


# ============================================================================
# 3. 融资融券明细 (Layer 4.1)
# ============================================================================


def get_margin_trading(code: str, page_size: int = 30) -> str:
    """查询个股融资融券明细（日级）。"""
    try:
        data = _eastmoney_datacenter(
            "RPTA_WEB_RZRQ_GGMX",
            filter_str=f'(SCODE="{code}")',
            page_size=page_size,
            sort_columns="DATE",
            sort_types="-1",
        )
        title = f"融资融券 — {code}"
        if not data:
            return _format_result([], title)

        # 字段映射：原始KEY → 中文标签
        field_map = {
            "DATE": "日期",
            "RZYE": "融资余额(亿元)",
            "RZMRE": "融资买入(亿元)",
            "RZCHE": "融资偿还(亿元)",
            "RQYE": "融券余额(亿元)",
            "RZMCL": "融券卖出量(万股)",
            "RQCHL": "融券偿还量(万股)",
            "RZRQYE": "两融余额合计(亿元)",
        }

        # 金额字段 → 亿元；量字段 → 万股；DATE 保持原样
        yi_fields: set = {"RZYE", "RZMRE", "RZCHE", "RQYE", "RZRQYE"}
        wan_fields: set = {"RZMCL", "RQCHL"}

        rows: List[Dict[str, Any]] = []
        for row in data:
            new_row: Dict[str, Any] = {}
            for key, label in field_map.items():
                val = row.get(key, 0)
                if val is None:
                    val = 0
                if key in ("DATE",):
                    # 日期字段保持原始字符串
                    new_row[label] = str(val)
                    continue
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    val = 0.0
                if key in yi_fields:
                    val = round(val / 1e8, 2)
                elif key in wan_fields:
                    val = round(val / 1e4, 2)
                new_row[label] = val
            rows.append(new_row)

        return _format_result(rows, title)
    except Exception as e:
        return f"融资融券查询失败 ({code}): {str(e)}"


# ============================================================================
# 4. 大宗交易 (Layer 4.2)
# ============================================================================


def get_block_trade(code: str, page_size: int = 20) -> str:
    """查询个股大宗交易记录。

    参数:
        code: 股票代码，如 "600519"
        page_size: 返回条数，默认 20

    返回:
        Markdown 格式字符串
    """
    title = f"大宗交易 — {code}"
    try:
        data = _eastmoney_datacenter(
            "RPT_DATA_BLOCKTRADE",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=page_size,
            sort_columns="TRADE_DATE",
            sort_types="-1",
        )
    except Exception as e:
        return f"大宗交易查询失败 ({code}): {str(e)}"

    if not data:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return "\n".join([
            f"# {title}",
            "# 数据来源: a-stock-data",
            f"# 请求时间: {now}",
            "",
            "无数据",
        ])

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: List[str] = [
        f"# {title}",
        "# 数据来源: a-stock-data",
        f"# 请求时间: {now}",
        "",
        "| 日期 | 成交价 | 收盘价 | 溢价率(%) | 成交量(股) | 成交额(元) | 买方 | 卖方 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in data:
        trade_date = row.get("TRADE_DATE", "")
        deal_price = row.get("DEAL_PRICE", 0) or 0
        close_price = row.get("CLOSE_PRICE", 0) or 0
        if close_price:
            premium_pct = round((deal_price / close_price - 1) * 100, 2)
        else:
            premium_pct = 0.0
        deal_vol = row.get("DEAL_VOLUME", 0) or 0
        deal_amt = row.get("DEAL_AMOUNT", 0) or 0
        buyer = row.get("BUYER_NAME", "") or ""
        seller = row.get("SELLER_NAME", "") or ""

        lines.append(
            f"| {trade_date} | {deal_price} | {close_price} | {premium_pct} | {deal_vol} | {deal_amt} | {buyer} | {seller} |"
        )

    return "\n".join(lines)


# ============================================================================
# 5. 限售解禁日历 (Layer 3.6)
# ============================================================================


def get_lockup_expiry(code: str, trade_date: str, forward_days: int = 90) -> str:
    """查询限售解禁日历（历史 + 未来预警）。

    返回 Markdown 格式字符串，包含"历史解禁"和"未来待解禁"两节。
    出错时返回错误描述字符串。
    """
    try:
        # ── 历史解禁（按日期降序） ──────────────────────────────────────
        history = _eastmoney_datacenter(
            "RPT_LIFT_STAGE",
            filter_str=f'(SECURITY_CODE="{code}")',
            sort_columns="FREE_DATE",
            sort_types="-1",
        )

        # ── 未来待解禁（计算截止日期，按日期升序） ─────────────────────
        trade_dt = datetime.strptime(trade_date, "%Y-%m-%d")
        end_date = trade_dt + timedelta(days=forward_days)
        end_str = end_date.strftime("%Y-%m-%d")

        future = _eastmoney_datacenter(
            "RPT_LIFT_STAGE",
            filter_str=(
                f'(SECURITY_CODE="{code}")'
                f'(FREE_DATE>="{trade_date}")'
                f'(FREE_DATE<="{end_str}")'
            ),
            sort_columns="FREE_DATE",
            sort_types="1",
        )

        lines: List[str] = [f"# 限售解禁 — {code}", ""]

    # ── 历史解禁表格 ────────────────────────────────────────────
        lines.append("## 历史解禁")
        _append_table(lines, history, [
            "FREE_DATE", "FREE_SHARES_TYPE", "FREE_SHARES", "FREE_RATIO",
        ], "无历史解禁记录")

        lines.append("")

        # ── 未来待解禁表格 ──────────────────────────────────────────
        lines.append(f"## 未来{forward_days}天待解禁")
        _append_table(lines, future, [
            "FREE_DATE", "FREE_SHARES_TYPE", "FREE_SHARES", "FREE_RATIO",
        ], "无待解禁记录")

        return "\n".join(lines)

    except Exception as e:
        return f"限售解禁查询失败 ({code}): {str(e)}"


def _append_table(
    lines: List[str],
    data: List[Dict[str, Any]],
    headers: List[str],
    empty_msg: str = "无数据",
) -> None:
    """向 lines 中追加一个 Markdown 表格（或空提示）。"""
    if not data:
        lines.append(empty_msg)
        return

    header_row = "| " + " | ".join(headers) + " |"
    sep_row = "| " + " | ".join(["---"] * len(headers)) + " |"
    lines.append(header_row)
    lines.append(sep_row)
    for row in data:
        vals = []
        for h in headers:
            v = row.get(h, "")
            if v is None:
                v = ""
            elif not isinstance(v, (str, int, float)):
                v = str(v)
            vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")


# ============================================================================
# 6. 股东户数变化 (Layer 4.3)
# ============================================================================


def get_shareholder_count(code: str, page_size: int = 10) -> str:
    """查询股东户数变化趋势。

    返回 Markdown 格式字符串，包含每季度股东户数、环比变化、户均持股及筹码集中度。
    环比下降标注"筹码集中"，环比上升标注"筹码分散"。
    出错时返回错误描述字符串。

    参数:
        code: 股票代码
        page_size: 返回期数，默认 10
    """
    try:
        raw = _eastmoney_datacenter(
            "RPT_HOLDERNUMLATEST",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=page_size,
            sort_columns="END_DATE",
            sort_types="-1",
        )

        if not raw:
            return _format_result([], f"股东户数变化 — {code}")

        rows: List[Dict[str, Any]] = []
        for row in raw:
            end_date = row.get("END_DATE", "")
            holder_num = row.get("HOLDER_NUM", 0)
            change_ratio = row.get("HOLDER_NUM_RATIO", "")
            avg_shares = row.get("AVG_HOLD_NUM", 0)

            if holder_num is None:
                continue

            try:
                current = float(holder_num)
            except (ValueError, TypeError):
                continue

            # 环比变化：API 直接返回 HOLDER_NUM_RATIO（负值 = 筹码集中）
            if change_ratio is not None and change_ratio != "":
                try:
                    change_ratio_f = float(change_ratio)
                    change_pct = round(change_ratio_f, 2)
                    change_pct_str = f"{change_pct:.2f}%"
                    # 注意：东财正数 = 增加 = 筹码分散，负数 = 减少 = 筹码集中
                    label = "筹码集中" if change_ratio_f < 0 else "筹码分散"
                except (ValueError, TypeError):
                    change_pct_str = "—"
                    label = "—"
            else:
                change_pct_str = "—"
                label = "—"

            # 户均持股
            if avg_shares is not None and avg_shares != "":
                try:
                    avg_shares_f = float(avg_shares)
                    if avg_shares_f >= 1e4:
                        avg_str = f"{avg_shares_f / 1e4:.2f}万"
                    else:
                        avg_str = f"{avg_shares_f:,.0f}"
                except (ValueError, TypeError):
                    avg_str = "—"
            else:
                avg_str = "—"

            # 日期只取前10位 YYYY-MM-DD
            end_date_short = str(end_date)[:10]

            rows.append({
                "截止日期": end_date_short,
                "股东户数": f"{current:,.0f}",
                "环比变化": change_pct_str,
                "户均持股": avg_str,
                "筹码集中度": label,
            })

        return _format_result(rows, f"股东户数变化 — {code}")
    except Exception as e:
        return f"股东户数查询失败 ({code}): {str(e)}"


# ============================================================================
# 7. 分红送转历史 (Layer 4.4)
# ============================================================================


def get_dividend_history(code: str, page_size: int = 30) -> str:
    """查询分红送转历史。

    参数:
        code: 股票代码，如 "600519"
        page_size: 返回条数，默认 30

    返回:
        Markdown 格式字符串，包含报告期、每股派息、送股、转增、进度状态。
        出错时返回错误描述字符串。
    """
    try:
        data = _eastmoney_datacenter(
            "RPT_F10_FINANCE_BONUS",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=page_size,
            sort_columns="REPORT_DATE",
            sort_types="-1",
        )

        if not data:
            return _format_result([], f"分红送转 — {code}")

        rows: List[Dict[str, Any]] = []
        for row in data:
            new_row = {
                "报告期": row.get("REPORT_DATE", ""),
                "每股派息": row.get("BONUS_EPS", ""),
                "送股": row.get("BONUS_SEND", ""),
                "转增": row.get("BONUS_TRANSFER", ""),
                "进度状态": row.get("BONUS_STATUS", ""),
            }
            rows.append(new_row)

        return _format_result(rows, f"分红送转 — {code}")
    except Exception as e:
        return f"分红送转查询失败 ({code}): {str(e)}"


# ============================================================================
# 7.5. 新浪财报三表 (Layer 6)
# ============================================================================


def get_financial_statements(code: str, report_type: str = "balance") -> str:
    """查询新浪财报三表（资产负债表/利润表/现金流量表）。

    直连新浪财经 JSONP API，零第三方依赖。
    自动识别沪市（sh）和深市（sz）前缀。
    返回最近 5 期财务数据。

    参数:
        code: 股票代码，如 "600519"
        report_type: 报表类型
                     - "balance"   → 资产负债表 (BalanceSheet)
                     - "income"    → 利润表 (ProfitStatement)
                     - "cashflow"  → 现金流量表 (CashFlow)

    返回:
        Markdown 格式字符串，包含最近 5 期财务数据
        出错时返回错误描述字符串
    """
    # ── Sina symbol 前缀 ────────────────────────────────────────────
    sina_sym = f"sh{code}" if code.startswith("6") else f"sz{code}"

    # ── report_type 映射 ────────────────────────────────────────────
    endpoint_map: Dict[str, str] = {
        "balance": "BalanceSheet",
        "income": "ProfitStatement",
        "cashflow": "CashFlow",
    }
    type_name_map: Dict[str, str] = {
        "balance": "资产负债表",
        "income": "利润表",
        "cashflow": "现金流量表",
    }

    if report_type not in endpoint_map:
        return (
            f"财报查询失败: 不支持的报表类型 '{report_type}'"
            f"，可选 balance(资产负债表)/income(利润表)/cashflow(现金流量表)"
        )

    endpoint = endpoint_map[report_type]
    type_name = type_name_map[report_type]

    url = (
        f"https://quotes.sina.cn/cn/api/jsonp_v2.php/data"
        f"/CN_{endpoint}Service.get{endpoint}Data"
    )
    params: Dict[str, Any] = {
        "symbol": sina_sym,
        "type": "0",
        "page": "1",
        "num": "5",
    }
    headers: Dict[str, str] = {
        "User-Agent": UA,
        "Referer": "https://finance.sina.com.cn/",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()

        # ── 解析 JSONP 响应 ──────────────────────────────────────
        # 格式: try{ jsonpCallback({...}); }catch(e){}
        text = resp.text.strip()
        start = text.find("(")
        end = text.rfind(")")
        if start >= 0 and end > start:
            json_str = text[start + 1 : end]
        else:
            json_str = text

        body = json.loads(json_str)

        # ── 提取数据 ──────────────────────────────────────────────
        # 新浪返回多种格式：直接数组、{result:{data:[...]}}、{data:[...]}
        result_data: Any = body
        if isinstance(body, dict):
            for key in ("result", "data"):
                candidate = body.get(key)
                if candidate is not None:
                    result_data = candidate
                    if isinstance(candidate, dict):
                        inner = candidate.get("data") or candidate.get("result")
                        if inner is not None:
                            result_data = inner
                    break

        if isinstance(result_data, dict):
            result_data = [result_data]
        elif not isinstance(result_data, list):
            return _format_result([], f"财务报表({type_name}) — {code}")

        # 取前 5 条
        rows = result_data[:5]

        return _format_result(rows, f"财务报表({type_name}) — {code}")
    except Exception as e:
        return f"财报查询失败 ({code}): {str(e)}"


# ============================================================================
# 8. 财联社快讯 (Layer 5.2)
# ============================================================================


def _cls_sign(params: Dict[str, Any]) -> str:
    """财联社 API 签名：参数排序 → key=value&... → SHA1(hex) → MD5(hex)。"""
    keys = sorted(params.keys())
    param_str = "&".join(f"{k}={params[k]}" for k in keys)
    sha1 = hashlib.sha1(param_str.encode("utf-8")).hexdigest()
    return hashlib.md5(sha1.encode("utf-8")).hexdigest()


def get_cls_flash(count: int = 20) -> str:
    """查询财联社实时快讯。

    直连财联社 /v1/roll/get_roll_list 接口，参数排序后经 SHA1+MD5 双重签名认证。
    返回标题、时间（北京时间）、内容摘要。

    参数:
        count: 返回条数，默认 20

    返回:
        Markdown 格式快讯内容，出错时返回错误字符串
    """
    headers = {
        "User-Agent": UA,
        "Host": "www.cls.cn",
        "Referer": "https://www.cls.cn/telegraph",
    }
    try:
        last_time = int(datetime.now().timestamp())
        params: Dict[str, Any] = {
            "app": "CailianpressWeb",
            "category": "",
            "last_time": last_time,
            "os": "web",
            "refresh_type": 1,
            "rn": min(count, 100),
            "sv": "8.7.9",
        }
        params["sign"] = _cls_sign(params)
        url = "https://www.cls.cn/v1/roll/get_roll_list"

        resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", {}).get("roll_data", [])[:count]
        rows: List[Dict[str, Any]] = []
        for item in data:
            ctime = item.get("ctime", 0)
            if ctime:
                try:
                    ts = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    ts = str(ctime)
            else:
                ts = "未知时间"
            title = item.get("title", "").strip()
            content = (item.get("content", "") or "")[:60]
            rows.append({"title": title, "时间": ts, "content": content})
        return _format_result(rows, "财联社快讯")
    except Exception as e:
        return f"财联社快讯查询失败: {str(e)}"


# ============================================================================
# 9. 巨潮公告 (Layer 7.1)
# ============================================================================


def get_cninfo_announcements(code: str, page_size: int = 20) -> str:
    """查询巨潮公告。

    直连巨潮 cninfo 历史公告查询 API，返回公告标题、发布时间、PDF链接。

    参数:
        code: 股票代码，如 "600519"
        page_size: 每页条数，默认 20

    返回:
        Markdown 格式字符串，包含公告标题、时间、PDF 链接。
        出错时返回错误描述字符串。
    """
    try:
        # 推导 orgId：上证 gssh0{code}，深证/创业板 gssz0{code}
        if code.startswith("6"):
            org_id = f"gssh0{code}"
        else:
            org_id = f"gssz0{code}"

        url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
        headers = {
            "User-Agent": UA,
            "Referer": "http://www.cninfo.com.cn/",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }
        payload = {
            "pageNum": "1",
            "pageSize": str(page_size),
            "column": "szse",
            "tabName": "fulltext",
            "stock": f"{code},{org_id}",
        }
        resp = requests.post(url, headers=headers, data=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        body = resp.json()

        announcements = body.get("announcements", [])
        rows: List[Dict[str, Any]] = []
        for item in announcements:
            # 时间戳（毫秒）→ 可读日期
            ts = item.get("announcementTime")
            if ts:
                time_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
            else:
                time_str = ""

            # 构造 PDF 详情页链接
            ann_id = item.get("announcementId", "")
            pdf_url = (
                f"https://www.cninfo.com.cn/new/disclosure/detail"
                f"?stockCode={code}&announcementId={ann_id}"
            )

            rows.append({
                "announcementTitle": item.get("announcementTitle", ""),
                "announcementTime": time_str,
                "secName": item.get("secName", ""),
                "adjunctUrl": pdf_url,
            })

        return _format_result(rows, f"巨潮公告 — {code}")
    except Exception as e:
        return f"巨潮公告查询失败 ({code}): {str(e)}"


# ============================================================================
# 10. 概念板块 (Layer 3.3)
# ============================================================================


def get_concept_blocks(code: str) -> str:
    """查询个股关联的概念板块、行业板块和地域板块。

    直连百度股市通 PAE API，返回板块名称、涨跌幅和描述。

    参数:
        code: 股票代码，如 "600519"

    返回:
        Markdown 格式字符串，包含板块分类、名称、涨跌幅和描述

    数据源:
        https://finance.pae.baidu.com/api/getrelatedblock
    """
    url = "https://finance.pae.baidu.com/api/getrelatedblock"
    params = {
        "code": code,
        "market": "ab",
        "typeCode": "all",
        "finClientType": "pc",
    }
    headers = {
        "User-Agent": UA,
        "Host": "finance.pae.baidu.com",
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        d = resp.json()

        if str(d.get("ResultCode", -1)) != "0":
            raise ValueError(f"API 返回异常 ResultCode: {d.get('ResultCode')}")

        result = d.get("Result", [])
        if not result:
            return _format_result([], f"概念板块 — {code}")

        # 类型映射
        type_map = {
            "industry": "行业",
            "concept": "概念",
            "region": "地域",
        }

        rows: List[Dict[str, Any]] = []
        for item in result:
            raw_type = item.get("type", "")
            rows.append({
                "分类": type_map.get(raw_type, raw_type),
                "名称": item.get("name", ""),
                "涨跌幅": item.get("increase", ""),
                "描述": item.get("desc", ""),
            })

        return _format_result(rows, f"概念板块 — {code}")
    except Exception as e:
        return f"概念板块查询失败 ({code}): {str(e)}"


# ============================================================================
# 10. 强势股题材归因 — 同花顺热点 (Layer 3.1)
# ============================================================================


def get_hot_stock_reasons(date: str = "") -> str:
    """查询同花顺强势股题材归因。

    直连同花顺热点 API，获取当日强势股及其题材标签（如 "算力租赁+AI"）。

    参数:
        date: 日期（YYYY-MM-DD），默认当天

    返回:
        Markdown 格式字符串，包含 code/name/reason/zhangfu/huanshou/chengjiaoe
        出错时返回错误描述字符串
    """
    try:
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        url = (
            "http://zx.10jqka.com.cn/event/api/getharden"
            f"/date/{date}/orderby/date/orderway/desc/charset/GBK/"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                " Chrome/117.0.0.0 Safari/537.36"
            ),
        }

        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        body = resp.json()

        if body.get("errocode") != 0:
            return (
                f"同花顺热点查询失败: API 返回错误码 {body.get('errocode')}"
            )

        raw_data = body.get("data", [])
        rows = []
        for item in raw_data:
            rows.append({
                "code": item.get("code", ""),
                "name": item.get("name", ""),
                "reason": item.get("reason", ""),
                "date": item.get("date", ""),
            })

        title = f"强势股题材归因 — {date}"
        return _format_result(rows, title)
    except Exception as e:
        return f"同花顺热点查询失败: {str(e)}"


# ============================================================================
# 11. 个股资金流向（分钟级）— 东财 push2
# ============================================================================


def get_fund_flow_minute(code: str) -> str:
    """查询个股资金流向（分钟级）。

    直连东财 push2 接口，返回每分钟的主力净流入/出、小单、中单、大单、超大单资金流向。
    金额单位为 **元**。

    参数:
        code: 股票代码，如 "600519"

    返回:
        Markdown 格式字符串，包含每分钟资金流向数据
    """
    try:
        # 上证 1.{code}，深证 0.{code}
        secid = f"1.{code}" if code.startswith("6") else f"0.{code}"

        params: Dict[str, Any] = {
            "secid": secid,
            "klt": 1,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57",
        }
        headers = {
            "User-Agent": UA,
            "Referer": "https://quote.eastmoney.com/",
        }

        resp = requests.get(PUSH2_URL, params=params, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        body = resp.json()

        data = body.get("data", {})
        kline = data.get("klines", [])

        if not kline:
            return _format_result([], f"个股资金流向 — {code}")

        rows: List[Dict[str, Any]] = []
        for line in kline:
            parts = line.split(",")
            if len(parts) >= 6:
                rows.append({
                    "时间": parts[0],               # f51
                    "主力净流入": parts[1],          # f52
                    "小单净流入": parts[2],          # f53
                    "中单净流入": parts[3],          # f54
                    "大单净流入": parts[4],          # f55
                    "超大单净流入": parts[5],        # f56
                })

        return _format_result(rows, f"个股资金流向 — {code}")
    except Exception as e:
        return f"资金流向查询失败 ({code}): {str(e)}"


def get_fund_flow_120d(code: str) -> str:
    """查询个股 120 日资金流向。

    直连东财 push2his 接口，返回每日主力净流入/出、小单、中单、大单、超大单资金流向。
    金额单位为 **元**。

    参数:
        code: 股票代码，如 "600519"

    返回:
        Markdown 格式字符串，包含每日资金流向数据
    """
    try:
        # 上证 1.{code}，深证 0.{code}
        secid = f"1.{code}" if code.startswith("6") else f"0.{code}"

        params: Dict[str, Any] = {
            "secid": secid,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57",
            "klt": 101,
            "lmt": 120,
        }
        headers = {
            "User-Agent": UA,
            "Referer": "https://quote.eastmoney.com/",
        }

        resp = requests.get(PUSH2HIS_URL, params=params, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        body = resp.json()

        data = body.get("data", {})
        kline = data.get("klines", [])

        if not kline:
            return _format_result([], f"120日资金流向 — {code}")

        rows: List[Dict[str, Any]] = []
        for line in kline:
            parts = line.split(",")
            if len(parts) >= 6:
                rows.append({
                    "时间": parts[0],               # f51
                    "主力净流入": parts[1],          # f52
                    "小单净流入": parts[2],          # f53
                    "中单净流入": parts[3],          # f54
                    "大单净流入": parts[4],          # f55
                    "超大单净流入": parts[5],        # f56
                })

        return _format_result(rows, f"120日资金流向 — {code}")
    except Exception as e:
        return f"120日资金流向查询失败 ({code}): {str(e)}"


# ============================================================================
# 11. 个股新闻 — 东财搜索
# ============================================================================


def get_stock_news(code: str, page_size: int = 10) -> str:
    """查询个股相关新闻。

    直连东财搜索 API，获取个股相关新闻列表。

    参数:
        code: 股票代码，如 "600519"
        page_size: 返回条数，默认 10

    返回:
        Markdown 格式字符串，包含新闻标题、日期、摘要。
        出错时返回错误描述字符串。
    """
    try:
        url = "https://search-api-web.eastmoney.com/search/jsonp"
        params = {
            "cb": "jQuery",
            "param": json.dumps(
                {
                    "uid": "",
                    "keyword": code,
                    "type": ["8192"],
                    "client": "web",
                    "clientType": "web",
                    "pageSize": page_size,
                    "pageNo": 1,
                },
                ensure_ascii=False,
            ),
        }
        headers = {
            "User-Agent": UA,
            "Referer": "https://quote.eastmoney.com/",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()

        # 解析 JSONP 响应：jQuery(...)
        text = resp.text.strip()
        start = text.find("(")
        if start >= 0 and text.endswith(")"):
            json_str = text[start + 1 : -1]
        else:
            json_str = text
        d = json.loads(json_str)

        data = d.get("result", {}).get("data", [])
        rows: List[Dict[str, Any]] = []
        for item in data:
            title = item.get("title", "").strip()
            date = item.get("date", item.get("showDate", ""))
            content = (item.get("content", "") or "")[:80]
            rows.append({
                "标题": title,
                "日期": date,
                "摘要": content,
            })

        return _format_result(rows, f"个股新闻 — {code}")
    except Exception as e:
        return f"新闻查询失败 ({code}): {str(e)}"


# ============================================================================
# 12. 全球财经资讯 — 东财全球资讯
# ============================================================================


def get_global_news_em(count: int = 10) -> str:
    """查询东财全球财经资讯。

    直连东财 np-weblist 快讯接口，获取全球财经资讯列表。
    需要 req_trace UUID 参数（V3.1 新增必填项）。

    参数:
        count: 返回条数，默认 10

    返回:
        Markdown 格式字符串，包含资讯标题、时间、内容摘要。
        出错时返回错误描述字符串。
    """
    url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
    params = {
        "client": "web",
        "bizCode": "000",
        "fastColumn": "102",
        "sortEnd": "",
        "pageIndex": "1",
        "pageSize": str(count),
        "req_trace": uuid.uuid4().hex,
    }
    headers = {
        "User-Agent": UA,
        "Referer": "https://np-weblist.eastmoney.com/",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        d = resp.json()
        data = d.get("data", {}).get("fastNewsList", [])[:count]
        rows: List[Dict[str, Any]] = []
        for item in data:
            title = item.get("title", "").strip()
            show_time = item.get("showTime", "")
            content = (item.get("content", "") or "")[:80]
            rows.append({
                "标题": title,
                "时间": show_time,
                "摘要": content,
            })
        return _format_result(rows, "全球财经资讯")
    except Exception as e:
        return f"全球资讯查询失败: {str(e)}"


# ============================================================================
# 13. 百度K线 — MA5/MA10/MA20 (Layer 1.3)
# ============================================================================


def get_baidu_kline_ma(code: str, count: int = 20) -> str:
    """查询百度股市通 K 线数据（自带 MA5/MA10/MA20）。

    直连百度股市通 selfselect/getstockquotation API，返回 K 线及均线指标。
    数据含 MA5/MA10/MA20 均价字段。

    参数:
        code: 股票代码，如 "600519"
        count: 返回 K 线条数，默认 20

    返回:
        Markdown 格式字符串，包含 K 线时间、价格及均线数据
    """
    url = "https://finance.pae.baidu.com/selfselect/getstockquotation"
    params: Dict[str, Any] = {
        "all": "1",
        "isIndex": "false",
        "isStock": "true",
        "newFormat": "1",
        "group": "quotation_kline_ab",
        "finClientType": "pc",
        "code": code,
        "ktype": "1",
    }
    headers = {
        "User-Agent": UA,
        "Host": "finance.pae.baidu.com",
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        d = resp.json()

        market_data = d.get("Result", {}).get("newMarketData", {})
        keys = market_data.get("keys", [])
        raw_data = market_data.get("marketData", "")

        if not keys or not raw_data:
            return _format_result([], f"百度K线 — {code}")

        rows: List[Dict[str, Any]] = []
        lines = raw_data.strip().split(";")

        for line in lines[-count:]:
            if not line.strip():
                continue
            parts = line.strip().split(",")
            if len(parts) != len(keys):
                continue
            row: Dict[str, Any] = {}
            for i, key in enumerate(keys):
                row[key] = parts[i]
            rows.append(row)

        return _format_result(rows, f"百度K线 — {code}")
    except Exception as e:
        return f"K线查询失败 ({code}): {str(e)}"


# ============================================================================
# 12. 个股基础信息 — 东财 push2
# ============================================================================


def get_stock_info(code: str) -> str:
    """查询个股基础信息（通过腾讯财经）。

    委托给 get_current_price_a，返回名称、现价、昨收、涨跌额/幅、
    换手率、PE(TTM)、PB 等字段。

    参数:
        code: 股票代码，如 "600519"

    返回:
        Markdown 格式字符串，包含个股基础信息
    """
    return get_current_price_a(code)


# ============================================================================
# 13. 个股研报 — 东财 reportapi
# ============================================================================


def get_research_reports(code: str, max_pages: int = 3) -> str:
    """查询个股研报。

    直连东财 reportapi，获取个股研究报告列表，支持翻页。

    参数:
        code: 股票代码，如 "600519"
        max_pages: 最大翻页数，默认 3

    返回:
        Markdown 格式字符串，包含研报标题、日期、机构、评级、盈利预测。
        出错时返回错误描述字符串。
    """
    try:
        url = "https://reportapi.eastmoney.com/report/list"
        headers = {
            "User-Agent": UA,
            "Referer": "https://data.eastmoney.com/",
        }
        rows: List[Dict[str, Any]] = []

        for page_no in range(1, max_pages + 1):
            params: Dict[str, Any] = {
                "industryCode": "*",
                "pageSize": 50,
                "beginTime": "2000-01-01",
                "endTime": "2030-01-01",
                "pageNo": page_no,
                "qType": 0,
                "code": code,
            }

            resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            body = resp.json()

            data = body.get("data", [])
            if not data:
                break

            for item in data:
                rows.append({
                    "title": item.get("title", ""),
                    "publishDate": item.get("publishDate", ""),
                    "orgSName": item.get("orgSName", ""),
                    "predictThisYearEps": item.get("predictThisYearEps", ""),
                    "predictNextYearEps": item.get("predictNextYearEps", ""),
                    "emRatingName": item.get("emRatingName", ""),
                })

            if page_no < max_pages:
                time.sleep(0.3)

        return _format_result(rows, f"研报列表 — {code}")
    except Exception as e:
        return f"研报查询失败 ({code}): {str(e)}"


# ============================================================================
# 13. 机构一致预期 EPS — 同花顺 (Layer 2.2)
# ============================================================================


def get_consensus_eps(code: str) -> str:
    """查询同花顺机构一致预期 EPS。

    直连同花顺 worth 页面，爬取 HTML 表格提取机构预测 EPS（每股收益）均值数据。

    参数:
        code: 股票代码，如 "600519"

    返回:
        Markdown 格式字符串，包含一致预期 EPS 数据
        出错时返回错误描述字符串
    """
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": UA,
        "Referer": "https://basic.10jqka.com.cn/",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.encoding = "gbk"
        tables = pd.read_html(StringIO(resp.text))

        # 寻找包含"每股收益"或"均值"的表格
        target_df = None
        for df in tables:
            col_str = " ".join(str(c) for c in df.columns)
            if "每股收益" in col_str or "均值" in col_str:
                target_df = df
                break

        if target_df is None:
            return _format_result([], f"机构一致预期EPS — {code}")

        # 转为 dict 列表
        rows: List[Dict[str, Any]] = []
        for _, row in target_df.iterrows():
            entry: Dict[str, Any] = {}
            for col in target_df.columns:
                entry[str(col)] = row[col]
            rows.append(entry)

        return _format_result(rows, f"机构一致预期EPS — {code}")
    except Exception as e:
        return f"一致预期查询失败 ({code}): {str(e)}"


# ============================================================================
# 模块导出
# ============================================================================

__all__ = [
    "get_quarterly_snapshot",
    "get_f10_data",
    "get_dragon_tiger_stock",
    "get_dragon_tiger_market",
    "get_margin_trading",
    "get_block_trade",
    "get_lockup_expiry",
    "get_shareholder_count",
    "get_dividend_history",
    "get_financial_statements",
    "get_concept_blocks",
    "get_hot_stock_reasons",
    "get_cls_flash",
    "get_cninfo_announcements",
    "get_stock_info",
    "get_stock_news",
    "get_global_news_em",
    "get_baidu_kline_ma",
    "get_fund_flow_120d",
    # 公开包装函数 — 供 interface.py 路由
    "get_stock_data_a",
    "get_fundamentals_a",
    "get_indicators_a",
    "get_current_price_a",
    "get_balance_sheet_a",
    "get_cashflow_a",
    "get_income_statement_a",
    "get_news_a",
    "get_global_news_a",
]
