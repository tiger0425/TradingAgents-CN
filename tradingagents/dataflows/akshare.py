"""
AKShare data vendor module for TradingAgents.
Provides A-share (China stock market) data through the akshare library.
All functions return str type for compatibility with the TradingAgents tool system.

Dependencies:
    - akshare: A-share financial data interface
    - stockstats: Technical indicator calculation (via wrap)
    - pandas: DataFrame manipulation
"""

from typing import Annotated
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
import os
import time
import requests

from .config import get_config

# ---------------------------------------------------------------------------
# Lazy import guard — akshare is large and may not be installed everywhere
# ---------------------------------------------------------------------------
try:
    import akshare as ak
except ImportError:
    ak = None

# stockstats is a required dependency for technical indicator calculations
from stockstats import wrap


# ============================================================================
# Internal helpers
# ============================================================================

def _ensure_akshare():
    """Raise a user-friendly error if akshare is not installed."""
    if ak is None:
        raise ImportError(
            "akshare is not installed. Please install it with: pip install akshare"
        )


def _ak_date(date_str: str) -> str:
    """Convert 'yyyy-mm-dd' to akshare's expected 'yyyymmdd' format."""
    return date_str.replace("-", "")


def _to_date(date_str: str) -> datetime:
    """Parse 'yyyy-mm-dd' to datetime."""
    return datetime.strptime(date_str, "%Y-%m-%d")


def _to_sina_symbol(symbol: str) -> str:
    """Convert 6-digit A-share code to Sina format with sh/sz prefix.

    Shanghai (SSE) stocks start with '6', ETFs start with '5' → sh{symbol}
    Shenzhen (SZSE) stocks start with '0' or '3', ETFs start with '15/16' → sz{symbol}
    Beijing (BSE) stocks start with '8' → bj{symbol}
    """
    symbol = symbol.strip()
    if not (len(symbol) == 6 and symbol.isdigit()):
        raise ValueError(
            f"Invalid A-share symbol: '{symbol}'. Expected 6-digit numeric code."
        )
    first = symbol[0]
    if first in ("5", "6"):
        return f"sh{symbol}"
    elif first in ("0", "1", "2", "3"):
        return f"sz{symbol}"
    elif first == "8":
        return f"bj{symbol}"
    elif first == "4":
        return f"sh{symbol}"  # 老三板
    else:
        raise ValueError(
            f"Unknown exchange for symbol: '{symbol}'. "
            f"First digit must be 5/6 (SSE), 0/1/2/3 (SZSE), or 8 (BSE)."
        )


def _load_ohlcv_akshare(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch and cache A-share OHLCV data for stockstats consumption.

    Downloads ~5 years of daily data up to curr_date, caches per symbol,
    and filters out rows after curr_date to prevent look-ahead bias.
    Returns a DataFrame with columns: Date, Open, High, Low, Close, Volume.

    Note: data source switched from akshare (Sina) to mootdx (TCP direct).
    """
    from tradingagents.dataflows.a_stock_data import _load_ohlcv_mootdx
    config = get_config()

    curr_dt = _to_date(curr_date)
    today = datetime.now()
    start_dt = today - relativedelta(years=5)

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    cache_file = os.path.join(
        config["data_cache_dir"],
        f"{symbol}-mootdx-{start_str}-{end_str}.csv",
    )

    if os.path.exists(cache_file):
        data = pd.read_csv(cache_file, on_bad_lines="skip", encoding="utf-8")
    else:
        raw = _load_ohlcv_mootdx(symbol, curr_date)
        if raw is None or raw.empty:
            raise ValueError(f"No OHLCV data returned for {symbol}")
        raw.to_csv(cache_file, index=False, encoding="utf-8")
        data = raw

    # Clean and normalise for stockstats (second pass)
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])

    price_cols = ["Open", "High", "Low", "Close", "Volume"]
    for c in price_cols:
        if c in data.columns:
            data[c] = pd.to_numeric(data[c], errors="coerce")
    data = data.dropna(subset=["Close"])
    data[price_cols] = data[price_cols].ffill().bfill()

    # Prevent look-ahead bias
    data = data[data["Date"] <= pd.Timestamp(curr_date)]

    return data


# ============================================================================
# 1. Core Stock Data — OHLCV
# ============================================================================

def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company (6-digit A-share code)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve A-share OHLCV historical price data via akshare (Sina source).

    Returns CSV-formatted string with header comment lines.
    """
    try:
        _ensure_akshare()
        sina_symbol = _to_sina_symbol(symbol)

        df = ak.stock_zh_a_daily(
            symbol=sina_symbol,
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )

        if df is None or df.empty:
            return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

        # Sina source returns English lowercase column names
        df = df.rename(
            columns={
                "date": "Date",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            }
        )

        # Keep only OHLCV columns
        cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
        df = df[[c for c in cols if c in df.columns]]

        # Round price columns
        for col in ["Open", "High", "Low", "Close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(2)

        csv_string = df.to_csv(index=False)

        header = f"# Stock data for {symbol} from {start_date} to {end_date}\n"
        header += f"# Total records: {len(df)}\n"
        header += f"# Data source: akshare (Sina, forward-adjusted)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except ImportError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error fetching data for {symbol}: {str(e)}"


# ============================================================================
# 2. Technical Indicators
# ============================================================================

# Indicator descriptions — same semantics as yfinance best_ind_params
_INDICATOR_DESCRIPTIONS = {
    "close_50_sma": (
        "50 SMA: A medium-term trend indicator. "
        "Usage: Identify trend direction and serve as dynamic support/resistance. "
        "Tips: It lags price; combine with faster indicators for timely signals."
    ),
    "close_200_sma": (
        "200 SMA: A long-term trend benchmark. "
        "Usage: Confirm overall market trend and identify golden/death cross setups. "
        "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
    ),
    "close_10_ema": (
        "10 EMA: A responsive short-term average. "
        "Usage: Capture quick shifts in momentum and potential entry points. "
        "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
    ),
    "macd": (
        "MACD: Computes momentum via differences of EMAs. "
        "Usage: Look for crossovers and divergence as signals of trend changes. "
        "Tips: Confirm with other indicators in low-volatility or sideways markets."
    ),
    "macds": (
        "MACD Signal: An EMA smoothing of the MACD line. "
        "Usage: Use crossovers with the MACD line to trigger trades. "
        "Tips: Should be part of a broader strategy to avoid false positives."
    ),
    "macdh": (
        "MACD Histogram: Shows the gap between the MACD line and its signal. "
        "Usage: Visualize momentum strength and spot divergence early. "
        "Tips: Can be volatile; complement with additional filters in fast-moving markets."
    ),
    "rsi": (
        "RSI: Measures momentum to flag overbought/oversold conditions. "
        "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
        "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
    ),
    "boll": (
        "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
        "Usage: Acts as a dynamic benchmark for price movement. "
        "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
    ),
    "boll_ub": (
        "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
        "Usage: Signals potential overbought conditions and breakout zones. "
        "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
    ),
    "boll_lb": (
        "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
        "Usage: Indicates potential oversold conditions. "
        "Tips: Use additional analysis to avoid false reversal signals."
    ),
    "atr": (
        "ATR: Averages true range to measure volatility. "
        "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
        "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
    ),
    "vwma": (
        "VWMA: A moving average weighted by volume. "
        "Usage: Confirm trends by integrating price action with volume data. "
        "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
    ),
    "mfi": (
        "MFI: The Money Flow Index is a momentum indicator that uses both price and volume "
        "to measure buying and selling pressure. "
        "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength "
        "of trends or reversals. "
        "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI "
        "can indicate potential reversals."
    ),
}


def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company (6-digit A-share code)"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, yyyy-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """Retrieve a technical indicator time-series for an A-share stock.

    Uses stockstats over akshare-sourced OHLCV data. Returns a text report
    with one (date, value) pair per trading day in the look-back window.
    """
    indicator = indicator.lower().strip()

    if indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator '{indicator}' is not supported. "
            f"Please choose from: {list(_INDICATOR_DESCRIPTIONS.keys())}"
        )

    curr_dt = _to_date(curr_date)
    before_dt = curr_dt - relativedelta(days=look_back_days)

    try:
        # Fetch once, compute indicator for all dates in one pass
        data = _load_ohlcv_akshare(symbol, curr_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        df[indicator]  # triggers stockstats calculation

        # Build dict: date → indicator value
        indicator_map = {}
        for _, row in df.iterrows():
            date_str = row["Date"]
            val = row[indicator]
            indicator_map[date_str] = "N/A" if pd.isna(val) else str(val)

        try:
            from .a_share_calendar import is_trade_day
        except ImportError:
            is_trade_day = lambda d: True  # fallback: assume all dates potentially have data

        # Walk backwards from curr_date and look up values
        ind_string = ""
        cursor = curr_dt
        while cursor >= before_dt:
            date_str = cursor.strftime("%Y-%m-%d")
            if date_str in indicator_map:
                value = indicator_map[date_str]
            elif is_trade_day(date_str):
                value = "N/A: Data not yet available (trading day)"
            else:
                value = "N/A: Not a trading day (weekend or holiday)"
            ind_string += f"{date_str}: {value}\n"
            cursor -= relativedelta(days=1)

    except Exception as e:
        # Fallback: compute one date at a time via _get_single_indicator
        ind_string = ""
        cursor = curr_dt
        while cursor >= before_dt:
            date_str = cursor.strftime("%Y-%m-%d")
            value = _get_single_indicator(symbol, indicator, date_str)
            ind_string += f"{date_str}: {value}\n"
            cursor -= relativedelta(days=1)

    result = (
        f"## {indicator} values from {before_dt.strftime('%Y-%m-%d')} to "
        f"{curr_date}:\n\n"
        + ind_string
        + "\n"
        + _INDICATOR_DESCRIPTIONS.get(
            indicator, "No description available."
        )
    )

    return result


def _get_single_indicator(symbol: str, indicator: str, curr_date: str) -> str:
    """Fallback: compute one indicator value for a single date."""
    try:
        from .a_share_calendar import is_trade_day
    except ImportError:
        is_trade_day = lambda d: True

    try:
        data = _load_ohlcv_akshare(symbol, curr_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        df[indicator]
        matching = df[df["Date"].str.startswith(curr_date)]
        if not matching.empty:
            val = matching[indicator].values[0]
            return str(val) if not pd.isna(val) else "N/A"
        if is_trade_day(curr_date):
            return "N/A: Data not yet available (trading day)"
        return "N/A: Not a trading day (weekend or holiday)"
    except Exception:
        if is_trade_day(curr_date):
            return "N/A: Data fetch failed (trading day)"
        return "N/A: Not a trading day (weekend or holiday)"


# ============================================================================
# 3. Fundamentals
# ============================================================================

def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company (6-digit A-share code)"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve fundamental data (PE, PB, Market Cap, Turnover) for an A-share stock.

    直连腾讯财经 HTTP API (qt.gtimg.cn)，获取实时核心估值指标。
    返回文本报告，包含：PE(TTM)、PB、总市值、换手率、涨跌幅等。
    """
    try:
        # 交易所前缀：6/9开头→沪市(sh)，0/2/3开头→深市(sz)
        prefix = "sh" if ticker[0] in ("6", "9") else "sz"
        url = f"https://qt.gtimg.cn/q={prefix}{ticker}"

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        text = resp.content.decode("gbk", errors="replace").strip()

        if "=" not in text:
            return f"基本面数据查询失败 ({ticker}): 响应格式错误（无 '=' 分隔符）"

        data_str = text.split("=", 1)[1].strip('"; \t\n\r')
        if not data_str:
            return f"基本面数据查询失败 ({ticker}): 空响应"

        fields = data_str.split("~")
        if len(fields) < 47:
            return (
                f"基本面数据查询失败 ({ticker}): 字段不足"
                f"（期望 ≥47，实际 {len(fields)}）"
            )

        name = fields[1]
        price = fields[3]
        last_close = fields[4]
        change_pct = fields[32]
        turnover = fields[38]
        pe = fields[39]
        total_market_cap = fields[44]
        pb = fields[46]

        header = (
            f"# 基本面数据: {ticker} ({name})\n"
            f"# 数据来源: 腾讯财经 (qt.gtimg.cn)\n"
            f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        lines = [
            f"**股票名称**: {name}",
            f"**最新价**: {price}",
            f"**昨收**: {last_close}",
            f"**涨跌幅**: {change_pct}%",
            f"**换手率**: {turnover}%",
            f"**市盈率(TTM)**: {pe}",
            f"**市净率(PB)**: {pb}",
            f"**总市值(亿)**: {total_market_cap}",
        ]

        return header + "\n".join(lines)

    except Exception as e:
        return f"基本面数据查询失败 ({ticker}): {str(e)}"


# ============================================================================
# 4–6. Financial Statements (Balance Sheet, Cash Flow, Income Statement)
# ============================================================================

# Priority financial metrics per report type.
# Only these columns are extracted from the raw Sina API response (which can
# return 100+ columns); the rest are discarded to keep LLM input lean.
_FINANCIAL_REPORT_PRIORITY = {
    "资产负债表": [
        # --- 资产 (Assets) ---
        "货币资金",
        "应收票据及应收账款",
        "存货",
        "流动资产合计",
        "固定资产",
        "非流动资产合计",
        "资产总计",
        # --- 负债 (Liabilities) ---
        "短期借款",
        "应付票据及应付账款",
        "流动负债合计",
        "非流动负债合计",
        "负债合计",
        # --- 股东权益 (Equity) ---
        "实收资本（或股本）",
        "未分配利润",
        "归属于母公司股东权益合计",
        "负债和股东权益总计",
    ],
    "利润表": [
        "营业总收入",
        "营业收入",
        "营业总成本",
        "营业成本",
        "营业利润",
        "利润总额",
        "净利润",
        "归属于母公司股东的净利润",
        "基本每股收益",
        "稀释每股收益",
    ],
    "现金流量表": [
        "经营活动现金流入小计",
        "经营活动现金流出小计",
        "经营活动产生的现金流量净额",
        "投资活动现金流入小计",
        "投资活动现金流出小计",
        "投资活动产生的现金流量净额",
        "筹资活动现金流入小计",
        "筹资活动现金流出小计",
        "筹资活动产生的现金流量净额",
        "现金及现金等价物净增加额",
        "期初现金及现金等价物余额",
        "期末现金及现金等价物余额",
    ],
}

# Semantic section headers for balance sheet metrics.
_BALANCE_SHEET_SECTIONS = {
    "资产": [
        "货币资金", "应收票据及应收账款", "存货",
        "流动资产合计", "固定资产", "非流动资产合计", "资产总计",
    ],
    "负债": [
        "短期借款", "应付票据及应付账款",
        "流动负债合计", "非流动负债合计", "负债合计",
    ],
    "股东权益": [
        "实收资本（或股本）", "未分配利润",
        "归属于母公司股东权益合计", "负债和股东权益总计",
    ],
}


def _format_financial_report(
    df: "pd.DataFrame",
    label: str,
    ticker: str,
    freq: str,
    report_type: str,
) -> str:
    """Convert a wide financial-report DataFrame into structured, LLM-friendly Markdown.

    The raw Sina API response can contain 100+ columns (one per financial metric).
    This function:
      - Extracts only priority metrics defined in ``_FINANCIAL_REPORT_PRIORITY``.
      - Groups balance-sheet items into Assets / Liabilities / Equity sections.
      - Formats output as a two-column Markdown table (项目 | 金额).
      - Falls back to showing *all* columns if no priority columns match (rare).

    Returns:
        str: Structured Markdown, ready for LLM consumption.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = [
        f"# {label} for {ticker} ({freq})",
        "# Data source: akshare (Sina Financial Reports)",
        f"# Report type: {report_type}",
        f"# Data retrieved on: {now_str}",
        "",
    ]

    # --- Report date ---
    report_date = ""
    if "报告日" in df.columns:
        report_date = str(df.iloc[0]["报告日"])
        lines.append(f"**报告日**: {report_date}")
    lines.append("")

    # --- Collect matched priority columns ---
    priority = _FINANCIAL_REPORT_PRIORITY.get(report_type, [])
    # NB: Sina columns may have parens or subtle variants, so we match by
    #     startswith on the cleaned key.
    actual_cols = {str(c).strip(): c for c in df.columns if str(c).strip() != "报告日"}
    matched: dict[str, str] = {}  # clean_key → label (may be original column name)

    for pkey in priority:
        pkey_stripped = pkey.strip()
        for clean, orig in actual_cols.items():
            if clean.startswith(pkey_stripped) or pkey_stripped.startswith(clean):
                matched[clean] = orig
                break

    # Fallback: if no priority columns matched, use all non-date columns
    if not matched:
        for clean, orig in actual_cols.items():
            matched[clean] = orig
        lines.append("> ⚠️ 未匹配到预定义关键指标，显示全部可用字段。")
        lines.append("")

    # --- Build the table(s) ---
    row = df.iloc[0]

    def _fmt_val(col_name: str) -> str:
        v = row[col_name]
        if pd.isna(v):
            return "—"
        try:
            n = float(v)
            if n == int(n) and abs(n) < 1e12:
                return f"{int(n):,}"
            return f"{n:,.2f}"
        except (ValueError, TypeError):
            return str(v)

    if report_type == "资产负债表" and matched:
        # Sectioned output
        for section_name, section_keys in _BALANCE_SHEET_SECTIONS.items():
            section_items: list[tuple[str, str]] = []
            for sk in section_keys:
                # find the actual matched column that starts with sk
                for clean, orig in matched.items():
                    if clean.startswith(sk) or sk.startswith(clean):
                        section_items.append((orig, _fmt_val(orig)))
                        break
            if not section_items:
                continue
            lines.append(f"### {section_name}")
            lines.append("| 项目 | 金额 |")
            lines.append("|------|------|")
            for item_label, item_val in section_items:
                lines.append(f"| {item_label} | {item_val} |")
            lines.append("")

        # Any unmatched priority columns → catch-all section
        shown_orig = {orig for _, orig in _BALANCE_SHEET_SECTIONS.get("资产", [])}
        shown_orig.update(orig for _, orig in _BALANCE_SHEET_SECTIONS.get("负债", []))
        shown_orig.update(orig for _, orig in _BALANCE_SHEET_SECTIONS.get("股东权益", []))
        # Actually shown_orig needs to use matched keys...
        # Simpler: just track which matched keys we've displayed
        displayed = set()
        for section_keys in _BALANCE_SHEET_SECTIONS.values():
            for sk in section_keys:
                for clean, orig in matched.items():
                    if clean.startswith(sk) or sk.startswith(clean):
                        displayed.add(orig)
        others = [(orig, _fmt_val(orig)) for clean, orig in matched.items() if orig not in displayed]
        if others:
            lines.append("### 其他")
            lines.append("| 项目 | 金额 |")
            lines.append("|------|------|")
            for item_label, item_val in others:
                lines.append(f"| {item_label} | {item_val} |")
            lines.append("")
    else:
        # Single flat table for income / cashflow
        lines.append("| 项目 | 金额 |")
        lines.append("|------|------|")
        for orig in matched.values():
            lines.append(f"| {orig} | {_fmt_val(orig)} |")
        lines.append("")

    # --- Note about column reduction ---
    total_cols = len(df.columns) - 1  # exclude 报告日
    shown_cols = len(matched)
    if total_cols > shown_cols:
        lines.append(
            f"> 📊 原始数据 {total_cols} 列，为便于分析只展示 {shown_cols} 个关键指标。"
        )

    return "\n".join(lines)


def _get_financial_report_sina(
    ticker: str,
    report_type: str,
    freq: str,
    curr_date: str,
    label: str,
) -> str:
    """Shared implementation for all three financial statements via Sina.

    Args:
        ticker: 6-digit A-share code.
        report_type: "资产负债表", "利润表", or "现金流量表".
        freq: "annual" or "quarterly" (for display only; Sina API returns what's available).
        curr_date: cutoff date for look-ahead bias prevention.
        label: Human-readable label for the header (e.g. "Balance Sheet").

    Returns:
        Structured Markdown with key financial metrics (not raw CSV).
    """
    try:
        _ensure_akshare()

        df = ak.stock_financial_report_sina(stock=ticker, symbol=report_type)

        # Filter: keep only the most recent report period
        if df is not None and not df.empty and '报告日' in df.columns:
            df = df.sort_values('报告日', ascending=False).head(1)

        if df is None or df.empty:
            return f"No {label.lower()} data found for symbol '{ticker}'"

        return _format_financial_report(df, label, ticker, freq, report_type)

    except ImportError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error retrieving {label.lower()} for {ticker}: {str(e)}"


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company (6-digit A-share code)"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve balance sheet data for an A-share stock."""
    return _get_financial_report_sina(
        ticker=ticker,
        report_type="资产负债表",
        freq=freq,
        curr_date=curr_date,
        label="Balance Sheet",
    )


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company (6-digit A-share code)"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve cash flow statement data for an A-share stock."""
    return _get_financial_report_sina(
        ticker=ticker,
        report_type="现金流量表",
        freq=freq,
        curr_date=curr_date,
        label="Cash Flow",
    )


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company (6-digit A-share code)"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve income statement data for an A-share stock."""
    return _get_financial_report_sina(
        ticker=ticker,
        report_type="利润表",
        freq=freq,
        curr_date=curr_date,
        label="Income Statement",
    )


# ============================================================================
# 7. Stock News
# ============================================================================

def get_news(
    ticker: Annotated[str, "ticker symbol of the company (6-digit A-share code)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve news articles for an A-share stock from East Money (东方财富).

    Returns Markdown-formatted string.
    """
    try:
        _ensure_akshare()

        df = ak.stock_news_em(symbol=ticker)

        if df is None or df.empty:
            return f"No news found for {ticker}"

        # Columns: 关键词, 新闻标题, 新闻内容, 发布时间, 文章来源, 新闻链接
        start_dt = _to_date(start_date)
        end_dt = _to_date(end_date)

        news_str = ""
        count = 0

        for _, row in df.iterrows():
            try:
                # Parse the publication datetime (format: "2026-04-25 10:15:22")
                pub_datetime = str(row.get("发布时间", ""))
                date_str = pub_datetime[:10] if len(pub_datetime) >= 10 else ""
                time_str = pub_datetime[11:19] if len(pub_datetime) >= 19 else ""

                if date_str:
                    pub_dt = datetime.strptime(date_str, "%Y-%m-%d")
                    if not (start_dt <= pub_dt <= end_dt + relativedelta(days=1)):
                        continue

                title = str(row.get("新闻标题", "No title"))
                source = str(row.get("文章来源", "Unknown"))
                summary = str(row.get("新闻内容", ""))

                pub_info = f"{pub_datetime}" if pub_datetime else date_str

                news_str += f"### {title}  (source: {source}, {pub_info})\n"
                if summary:
                    news_str += f"{summary}\n"
                news_str += "\n"
                count += 1
            except (ValueError, KeyError):
                continue

        if count == 0:
            return f"No news found for {ticker} between {start_date} and {end_date}"

        header = f"## {ticker} News, from {start_date} to {end_date}:\n\n"
        return header + news_str

    except ImportError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


# ============================================================================
# 8. Global / Macro News
# ============================================================================

def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """查询全球财经新闻（委托 a_stock_data）。"""
    try:
        from tradingagents.dataflows.a_stock_data import get_global_news_em
        return get_global_news_em(limit)
    except Exception as e:
        return f"全球新闻查询失败: {str(e)}"


# ============================================================================
# 9. Insider / Management Transactions
# ============================================================================

def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company (6-digit A-share code)"],
) -> str:
    """Retrieve management shareholding changes for an A-share stock.

    A-shares don't have "insider transactions" in the SEC sense.
    Instead we use akshare's stock_hold_management_detail_em() which reports
    changes in management/director shareholdings.

    Returns Markdown-formatted string.
    """
    try:
        _ensure_akshare()

        df = ak.stock_hold_management_detail_em(symbol=ticker)

        if df is None or df.empty:
            return f"No management shareholding change data found for symbol '{ticker}'"

        # Typical columns from East Money:
        # 股东名称, 持股数量, 变动数量, 变动比例, 变动日期, 变动原因, etc.
        tx_str = ""
        count = 0

        for _, row in df.iterrows():
            name = row.get("股东名称", "") or row.get("高管姓名", "") or "Unknown"
            shares = row.get("持股数量", "") or row.get("变动后持股数", "")
            change = row.get("变动数量", "")
            change_ratio = row.get("变动比例", "")
            date = row.get("变动日期", "")
            reason = row.get("变动原因", "")

            tx_str += f"### {name}\n"
            if date:
                tx_str += f"- Date: {date}\n"
            if shares:
                tx_str += f"- Shares Held: {shares}\n"
            if change:
                tx_str += f"- Change: {change}\n"
            if change_ratio:
                tx_str += f"- Change Ratio: {change_ratio}\n"
            if reason:
                tx_str += f"- Reason: {reason}\n"
            tx_str += "\n"
            count += 1

        if count == 0:
            return f"No management shareholding change data found for symbol '{ticker}'"

        header = (
            f"# Management Shareholding Changes for {ticker}\n"
            f"# Data source: akshare (East Money)\n"
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        return header + tx_str

    except ImportError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error retrieving insider/management transactions for {ticker}: {str(e)}"

# ============================================================================
# 10. Real-time Stock Quote
# ============================================================================

def get_current_price(
    symbol: Annotated[str, "ticker symbol of the company (6-digit A-share code)"],
) -> str:
    """Retrieve real-time stock quote for an A-share stock via Sina finance.

    Uses Sina's single-stock HTTP API (hq.sinajs.cn) directly with a 5-second
    timeout, avoiding the slow full-market scan in akshare's stock_zh_a_spot().

    Returns Markdown-formatted string.
    """
    sina_url = "https://hq.sinajs.cn/list="

    try:
        sina_symbol = _to_sina_symbol(symbol)
        resp = requests.get(
            sina_url + sina_symbol,
            timeout=5,
            headers={"Referer": "https://finance.sina.com.cn"},
        )
        resp.raise_for_status()
        resp.encoding = "gbk"

        text = resp.text.strip()
        if "=" not in text:
            return f"No real-time quote found for symbol '{symbol}'"

        data_str = text.split("=", 1)[1].strip('"; \n')
        if not data_str:
            return f"No real-time data for symbol '{symbol}'"

        fields = data_str.split(",")
        if len(fields) < 10:
            return f"Incomplete data for symbol '{symbol}'"

        name = fields[0]
        open_price = float(fields[1])
        prev_close = float(fields[2])
        price = float(fields[3])
        high = float(fields[4])
        low = float(fields[5])
        volume = int(float(fields[8]))
        amount = float(fields[9])
        date_str = fields[30] if len(fields) > 30 else ""
        time_str = fields[31] if len(fields) > 31 else ""
        data_time = f"{date_str} {time_str}".strip()

        change = round(price - prev_close, 3)
        change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close != 0 else 0.0

        volume_m = f"{volume / 10000:.0f}万手" if volume > 0 else "N/A"
        amount_yi = f"{amount / 100000000:.2f}亿" if amount > 0 else "N/A"

        lines = [
            f"# Real-time Quote for {symbol} ({name})",
            f"**Current Price**: {price:.2f}",
            f"**Change**: {change:+.2f} ({change_pct:+.2f}%)",
            f"**Open**: {open_price:.2f}",
            f"**High**: {high:.2f}",
            f"**Low**: {low:.2f}",
            f"**Previous Close**: {prev_close:.2f}",
            f"**Volume**: {volume_m}",
            f"**Turnover**: {amount_yi}",
            f"**Data Time**: {data_time}",
            f"",
            f"*Data source: Sina Finance (hq.sinajs.cn, real-time)*",
            f"*Retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ]

        return "\n".join(lines)

    except requests.exceptions.Timeout:
        return (
            f"网络请求超时: 获取 {symbol} 实时行情超时（5秒），请稍后重试。"
            f"\n可能是网络问题或新浪接口暂时不可用。"
        )
    except requests.exceptions.ConnectionError:
        return f"网络连接失败: 无法连接新浪行情接口，请检查网络。"
    except requests.exceptions.HTTPError as e:
        return f"HTTP 错误: {e.response.status_code if e.response else str(e)}"
    except ValueError as e:
        return f"数据解析错误: {e}"
    except Exception as e:
        return f"Error fetching current price for {symbol}: {str(e)}"


# ============================================================================
# 11. Social Sentiment — Behavioral Metrics (East Money + Xueqiu)
# ============================================================================

def get_social_sentiment(symbol: str) -> str:
    """Get A-share social sentiment behavioral metrics via akshare."""
    try:
        _ensure_akshare()
        lines = [f"## Social Sentiment Analysis for {symbol}", ""]

        try:
            df = ak.stock_comment_em()
            row = df[df["代码"] == symbol] if df is not None else None
            if row is not None and not row.empty:
                r = row.iloc[0]
                name = r.get("名称", symbol)
                lines[0] = f"## Social Sentiment Analysis for {symbol} ({name})"
                lines.append("### Attention Index (关注指数)")
                for col, label in [("关注指数", "Index"), ("关注度变化", "Change"),
                                   ("最新价", "Latest Price"), ("涨跌幅", "Change %")]:
                    if col in r.index and pd.notna(r[col]):
                        lines.append(f"- {label}: {r[col]}")
        except Exception as e:
            lines.append(f"*Attention index unavailable: {e}*")
        lines.append("")

        try:
            focus_df = ak.stock_comment_detail_scrd_focus_em(symbol=symbol)
            if focus_df is not None and not focus_df.empty:
                lines.append("### Attention Trend (近期关注度趋势)")
                lines.append(focus_df.head(7).to_string(index=False))
        except Exception as e:
            lines.append(f"*Attention trend unavailable: {e}*")
        lines.append("")

        try:
            desire_df = ak.stock_comment_detail_scrd_desire_em(symbol=symbol)
            if desire_df is not None and not desire_df.empty:
                lines.append("### Participation Willingness (参与意愿)")
                lines.append(desire_df.head(7).to_string(index=False))
        except Exception as e:
            lines.append(f"*Participation data unavailable: {e}*")
        lines.append("")

        try:
            hot_df = ak.stock_hot_rank_detail_realtime_em()
            hot_row = hot_df[hot_df["代码"] == symbol] if hot_df is not None else None
            if hot_row is not None and not hot_row.empty:
                lines.append("### Real-time Popularity Ranking (实时热度排名)")
                for _, hr in hot_row.iterrows():
                    parts = [f"{label}: {hr[col]}" for col, label in
                             [("排名", "Rank"), ("热度", "Score")]
                             if col in hr.index and pd.notna(hr[col])]
                    if parts:
                        lines.append(f"- {', '.join(parts)}")
        except Exception as e:
            lines.append(f"*Hot ranking unavailable: {e}*")
        lines.append("")

        try:
            xq_df = ak.stock_hot_follow_xq(symbol=symbol)
            if xq_df is not None and not xq_df.empty:
                lines.append("### Xueqiu Community (雪球关注)")
                lines.append(xq_df.head(10).to_string(index=False))
        except Exception as e:
            lines.append(f"*Xueqiu data unavailable: {e}*")
        lines.append("")

        lines.append(f"*Data source: akshare | Retrieved: {datetime.now():%Y-%m-%d %H:%M:%S}*")
        return "\n".join(lines)
    except Exception as e:
        return f"**Social sentiment data temporarily unavailable.** Error: {e}"


# ============================================================================
# 12. Real-time Quotes (East Money) — Multi-symbol, used by CLI quote command
# ============================================================================

# Cache for East Money spot data, shared by get_current_price and get_real_time_quotes
_SPOT_EM_CACHE_TTL = 30  # seconds
_spot_em_cache: tuple = (0, None)


def get_real_time_quotes(symbol: str) -> str:
    """Retrieve real-time stock quotes from East Money via push2 HTTP API.

    Direct HTTP call to East Money push2 endpoint, replacing the previous
    akshare ``ak.stock_zh_a_spot_em()`` full-market scan for better performance.

    Args:
        symbol: Single A-share code (eg ``600519``) or comma-separated multiple codes.

    Returns:
        Markdown-formatted string with real-time quotes for the requested symbol(s).
    """
    try:
        # Normalise: accept comma-separated or single code
        symbols = [s.strip() for s in symbol.replace("，", ",").split(",")]

        # Cache hit check — return cached result if same symbols and within TTL
        global _spot_em_cache
        cache_ts, cache_val = _spot_em_cache
        if cache_val is not None and time.time() - cache_ts < _SPOT_EM_CACHE_TTL:
            cached_symbols, cached_result = cache_val
            if cached_symbols == symbols:
                return cached_result

        # Build secid list: 沪市(6/5/9开头) → 1.{code}, 深市(其他) → 0.{code}
        secids = []
        for s in symbols:
            if s.startswith(("6", "5", "9")):
                secids.append(f"1.{s}")
            else:
                secids.append(f"0.{s}")

        fields = "f57,f58,f43,f44,f45,f46,f47,f48,f60,f116,f117,f162,f167,f168,f169"
        url = "https://push2.eastmoney.com/api/qt/ustock/ustock/get"
        params = {"fields": fields, "secids": ",".join(secids)}

        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("data") is None or data["data"] is None:
            return "No real-time data available"

        rows = []
        for item in data["data"]:
            if item is None:
                continue
            rows.append({
                "code": item.get("f57", ""),
                "name": item.get("f58", ""),
                "price": item.get("f43", "N/A"),
                "change": item.get("f117", "N/A"),
                "change_pct": item.get("f116", "N/A"),
                "open": item.get("f46", "N/A"),
                "high": item.get("f44", "N/A"),
                "low": item.get("f45", "N/A"),
                "prev_close": item.get("f60", "N/A"),
                "volume": item.get("f47", "N/A"),
                "amount": item.get("f48", "N/A"),
                "amplitude": item.get("f162", "N/A"),
                "turnover_rate": item.get("f167", "N/A"),
                "pe": item.get("f168", "N/A"),
                "pb": item.get("f169", "N/A"),
            })

        if not rows:
            joined = ", ".join(symbols)
            return f"No real-time quote found for symbol(s): '{joined}'"

        if len(rows) == 1:
            r = rows[0]
            lines = [
                f"# 实时行情: {r['code']} ({r['name']})",
                "",
                f"| 指标 | 值 |",
                f"|------|-----|",
                f"| **最新价** | {r['price']} |",
                f"| **涨跌额** | {r['change']} |",
                f"| **涨跌幅** | {r['change_pct']}% |",
                f"| **今开** | {r['open']} |",
                f"| **最高** | {r['high']} |",
                f"| **最低** | {r['low']} |",
                f"| **昨收** | {r['prev_close']} |",
                f"| **成交量** | {r['volume']} |",
                f"| **成交额** | {r['amount']} |",
                f"| **振幅** | {r['amplitude']} |",
                f"| **换手率** | {r['turnover_rate']}% |",
                f"| **市盈率(动态)** | {r['pe']} |",
                f"| **市净率** | {r['pb']} |",
                "",
                f"*数据来源: 东方财富 (push2, 实时)*",
                f"*获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            ]
        else:
            lines = [
                "# 实时行情（批量）",
                "",
                f"| 代码 | 名称 | 最新价 | 涨跌幅 | 涨跌额 | 成交量 | 成交额 | 最高 | 最低 | 今开 |",
                f"|------|------|--------|--------|--------|--------|--------|------|------|------|",
            ]
            for r in rows:
                lines.append(
                    f"| {r['code']} | {r['name']} | {r['price']} | {r['change_pct']}% | "
                    f"{r['change']} | {r['volume']} | {r['amount']} | "
                    f"{r['high']} | {r['low']} | {r['open']} |"
                )
            lines += [
                "",
                f"*数据来源: 东方财富 (push2, 实时)*",
                f"*获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            ]

        result = "\n".join(lines)
        _spot_em_cache = (time.time(), (symbols, result))
        return result

    except Exception as e:
        return f"实时行情查询失败 ({symbol}): {str(e)}"


# ============================================================================
# 13. Individual Stock Notices/Announcements
# ============================================================================


def get_individual_notices(
    symbol: str,
    days_back: int = 7,
    notice_type: str = "全部",
) -> str:
    """Fetch recent stock announcements for an A-share via cninfo (巨潮).

    直连巨潮公告 API，返回 Markdown 格式的公告列表（标题、时间、PDF 链接）。

    Args:
        symbol: 6-digit A-share code (eg ``600519``).
        days_back: Number of days to look back (default 7).
        notice_type: Filter type — retained for signature compatibility, not used
            by cninfo API (all types are returned).

    Returns:
        Markdown-formatted string with announcement list.
    """
    try:
        from tradingagents.dataflows.a_stock_data import get_cninfo_announcements
        return get_cninfo_announcements(symbol, page_size=min(days_back * 3, 50))
    except Exception as e:
        return f"公告查询失败 ({symbol}): {str(e)}"


def _filter_notices_by_date(df, start: datetime, end: datetime):
    """Filter notice DataFrame to rows within [start, end] date range.

    Attempts to parse the '公告时间' or '公告日期' column. If the date column
    is missing or unparseable, returns the original DataFrame unchanged.
    """
    import pandas as pd

    # Find the date column
    date_col = None
    for col in ["公告时间", "公告日期", "date", "发布时间"]:
        if col in df.columns:
            date_col = col
            break

    if date_col is None:
        return df  # No date column — return unfiltered

    try:
        dates = pd.to_datetime(df[date_col], errors="coerce")
        mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
        return df[mask]
    except Exception:
        return df  # Parse failure — return unfiltered


def _format_notices_df(df, symbol: str, days_back: int, type_label: str,
                       source_label: str) -> str:
    """Format a notice DataFrame into Markdown (individual notice report format)."""
    lines = [
        f"# 个股公告: {symbol}",
        f"最近 {days_back} 天 · {type_label}",
        "",
    ]

    for i, (_, row) in enumerate(df.iterrows(), 1):
        title = row.get("公告标题", row.get("title", f"公告 #{i}"))
        date_val = row.get("公告时间", row.get("date", row.get("公告日期", "")))
        cat = row.get("公告分类", row.get("type", row.get("公告类型", "")))
        content = row.get("公告内容", row.get("content", row.get("公告内容摘要", "")))

        lines.append(f"### {i}. {title}")
        lines.append(f"**日期**: {date_val}  |  **类型**: {cat}")
        lines.append("")

        if content and str(content).strip() and str(content) != "nan":
            text = str(content).strip()
            if len(text) > 1000:
                text = text[:1000] + "...(截断)"
            lines.append(text)
            lines.append("")

    lines.append("---")
    lines.append(f"共 {len(df)} 条公告 | 数据来源: {source_label} (akshare)")

    return "\n".join(lines)


def _format_notices_market_df(df, symbol: str, days_back: int,
                              type_label: str) -> str:
    """Format a market-wide notice DataFrame into Markdown (fallback format).

    Market-wide results lack full content text — they only have titles and URLs.
    """
    source_line = f"共 {len(df)} 条公告 | 数据来源: 东方财富 (akshare, 市场级 fallback)"

    lines = [
        f"# 个股公告: {symbol}",
        f"最近 {days_back} 天 · {type_label}",
        "",
    ]

    for i, (_, row) in enumerate(df.iterrows(), 1):
        title = row.get("公告标题", f"公告 #{i}")
        date_val = row.get("公告日期", "")
        cat = row.get("公告类型", "")
        url = row.get("网址", "")

        lines.append(f"### {i}. {title}")
        lines.append(f"**日期**: {date_val}  |  **类型**: {cat}")
        if url:
            lines.append(f"**链接**: {url}")
        lines.append("")

    lines.append("---")
    lines.append(source_line)

    return "\n".join(lines)


# ============================================================================
# 14. Research Reports (Analyst Reports)
# ============================================================================


def get_research_reports(symbol: str, top_n: int = 5) -> str:
    """查询A股研报（委托 a_stock_data）。"""
    try:
        from tradingagents.dataflows.a_stock_data import get_research_reports as _rpt
        return _rpt(symbol, max_pages=max(1, top_n // 10))
    except Exception as e:
        return f"研报查询失败: {str(e)}"
