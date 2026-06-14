"""
MACD ETF Strategy for OpenAlgo — v2
=====================================
Strategy   : Dual Timeframe MACD (12, 24, 3)
Universe   : ETFs via yfinance (NSE)
Execution  : Zerodha via OpenAlgo SDK (MTF product)

Entry      : Monthly MACD line > Monthly Signal line (filter)
             + Weekly MACD crossed above Weekly Signal (trigger)

Exit       : Weekly MACD crossed below Weekly Signal line

Candle rule: Always use iloc[-1] as last closed candle.
             yfinance never returns incomplete candles for
             daily/weekly/monthly intervals. So iloc[-1] is
             always the last fully closed candle regardless
             of what time or day the script is run.
             Works for: weekends, holidays, special sessions,
             Diwali muhurat, post-market runs, pre-market runs.

Data       : yfinance weekly + monthly candles
Run        : Runs immediately on startup — no fixed time
             Just open OpenAlgo and click Run any time
Author     : Generated for OpenAlgo Python Strategy Manager
Version    : 2.0 — Fixed iloc, rate limiting, rich logging
"""

import os
import time
import math
import logging
from datetime import datetime
import pytz
import pandas as pd
import yfinance as yf
from openalgo import api

# ─────────────────────────────────────────────
# CONFIGURATION — Only edit this block
# ─────────────────────────────────────────────

# Your OpenAlgo API key (get from OpenAlgo UI → API Key page)
API_KEY  = "c3dc554ae593b234bff9849b3f076cb5084d21673fe064058a2b85679cf74b73"
HOST_URL = "http://127.0.0.1:5000"

# Strategy identity shown in OpenAlgo order logs
STRATEGY_NAME = "MACD_ETF_MTF"

# Exchange
EXCHANGE = "NSE"

# Product type
# "MTF" → live leveraged trading via Zerodha MTF
# "CNC" → use this for sandbox / dry run testing
PRODUCT = "CNC"

# Cash per ETF from your side (INR)
CASH_PER_ETF = 10000  # <- change anytime

# MTF leverage Zerodha offers per ETF
MTF_LEVERAGE = 4  # <- change if Zerodha offers different

# MACD parameters — same for weekly and monthly
MACD_FAST   = 12
MACD_SLOW   = 24
MACD_SIGNAL = 3

# Delay between fetching each ETF from yfinance (seconds)
# Prevents rate limiting
FETCH_DELAY = 0.5

# IST timezone
IST = pytz.timezone("Asia/Kolkata")

# ─────────────────────────────────────────────
# ETF UNIVERSE
# Format: { "OPENALGO_SYMBOL": "YFINANCE_TICKER" }
# Add or remove ETFs here — code adapts automatically
# ─────────────────────────────────────────────

ETF_LIST = {
    "NIFTYBEES":   "NIFTYBEES.NS",
    "JUNIORBEES":  "JUNIORBEES.NS",
    "MOM100":      "MOM100.NS",
    "HDFCSML250":  "HDFCSML250.NS",
    "BANKBEES":    "BANKBEES.NS",
    "ITBEES":      "ITBEES.NS",
    "PSUBNKBEES":  "PSUBNKBEES.NS",
    "ICICIB22":    "ICICIB22.NS",
    "INFRABEES":   "INFRABEES.NS",
    "CONSUMBEES":  "CONSUMBEES.NS",
    "PHARMABEES":  "PHARMABEES.NS",
    "HEALTHIETF":  "HEALTHIETF.NS",
    "MOM30IETF":   "MOM30IETF.NS",
    "ALPHA":       "ALPHA.NS",
    "MODEFENCE":   "MODEFENCE.NS",
    "ALPL30IETF":  "ALPL30IETF.NS",
    "MIDCAPETF":   "MIDCAPETF.NS",
    "OILIETF":     "OILIETF.NS",
    "MOSMALL250":  "MOSMALL250.NS",
    "MOVALUE":     "MOVALUE.NS",
    "GOLDBEES":    "GOLDBEES.NS",
}

# ─────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# OPENALGO CLIENT
# ─────────────────────────────────────────────

client = api(
    api_key=API_KEY,
    host=HOST_URL
)

# ─────────────────────────────────────────────
# MACD CALCULATION
# ─────────────────────────────────────────────

def calculate_macd(close_series, ticker_name):
    """
    Calculate MACD (12, 24, 3) on a closing price series.

    CANDLE RULE:
    Always use iloc[-1] as last closed candle.
    yfinance never returns incomplete candles for weekly/monthly
    intervals — so iloc[-1] is always safe regardless of when
    the script runs (morning, evening, weekend, holiday).

    Returns: pd.DataFrame or None on failure
    """
    try:
        if len(close_series) < MACD_SLOW + MACD_SIGNAL + 3:
            log.error(
                f"    [MACD-ERROR] {ticker_name} | "
                f"Not enough data | "
                f"Have {len(close_series)} rows, "
                f"need {MACD_SLOW + MACD_SIGNAL + 3}"
            )
            return None

        ema_fast    = close_series.ewm(span=MACD_FAST,   adjust=False).mean()
        ema_slow    = close_series.ewm(span=MACD_SLOW,   adjust=False).mean()
        macd_line   = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
        histogram   = macd_line - signal_line

        if macd_line.iloc[-1] != macd_line.iloc[-1]:  # NaN check
            log.error(
                f"    [MACD-ERROR] {ticker_name} | "
                f"NaN in MACD values — data may have gaps"
            )
            return None

        return pd.DataFrame({
            "macd_line":   macd_line,
            "signal_line": signal_line,
            "histogram":   histogram
        }, index=close_series.index)

    except Exception as e:
        log.error(
            f"    [MACD-ERROR] {ticker_name} | "
            f"Exception in MACD calculation | {e}"
        )
        return None


# ─────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────

def fetch_weekly_data(symbol, yf_ticker):
    """
    Fetch 3 years of weekly OHLCV data.

    CANDLE RULE: iloc[-1] = last closed weekly candle always.
    Mid-week: last week's candle. After week close: this week's candle.
    yfinance handles this automatically.

    Returns: pd.DataFrame or None
    """
    try:
        log.info(f"    [DATA] Fetching weekly data for {symbol} ({yf_ticker})")

        df = yf.download(
            yf_ticker,
            period="3y",
            interval="1wk",
            progress=False,
            auto_adjust=True
        )

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df is None or df.empty:
            log.error(
                f"    [DATA-ERROR] {symbol} ({yf_ticker}) | "
                f"Weekly data empty | "
                f"Possible: wrong ticker, delisted, network issue | "
                f"Action: skipping"
            )
            return None

        if len(df) < MACD_SLOW + MACD_SIGNAL + 3:
            log.error(
                f"    [DATA-ERROR] {symbol} ({yf_ticker}) | "
                f"Insufficient weekly rows: {len(df)} | "
                f"Need: {MACD_SLOW + MACD_SIGNAL + 3} | "
                f"Action: skipping"
            )
            return None

        last_candle_date = df.index[-1]
        if hasattr(last_candle_date, 'date'):
            last_candle_date = last_candle_date.date()

        log.info(
            f"    [DATA] {symbol} weekly | "
            f"Rows: {len(df)} | "
            f"Last closed candle: {last_candle_date}"
        )
        return df

    except Exception as e:
        log.error(
            f"    [DATA-ERROR] {symbol} ({yf_ticker}) | "
            f"Weekly fetch exception: {e} | "
            f"Action: skipping"
        )
        return None


def fetch_monthly_data(symbol, yf_ticker):
    """
    Fetch 5 years of monthly OHLCV data.

    CANDLE RULE: iloc[-1] = last closed monthly candle always.
    Mid-month: last month's candle. After month close: this month's candle.
    yfinance handles this automatically.

    Returns: pd.DataFrame or None
    """
    try:
        log.info(f"    [DATA] Fetching monthly data for {symbol} ({yf_ticker})")

        df = yf.download(
            yf_ticker,
            period="5y",
            interval="1mo",
            progress=False,
            auto_adjust=True
        )

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df is None or df.empty:
            log.error(
                f"    [DATA-ERROR] {symbol} ({yf_ticker}) | "
                f"Monthly data empty | "
                f"Possible: wrong ticker, delisted, network issue | "
                f"Action: skipping"
            )
            return None

        if len(df) < MACD_SLOW + MACD_SIGNAL + 3:
            log.error(
                f"    [DATA-ERROR] {symbol} ({yf_ticker}) | "
                f"Insufficient monthly rows: {len(df)} | "
                f"Need: {MACD_SLOW + MACD_SIGNAL + 3} | "
                f"Action: skipping"
            )
            return None

        last_candle_date = df.index[-1]
        if hasattr(last_candle_date, 'date'):
            last_candle_date = last_candle_date.date()

        log.info(
            f"    [DATA] {symbol} monthly | "
            f"Rows: {len(df)} | "
            f"Last closed candle: {last_candle_date}"
        )
        return df

    except Exception as e:
        log.error(
            f"    [DATA-ERROR] {symbol} ({yf_ticker}) | "
            f"Monthly fetch exception: {e} | "
            f"Action: skipping"
        )
        return None


# ─────────────────────────────────────────────
# SIGNAL LOGIC
# ─────────────────────────────────────────────

def is_monthly_bullish(symbol, yf_ticker):
    """
    Monthly MACD filter:
    Returns True if Monthly MACD line > Monthly Signal line
    on the last closed monthly candle (iloc[-1]).

    No crossover needed — just MACD above signal.
    This confirms the long-term trend is bullish.
    """
    df = fetch_monthly_data(symbol, yf_ticker)
    if df is None:
        return False

    close = df["Close"].dropna()
    macd  = calculate_macd(close, f"{symbol}-monthly")
    if macd is None:
        return False

    # Always iloc[-1] — last closed monthly candle
    macd_val   = float(macd["macd_line"].iloc[-1])
    signal_val = float(macd["signal_line"].iloc[-1])
    is_bullish = macd_val > signal_val

    last_candle_date = df.index[-1]
    if hasattr(last_candle_date, 'date'):
        last_candle_date = last_candle_date.date()

    log.info(
        f"    [MONTHLY-MACD] {symbol} | "
        f"Candle: {last_candle_date} | "
        f"MACD: {macd_val:.4f} | "
        f"Signal: {signal_val:.4f} | "
        f"Bullish: {is_bullish}"
    )
    return is_bullish


def check_weekly_crossover_up(symbol, yf_ticker):
    """
    Weekly entry trigger:
    Returns True if Weekly MACD crossed ABOVE Weekly Signal
    on the last closed weekly candle.

    Crossover using iloc[-1] and iloc[-2]:
      iloc[-1] = last closed weekly candle
      iloc[-2] = week before that
    """
    df = fetch_weekly_data(symbol, yf_ticker)
    if df is None:
        return False

    close = df["Close"].dropna()
    macd  = calculate_macd(close, f"{symbol}-weekly-entry")
    if macd is None:
        return False

    curr_macd   = float(macd["macd_line"].iloc[-1])
    curr_signal = float(macd["signal_line"].iloc[-1])
    prev_macd   = float(macd["macd_line"].iloc[-2])
    prev_signal = float(macd["signal_line"].iloc[-2])

    curr_date = df.index[-1]
    prev_date = df.index[-2]
    if hasattr(curr_date, 'date'):
        curr_date = curr_date.date()
        prev_date = prev_date.date()

    crossed_up = (prev_macd < prev_signal) and (curr_macd > curr_signal)

    log.info(
        f"    [WEEKLY-ENTRY] {symbol} | "
        f"Prev ({prev_date}): MACD={prev_macd:.4f} Signal={prev_signal:.4f} | "
        f"Curr ({curr_date}): MACD={curr_macd:.4f} Signal={curr_signal:.4f} | "
        f"Crossover UP: {crossed_up}"
    )
    return crossed_up


def check_weekly_crossover_down(symbol, yf_ticker):
    """
    Weekly exit trigger:
    Returns True if Weekly MACD crossed BELOW Weekly Signal
    on the last closed weekly candle.
    """
    df = fetch_weekly_data(symbol, yf_ticker)
    if df is None:
        return False

    close = df["Close"].dropna()
    macd  = calculate_macd(close, f"{symbol}-weekly-exit")
    if macd is None:
        return False

    curr_macd   = float(macd["macd_line"].iloc[-1])
    curr_signal = float(macd["signal_line"].iloc[-1])
    prev_macd   = float(macd["macd_line"].iloc[-2])
    prev_signal = float(macd["signal_line"].iloc[-2])

    curr_date = df.index[-1]
    prev_date = df.index[-2]
    if hasattr(curr_date, 'date'):
        curr_date = curr_date.date()
        prev_date = prev_date.date()

    crossed_down = (prev_macd > prev_signal) and (curr_macd < curr_signal)

    log.info(
        f"    [WEEKLY-EXIT] {symbol} | "
        f"Prev ({prev_date}): MACD={prev_macd:.4f} Signal={prev_signal:.4f} | "
        f"Curr ({curr_date}): MACD={curr_macd:.4f} Signal={curr_signal:.4f} | "
        f"Crossover DOWN: {crossed_down}"
    )
    return crossed_down


# ─────────────────────────────────────────────
# POSITION STATE — Holdings + Positionbook
# ─────────────────────────────────────────────

def get_invested_etfs():
    """
    Returns dict of ETFs currently invested in.
    Checks BOTH holdings (T+1 MTF) and positionbook (same day).

    Returns: dict { "SYMBOL": quantity }
    """
    invested = {}
    log.info("  [POSITIONS] Fetching holdings from OpenAlgo...")

    # --- Holdings ---
    try:
        resp = client.holdings()
        if resp and isinstance(resp, dict) and resp.get("status") == "success":
            data = resp.get("data", [])
            if isinstance(data, list):
                for item in data:
                    sym = str(item.get("tradingsymbol", "")).upper()
                    qty = int(item.get("quantity", 0))
                    if sym in ETF_LIST and qty > 0:
                        invested[sym] = invested.get(sym, 0) + qty
                        log.info(f"  [HOLDINGS] Found: {sym} | Qty: {qty}")
            log.info(
                f"  [HOLDINGS] Fetch successful | "
                f"{len(invested)} ETFs found"
            )
        else:
            log.warning(
                f"  [HOLDINGS-WARN] Unexpected response: {resp}"
            )
    except Exception as e:
        log.error(
            f"  [HOLDINGS-ERROR] Failed: {e} | "
            f"Will still check positionbook"
        )

    # --- Positionbook ---
    log.info("  [POSITIONS] Fetching positionbook from OpenAlgo...")
    try:
        resp = client.positionbook()
        if resp and isinstance(resp, dict) and resp.get("status") == "success":
            data = resp.get("data", [])
            if isinstance(data, list):
                for item in data:
                    sym = str(item.get("tradingsymbol", "")).upper()
                    qty = int(item.get("quantity", 0))
                    if sym in ETF_LIST and qty > 0:
                        invested[sym] = invested.get(sym, 0) + qty
                        log.info(
                            f"  [POSITIONBOOK] Found: {sym} | Qty: {qty}"
                        )
            log.info("  [POSITIONBOOK] Fetch successful")
        else:
            log.warning(
                f"  [POSITIONBOOK-WARN] Unexpected response: {resp}"
            )
    except Exception as e:
        log.error(f"  [POSITIONBOOK-ERROR] Failed: {e}")

    log.info(
        f"  [POSITIONS] Total invested ETFs: {len(invested)} | "
        f"Symbols: {list(invested.keys()) if invested else 'None'}"
    )
    return invested


# ─────────────────────────────────────────────
# QUANTITY CALCULATION
# ─────────────────────────────────────────────

def calculate_quantity(symbol, yf_ticker):
    """
    Calculate shares to buy:
      total_value = CASH_PER_ETF x MTF_LEVERAGE
      quantity    = floor(total_value / last_close)

    Uses last available daily price from yfinance.
    Returns: int or None
    """
    try:
        log.info(f"    [QTY] Fetching price for {symbol}...")
        df = yf.download(
            yf_ticker,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df is None or df.empty:
            log.error(
                f"    [QTY-ERROR] {symbol} | "
                f"No price data from yfinance | "
                f"Cannot calculate quantity"
            )
            return None

        price = float(df["Close"].dropna().iloc[-1])

        if price <= 0:
            log.error(
                f"    [QTY-ERROR] {symbol} | "
                f"Price is 0 or negative: {price}"
            )
            return None

        total_value = CASH_PER_ETF * MTF_LEVERAGE
        quantity    = math.floor(total_value / price)

        log.info(
            f"    [QTY] {symbol} | "
            f"Price: Rs.{price:.2f} | "
            f"Rs.{CASH_PER_ETF} x {MTF_LEVERAGE}x = Rs.{total_value} | "
            f"Quantity: {quantity} units"
        )

        if quantity <= 0:
            log.warning(
                f"    [QTY-WARN] {symbol} | "
                f"Quantity is 0 — price Rs.{price:.2f} too high for "
                f"Rs.{CASH_PER_ETF} x {MTF_LEVERAGE}x = Rs.{total_value} | "
                f"Increase CASH_PER_ETF to fix"
            )
            return None

        return quantity

    except Exception as e:
        log.error(
            f"    [QTY-ERROR] {symbol} | "
            f"Exception: {e}"
        )
        return None


# ─────────────────────────────────────────────
# ORDER PLACEMENT
# ─────────────────────────────────────────────

def place_entry_order(symbol, quantity):
    """Place BUY MARKET order for MTF entry."""
    log.info(
        f"    [ORDER] Placing BUY | "
        f"{symbol} | Qty: {quantity} | "
        f"Product: {PRODUCT} | Type: MARKET"
    )
    try:
        response = client.placeorder(
            strategy=STRATEGY_NAME,
            symbol=symbol,
            action="BUY",
            exchange=EXCHANGE,
            price_type="MARKET",
            product=PRODUCT,
            quantity=str(quantity),
            price="0",
            trigger_price="0",
            disclosed_quantity="0"
        )
        log.info(
            f"    [ORDER-OK] ENTRY placed | "
            f"{symbol} | Qty: {quantity} | Response: {response}"
        )
        return response
    except Exception as e:
        log.error(
            f"    [ORDER-ERROR] ENTRY failed | "
            f"{symbol} | Error: {e}"
        )
        return None


def place_exit_order(symbol, quantity):
    """Place SELL MARKET order for full exit."""
    log.info(
        f"    [ORDER] Placing SELL | "
        f"{symbol} | Qty: {quantity} | "
        f"Product: {PRODUCT} | Type: MARKET"
    )
    try:
        response = client.placeorder(
            strategy=STRATEGY_NAME,
            symbol=symbol,
            action="SELL",
            exchange=EXCHANGE,
            price_type="MARKET",
            product=PRODUCT,
            quantity=str(quantity),
            price="0",
            trigger_price="0",
            disclosed_quantity="0"
        )
        log.info(
            f"    [ORDER-OK] EXIT placed | "
            f"{symbol} | Qty: {quantity} | Response: {response}"
        )
        return response
    except Exception as e:
        log.error(
            f"    [ORDER-ERROR] EXIT failed | "
            f"{symbol} | Error: {e} | "
            f"IMPORTANT: Position still open — check manually!"
        )
        return None


# ─────────────────────────────────────────────
# CORE STRATEGY LOGIC
# ─────────────────────────────────────────────

def run_strategy():
    """
    Main strategy execution.

    For each ETF:

    IF already invested:
      Check weekly MACD crossover down → exit if true

    IF not invested:
      1. Monthly filter: MACD > Signal on last closed monthly candle?
      2. Weekly trigger: MACD crossed above Signal on last closed weekly candle?
      → Both true → buy

    CANDLE RULE:
      iloc[-1] = last closed candle (always, for all timeframes)
      iloc[-2] = candle before that
      No time/date logic needed — yfinance handles it.
    """
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    log.info("=" * 60)
    log.info(f"[STRATEGY] RUN START | {now_ist}")
    log.info(f"[STRATEGY] ETFs: {list(ETF_LIST.keys())}")
    log.info(
        f"[STRATEGY] Config | "
        f"Cash: Rs.{CASH_PER_ETF} | "
        f"Leverage: {MTF_LEVERAGE}x | "
        f"Total/ETF: Rs.{CASH_PER_ETF * MTF_LEVERAGE} | "
        f"Product: {PRODUCT}"
    )
    log.info("=" * 60)

    # Step 1 — Get invested ETFs
    log.info("[STEP-1] Checking current ETF positions in OpenAlgo...")
    invested_etfs = get_invested_etfs()

    # Step 2 — Process each ETF
    log.info(f"[STEP-2] Scanning {len(ETF_LIST)} ETFs...")

    entry_count = 0
    exit_count  = 0
    skip_count  = 0

    for symbol, yf_ticker in ETF_LIST.items():
        log.info("-" * 50)
        log.info(f"[ETF] {symbol} ({yf_ticker})")

        time.sleep(FETCH_DELAY)

        # ── CASE 1: Invested → check exit ──
        if symbol in invested_etfs:
            held_qty = invested_etfs[symbol]
            log.info(
                f"  [STATUS] INVESTED | "
                f"Held qty: {held_qty} | "
                f"Checking exit..."
            )

            exit_signal = check_weekly_crossover_down(symbol, yf_ticker)
            if exit_signal:
                log.info(
                    f"  [EXIT-SIGNAL] Weekly MACD crossover DOWN | "
                    f"{symbol} | Exiting {held_qty} units"
                )
                place_exit_order(symbol, held_qty)
                exit_count += 1
            else:
                log.info(
                    f"  [HOLD] {symbol} | "
                    f"Qty: {held_qty} | No exit signal"
                )

        # ── CASE 2: Not invested → check entry ──
        else:
            log.info(f"  [STATUS] NOT INVESTED | Checking entry...")

            # Monthly filter
            log.info(f"  [CHECK] Monthly MACD filter for {symbol}...")
            monthly_ok = is_monthly_bullish(symbol, yf_ticker)
            if not monthly_ok:
                log.info(
                    f"  [SKIP] {symbol} | "
                    f"Monthly MACD not bullish — trend filter failed"
                )
                skip_count += 1
                continue

            # Weekly crossover
            log.info(f"  [CHECK] Weekly MACD crossover for {symbol}...")
            weekly_ok = check_weekly_crossover_up(symbol, yf_ticker)
            if not weekly_ok:
                log.info(
                    f"  [SKIP] {symbol} | "
                    f"Monthly OK but no weekly crossover yet"
                )
                skip_count += 1
                continue

            # Both conditions met
            log.info(
                f"  [ENTRY-SIGNAL] {symbol} | "
                f"Monthly bullish + Weekly crossover UP"
            )

            qty = calculate_quantity(symbol, yf_ticker)
            if qty is None:
                log.warning(
                    f"  [SKIP] {symbol} | "
                    f"Could not calculate quantity"
                )
                continue

            place_entry_order(symbol, qty)
            entry_count += 1

    log.info("=" * 60)
    log.info(
        f"[STRATEGY] RUN COMPLETE | "
        f"{datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}"
    )
    log.info(
        f"[SUMMARY] "
        f"Entries: {entry_count} | "
        f"Exits: {exit_count} | "
        f"Skipped: {skip_count} | "
        f"Held: {len(invested_etfs)}"
    )
    log.info("=" * 60)


# ─────────────────────────────────────────────
# MAIN — runs immediately on startup
# ─────────────────────────────────────────────

def main():
    """
    Runs strategy immediately when you start it.
    No fixed time — just open OpenAlgo and click Run.
    Works correctly for any run time or day.
    """
    log.info("[INIT] MACD ETF Strategy v2 starting...")
    log.info(
        f"[INIT] Config | "
        f"Cash: Rs.{CASH_PER_ETF}/ETF | "
        f"Leverage: {MTF_LEVERAGE}x | "
        f"Product: {PRODUCT} | "
        f"ETFs: {list(ETF_LIST.keys())}"
    )
    log.info(
        "[INIT] Candle rule: iloc[-1] always = last closed candle | "
        "Safe for any run time or day"
    )

    run_strategy()

    log.info("[DONE] Strategy complete. You can close this.")


if __name__ == "__main__":
    main()
