"""
Alert condition checker for TradingAgents CLI: check-alerts command.

Reads watchlist entries, checks each stock's alert conditions against
real-time/historical data via akshare, and reports triggered alerts.

Alert conditions (from watchlist per-stock ``alerts`` dict):
  - price_above:    trigger when current_price > threshold
  - price_below:    trigger when current_price < threshold
  - rsi_oversold:   trigger when RSI < 30 (boolean flag or numeric threshold)
  - rsi_overbought: trigger when RSI > 70 (boolean flag or numeric threshold)
  - volume_surge:   trigger when today's volume > N * average volume
  - ma_cross:       trigger when price crosses MA (golden cross / death cross)

Usage:
    tradingagents check-alerts --date 2026-05-09 --output json
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional, Tuple

import typer
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.watchlist import WatchlistManager

# ---------------------------------------------------------------------------
# Lazy akshare import
# ---------------------------------------------------------------------------
try:
    import akshare as ak
except ImportError:
    ak = None  # type: ignore[assignment]

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

try:
    from stockstats import wrap
except ImportError:
    wrap = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Alert checking logic (pure functions where possible)
# ---------------------------------------------------------------------------

def _check_price(current_price: float, alert_type: str, threshold: float) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Check price_above / price_below conditions.

    Returns (triggered, result_dict_or_None).
    """
    if alert_type == "price_above" and current_price > threshold:
        return True, {
            "alert": "price_above",
            "current": current_price,
            "threshold": threshold,
        }
    if alert_type == "price_below" and current_price < threshold:
        return True, {
            "alert": "price_below",
            "current": current_price,
            "threshold": threshold,
        }
    return False, None


def _check_rsi(rsi_value: float, alert_type: str, threshold: Any) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Check rsi_oversold / rsi_overbought conditions.

    threshold may be a boolean (True = use default 30/70) or a number.
    """
    if alert_type == "rsi_oversold":
        # If threshold is True (boolean flag), use default 30
        limit = 30.0 if threshold is True else float(threshold)
        if rsi_value < limit:
            return True, {
                "alert": "rsi_oversold",
                "current": round(rsi_value, 2),
                "threshold": limit,
            }
    if alert_type == "rsi_overbought":
        limit = 70.0 if threshold is True else float(threshold)
        if rsi_value > limit:
            return True, {
                "alert": "rsi_overbought",
                "current": round(rsi_value, 2),
                "threshold": limit,
            }
    return False, None


def _check_volume_surge(current_volume: float, avg_volume: float, multiplier: float) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Check volume_surge: current volume > multiplier * average volume.

    multiplier from alert config (default 2.0 if boolean True).
    """
    if avg_volume <= 0:
        return False, None
    mult = float(multiplier) if multiplier is not True else 2.0
    if current_volume > mult * avg_volume:
        return True, {
            "alert": "volume_surge",
            "current": round(current_volume, 0),
            "avg_volume": round(avg_volume, 0),
            "multiplier": mult,
            "surge_ratio": round(current_volume / avg_volume, 2),
        }
    return False, None


def _check_ma_cross(df, alert_config: Any) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Check ma_cross: price crossing MA(5) or MA(20).

    Detects golden cross (price crosses above MA) and death cross
    (price crosses below MA) using the most recent two data points.

    alert_config can be:
      - True / "golden" : check for golden cross (price crosses above MA)
      - "death" : check for death cross
      - dict: {"type": "golden"|"death", "period": 5|20}
    """
    if len(df) < 2:
        return False, None

    # Determine cross type and MA period
    cross_type = "golden"  # default
    period = 20  # default

    if isinstance(alert_config, dict):
        cross_type = str(alert_config.get("type", "golden")).lower()
        period = int(alert_config.get("period", 20))
    elif isinstance(alert_config, str):
        cross_type = alert_config.lower()
    # else: True → defaults above

    # Ensure MA column exists in the wrapped DataFrame
    ma_key = f"ma_{period}"
    if ma_key not in df.columns:
        # Try wrapping to compute indicators
        try:
            wrapped = wrap(df.copy())
            ma_col = f"close_{period}_sma"
            if ma_col in wrapped.columns:
                df = wrapped
                ma_key = ma_col
        except Exception:
            pass

    if ma_key not in df.columns:
        return False, None

    # Get the two most recent rows
    recent = df.tail(2)
    prev_close = recent.iloc[0]["Close"]
    curr_close = recent.iloc[1]["Close"]
    prev_ma = recent.iloc[0][ma_key]
    curr_ma = recent.iloc[1][ma_key]

    if pd.isna(prev_ma) or pd.isna(curr_ma):
        return False, None

    if cross_type == "golden":
        # Golden cross: price was below MA and now above
        if prev_close <= prev_ma and curr_close > curr_ma:
            return True, {
                "alert": "ma_cross",
                "cross_type": "golden_cross",
                "period": period,
                "prev_close": round(float(prev_close), 2),
                "curr_close": round(float(curr_close), 2),
                "prev_ma": round(float(prev_ma), 2),
                "curr_ma": round(float(curr_ma), 2),
            }
    elif cross_type == "death":
        # Death cross: price was above MA and now below
        if prev_close >= prev_ma and curr_close < curr_ma:
            return True, {
                "alert": "ma_cross",
                "cross_type": "death_cross",
                "period": period,
                "prev_close": round(float(prev_close), 2),
                "curr_close": round(float(curr_close), 2),
                "prev_ma": round(float(prev_ma), 2),
                "curr_ma": round(float(curr_ma), 2),
            }

    return False, None


# ---------------------------------------------------------------------------
# Data fetching helpers
# ---------------------------------------------------------------------------

def _get_spot_price(ticker: str) -> Optional[float]:
    """Fetch current price for a ticker via the shared get_current_price() cache.

    Returns None on any error (network, ticker not found, etc.).
    """
    if ak is None:
        return None
    try:
        from tradingagents.dataflows.akshare import get_current_price
        import re

        result = get_current_price(ticker)
        if not result or result.startswith("Error") or "No real-time" in result:
            return None

        for line in result.split("\n"):
            if "**Current Price**" in line:
                m = re.search(r"([\d.]+)", line)
                if m:
                    return float(m.group(1))
        return None
    except Exception:
        return None


def _get_historical_data(ticker: str, date: str):
    """Load historical OHLCV data for alert checks.

    Returns a (DataFrame, wrapped_DataFrame) tuple, or (None, None) on error.
    The wrapped DataFrame includes calculated stockstats indicators.
    """
    if ak is None or pd is None:
        return None, None
    try:
        from tradingagents.dataflows.akshare import _load_ohlcv_akshare
        data = _load_ohlcv_akshare(ticker, date)
        if data is None or data.empty:
            return None, None

        # Wrap for technical indicators
        wdf = None
        if wrap is not None:
            try:
                wdf = wrap(data.copy())
            except Exception:
                pass

        return data, wdf
    except Exception:
        return None, None


def _get_rsi_value(wdf, date: str) -> Optional[float]:
    """Extract RSI value for a specific date from a wrapped DataFrame."""
    if wdf is None or pd is None:
        return None
    try:
        wdf["_date_str"] = pd.to_datetime(wdf["Date"]).dt.strftime("%Y-%m-%d")
        matching = wdf[wdf["_date_str"] == date]
        if matching.empty:
            # Try the most recent date as fallback
            matching = wdf.tail(1)
        if "rsi" not in wdf.columns:
            return None
        val = matching["rsi"].values[0]
        return float(val) if not pd.isna(val) else None
    except Exception:
        return None


def _get_volume_data(data, wdf) -> Tuple[Optional[float], Optional[float]]:
    """Get current day volume and 20-day average volume.

    Returns (current_volume, avg_volume_20day) or (None, None).
    """
    if data is None or data.empty or pd is None:
        return None, None
    try:
        if "Volume" not in data.columns:
            return None, None
        if len(data) < 20:
            return None, float(data["Volume"].mean())

        current_vol = float(data["Volume"].iloc[-1])
        avg_vol = float(data["Volume"].tail(20).mean())
        return current_vol, avg_vol
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Main check function — checks one stock against its alerts
# ---------------------------------------------------------------------------

VALID_ALERT_TYPES = {
    "price_above", "price_below",
    "rsi_oversold", "rsi_overbought",
    "volume_surge", "ma_cross",
}

PRICE_ALERTS = {"price_above", "price_below"}
RSI_ALERTS = {"rsi_oversold", "rsi_overbought"}


def _check_stock_alerts(
    ticker: str,
    alerts: Dict[str, Any],
    date: str,
    spot_price: Optional[float],
    ohlcv_data,
    wrapped_df,
) -> List[Dict[str, Any]]:
    """Check all alert conditions for a single stock.

    Returns a list of triggered alert dicts (empty if none triggered).
    """
    triggered: List[Dict[str, Any]] = []

    # Determine which data groups we need
    need_price = bool(PRICE_ALERTS & set(alerts.keys()))
    need_rsi = bool(RSI_ALERTS & set(alerts.keys()))
    need_volume = "volume_surge" in alerts
    need_ma = "ma_cross" in alerts

    # Pre-fetch data as needed
    if need_rsi or need_volume or need_ma:
        if ohlcv_data is None:
            ohlcv_data, wrapped_df = _get_historical_data(ticker, date)

    for alert_type, threshold in alerts.items():
        if alert_type not in VALID_ALERT_TYPES:
            continue

        try:
            if alert_type in PRICE_ALERTS:
                if need_price and spot_price is None:
                    spot_price = _get_spot_price(ticker)
                if spot_price is not None:
                    ok, result = _check_price(spot_price, alert_type, float(threshold))
                    if ok and result:
                        triggered.append(result)

            elif alert_type in RSI_ALERTS:
                rsi_val = _get_rsi_value(wrapped_df, date)
                if rsi_val is not None:
                    ok, result = _check_rsi(rsi_val, alert_type, threshold)
                    if ok and result:
                        triggered.append(result)

            elif alert_type == "volume_surge":
                current_vol, avg_vol = _get_volume_data(ohlcv_data, wrapped_df)
                if current_vol is not None and avg_vol is not None:
                    ok, result = _check_volume_surge(current_vol, avg_vol, threshold)
                    if ok and result:
                        triggered.append(result)

            elif alert_type == "ma_cross":
                if ohlcv_data is not None:
                    ok, result = _check_ma_cross(ohlcv_data, threshold)
                    if ok and result:
                        triggered.append(result)

        except Exception:
            # Individual alert check failure should not prevent others
            continue

    return triggered


# ---------------------------------------------------------------------------
# Typer command
# ---------------------------------------------------------------------------

def check_alerts(
    date: str = typer.Option(
        datetime.datetime.now().strftime("%Y-%m-%d"),
        "--date", "-d",
        help="检查日期 YYYY-MM-DD（默认今天）",
    ),
    output: str = typer.Option(
        "text",
        "--output", "-o",
        help='输出格式: "json" 或 "text"',
    ),
) -> None:
    """检查监视列表中的告警条件，报告触发的告警。

    逐只股票检查 watchlist 中配置的告警条件（价格、RSI、成交量、均线交叉），
    输出已触发告警的详情。

    示例：
        tradingagents check-alerts --date 2026-05-09 --output json
    """
    # Validate args
    output_mode = output.strip().lower()
    if output_mode not in ("json", "text"):
        typer.echo(
            f"错误: --output 必须为 'json' 或 'text'，收到: '{output}'",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        typer.echo(
            f"错误: 日期格式无效 '{date}'，请使用 YYYY-MM-DD 格式",
            err=True,
        )
        raise typer.Exit(code=1)

    # Read watchlist
    mgr = WatchlistManager()
    stocks = mgr.list()
    tickers = [s["ticker"] for s in stocks]

    if not tickers:
        if output_mode == "json":
            typer.echo(json.dumps({
                "date": date,
                "triggered": [],
                "checked": 0,
                "triggered_count": 0,
            }, ensure_ascii=False, indent=2))
        else:
            typer.echo("监视列表为空，无告警需要检查。")
        return

    # Check each stock's alerts
    all_triggered: List[Dict[str, Any]] = []
    checked = 0

    for stock in stocks:
        ticker = stock["ticker"]
        alerts = stock.get("alerts", {})

        # Skip stocks without alert conditions
        if not alerts or not any(
            k in VALID_ALERT_TYPES for k in alerts
        ):
            continue

        checked += 1

        # For alert checks, pre-fetch spot price as most alerts need it
        spot_price = None
        ohlcv_data = None
        wrapped_df = None

        # Determine what data we need
        need_price = bool(PRICE_ALERTS & set(alerts.keys()))
        need_ohlcv = any(
            k in alerts for k in (list(RSI_ALERTS) + ["volume_surge", "ma_cross"])
        )

        try:
            if need_price:
                spot_price = _get_spot_price(ticker)
            if need_ohlcv:
                ohlcv_data, wrapped_df = _get_historical_data(ticker, date)

            triggered = _check_stock_alerts(
                ticker, alerts, date, spot_price, ohlcv_data, wrapped_df,
            )
            for t in triggered:
                t.setdefault("ticker", ticker)
            all_triggered.extend(triggered)
        except Exception:
            # Single stock failure should not halt entire check
            continue

    # Output
    if output_mode == "json":
        result = {
            "date": date,
            "triggered": all_triggered,
            "checked": checked,
            "triggered_count": len(all_triggered),
        }
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # Text output
        lines: List[str] = []
        sep = "=" * 60
        lines.append(sep)
        lines.append(f"  告警检查 - {date}")
        lines.append(sep)
        lines.append(f"  已检查: {checked} 只股票（有告警条件）")
        lines.append(f"  已触发: {len(all_triggered)} 个告警")
        lines.append("")

        if all_triggered:
            alert_label = {
                "price_above": "价格突破上限",
                "price_below": "价格跌破下限",
                "rsi_oversold": "RSI 超卖",
                "rsi_overbought": "RSI 超买",
                "volume_surge": "成交量激增",
                "ma_cross": "均线交叉",
                "golden_cross": "金叉",
                "death_cross": "死叉",
            }
            for t in all_triggered:
                ticker_str = t.get("ticker", "")
                alert_key = t.get("alert", "")
                alert_name = alert_label.get(alert_key, alert_key)
                cross_type = t.get("cross_type", "")
                cross_name = alert_label.get(cross_type, "")
                if cross_name:
                    alert_name = f"{alert_name}（{cross_name}）"

                # Build detail line
                detail = f"  [{ticker_str}] {alert_name}"
                if alert_key in ("price_above", "price_below"):
                    detail += f"  →  现价: {t['current']}, 阈值: {t['threshold']}"
                elif alert_key in ("rsi_oversold", "rsi_overbought"):
                    detail += f"  →  RSI: {t['current']}, 阈值: {t['threshold']}"
                elif alert_key == "volume_surge":
                    detail += f"  →  成交量: {t['current']}, 均量: {t['avg_volume']}, 倍数: {t['surge_ratio']}x"
                elif alert_key == "ma_cross":
                    detail += f"  →  昨收: {t.get('prev_close')}, 今收: {t.get('curr_close')}, MA({t.get('period')}): {t.get('curr_ma')}"
                lines.append(detail)
        else:
            lines.append("  （无告警触发）")

        lines.append("")
        lines.append(sep)
        typer.echo("\n".join(lines))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        check_alerts()
    else:
        typer.echo("用法: python -m cli.alerts --date 2026-05-09 --output json")
