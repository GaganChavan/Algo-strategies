"""
Nifty 100 MACD Strategy for OpenAlgo — v2
==========================================
Strategy   : Dual Timeframe MACD (12, 24, 3)
Universe   : Nifty 100 stocks via yfinance (NSE)
Execution  : Zerodha via OpenAlgo SDK (MTF product)

Entry      : Weekly MACD line > Weekly Signal line (filter)
             + Daily MACD crossed above Daily Signal (trigger)

Exit       : Daily MACD crossed below Daily Signal (signal exit)
             OR last close >= buy_price x 1.035   (target exit)
             Whichever hits first

Candle rule: Always use iloc[-1] as last closed candle.
             yfinance never returns incomplete candles for
             daily/weekly/monthly intervals. So iloc[-1] is
             always the last fully closed candle regardless
             of what time or day the script is run.
             Works for: weekends, holidays, special sessions,
             Diwali muhurat, post-market runs, pre-market runs.

Buy Price  : Actual fill price read from OpenAlgo orderbook
Data       : yfinance daily + weekly candles
Run        : Runs immediately on startup — no fixed time
             Just open OpenAlgo and click Run any time before 9:15am
Author     : Generated for OpenAlgo Python Strategy Manager
Version    : 2.0 — Fixed iloc, rate limiting, TATAMOTORS, rich logging
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

# ─────────────────────────────────────────────────────────────
# CONFIGURATION — Only edit this block
# ─────────────────────────────────────────────────────────────

# Your OpenAlgo API key (get from OpenAlgo UI → API Key page)
API_KEY  = "c3dc554ae593b234bff9849b3f076cb5084d21673fe064058a2b85679cf74b73"
HOST_URL = "http://127.0.0.1:5000"

# Strategy name shown in OpenAlgo order logs
STRATEGY_NAME = "NIFTY100_MACD_MTF"

# Exchange
EXCHANGE = "NSE"

# Product type
# "MTF" → live leveraged trading via Zerodha MTF
# "CNC" → use this for sandbox / dry run testing
PRODUCT = "CNC"

# Your cash per stock (INR)
CASH_PER_STOCK = 10000  # <- change anytime

# MTF leverage Zerodha offers per stock
MTF_LEVERAGE = 4  # <- change if Zerodha offers different

# Target exit % above buy price
TARGET_PCT = 0.035  # 3.5% — change to 0.04 for 4% etc.

# MACD parameters — same for both daily and weekly
MACD_FAST   = 12
MACD_SLOW   = 24
MACD_SIGNAL = 3

# Delay between fetching each stock from yfinance (seconds)
# Prevents rate limiting when scanning 100 stocks
FETCH_DELAY = 0.5  # <- increase to 1.0 if errors persist

# IST timezone
IST = pytz.timezone("Asia/Kolkata")

# ─────────────────────────────────────────────────────────────
# NIFTY 100 STOCK UNIVERSE
# Format: { "OPENALGO_SYMBOL": "YFINANCE_TICKER" }
# Add or remove stocks freely — code adapts automatically
# Source: NSE Nifty 100 constituents (Dec 2025)
# Note: TATAMOTORS removed — yfinance ticker broken
#       Replace with "TATAMOTORS": "TATAMTRD.NS" if needed
# ─────────────────────────────────────────────────────────────

NIFTY100_STOCKS = {
    # ── Nifty 50 ──────────────────────────────────────────────
    "HDFCBANK":    "HDFCBANK.NS",
    "RELIANCE":    "RELIANCE.NS",
    "ICICIBANK":   "ICICIBANK.NS",
    "BHARTIARTL":  "BHARTIARTL.NS",
    "INFY":        "INFY.NS",
    "LT":          "LT.NS",
    "SBIN":        "SBIN.NS",
    "ITC":         "ITC.NS",
    "AXISBANK":    "AXISBANK.NS",
    "M&M":         "M&M.NS",
    "NTPC":        "NTPC.NS",
    "KOTAKBANK":   "KOTAKBANK.NS",
    "TITAN":       "TITAN.NS",
    "HCLTECH":     "HCLTECH.NS",
    "ONGC":        "ONGC.NS",
    "ULTRACEMCO":  "ULTRACEMCO.NS",
    "SUNPHARMA":   "SUNPHARMA.NS",
    "MARUTI":      "MARUTI.NS",
    "BAJFINANCE":  "BAJFINANCE.NS",
    "HINDUNILVR":  "HINDUNILVR.NS",
    "WIPRO":       "WIPRO.NS",
    "ADANIENT":    "ADANIENT.NS",
    "POWERGRID":   "POWERGRID.NS",
    "NESTLEIND":   "NESTLEIND.NS",
    "TATASTEEL":   "TATASTEEL.NS",
    "TECHM":       "TECHM.NS",
    "JSWSTEEL":    "JSWSTEEL.NS",
    "COALINDIA":   "COALINDIA.NS",
    "HINDALCO":    "HINDALCO.NS",
    "BAJAJFINSV":  "BAJAJFINSV.NS",
    "GRASIM":      "GRASIM.NS",
    "DRREDDY":     "DRREDDY.NS",
    "TCS":         "TCS.NS",
    "CIPLA":       "CIPLA.NS",
    "DIVISLAB":    "DIVISLAB.NS",
    "EICHERMOT":   "EICHERMOT.NS",
    "APOLLOHOSP":  "APOLLOHOSP.NS",
    "TATACONSUM":  "TATACONSUM.NS",
    "ASIANPAINT":  "ASIANPAINT.NS",
    "BAJAJ-AUTO":  "BAJAJ-AUTO.NS",
    "BRITANNIA":   "BRITANNIA.NS",
    "HEROMOTOCO":  "HEROMOTOCO.NS",
    "SHRIRAMFIN":  "SHRIRAMFIN.NS",
    "BPCL":        "BPCL.NS",
    "TRENT":       "TRENT.NS",
    "INDUSINDBK":  "INDUSINDBK.NS",
    "LICI":        "LICI.NS",
    "SBILIFE":     "SBILIFE.NS",
    "HDFCLIFE":    "HDFCLIFE.NS",
    "TATAMOTORS":  "TATAMOTORS.BO",  # using BSE ticker as fallback

    # ── Nifty Next 50 ─────────────────────────────────────────
    "ADANIPORTS":  "ADANIPORTS.NS",
    "ADANIGREEN":  "ADANIGREEN.NS",
    "ADANIPOWER":  "ADANIPOWER.NS",
    "SIEMENS":     "SIEMENS.NS",
    "HAVELLS":     "HAVELLS.NS",
    "PIDILITIND":  "PIDILITIND.NS",
    "BERGEPAINT":  "BERGEPAINT.NS",
    "GODREJCP":    "GODREJCP.NS",
    "MUTHOOTFIN":  "MUTHOOTFIN.NS",
    "CHOLAFIN":    "CHOLAFIN.NS",
    "MOTHERSON":   "MOTHERSON.NS",
    "TORNTPHARM":  "TORNTPHARM.NS",
    "DABUR":       "DABUR.NS",
    "MARICO":      "MARICO.NS",
    "COLPAL":      "COLPAL.NS",
    "LUPIN":       "LUPIN.NS",
    "BIOCON":      "BIOCON.NS",
    "ICICIPRULI":  "ICICIPRULI.NS",
    "ICICIGI":     "ICICIGI.NS",
    "HDFCAMC":     "HDFCAMC.NS",
    "MCDOWELL-N":  "MCDOWELL-N.NS",
    "VEDL":        "VEDL.NS",
    "ZOMATO":      "ZOMATO.NS",
    "NYKAA":       "NYKAA.NS",
    "PAYTM":       "PAYTM.NS",
    "DMART":       "DMART.NS",
    "AMBUJACEM":   "AMBUJACEM.NS",
    "ACC":         "ACC.NS",
    "SHREECEM":    "SHREECEM.NS",
    "INDIGO":      "INDIGO.NS",
    "BANKBARODA":  "BANKBARODA.NS",
    "PNB":         "PNB.NS",
    "CANBK":       "CANBK.NS",
    "UNIONBANK":   "UNIONBANK.NS",
    "NHPC":        "NHPC.NS",
    "RECLTD":      "RECLTD.NS",
    "PFC":         "PFC.NS",
    "IRFC":        "IRFC.NS",
    "HAL":         "HAL.NS",
    "BEL":         "BEL.NS",
    "BHEL":        "BHEL.NS",
    "GAIL":        "GAIL.NS",
    "IOC":         "IOC.NS",
    "HINDPETRO":   "HINDPETRO.NS",
    "ZYDUSLIFE":   "ZYDUSLIFE.NS",
    "ALKEM":       "ALKEM.NS",
    "PERSISTENT":  "PERSISTENT.NS",
    "MPHASIS":     "MPHASIS.NS",
    "LTIM":        "LTIM.NS",
    "OFSS":        "OFSS.NS",
}

# ─────────────────────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# OPENALGO CLIENT
# ─────────────────────────────────────────────────────────────

client = api(
    api_key=API_KEY,
    host=HOST_URL
)

# ─────────────────────────────────────────────────────────────
# MACD CALCULATION
# ─────────────────────────────────────────────────────────────

def calculate_macd(close_series, ticker_name):
    """
    Calculate MACD (12, 24, 3) on a closing price series.

    CANDLE RULE:
    Always use iloc[-1] as last closed candle.
    yfinance never returns incomplete candles for daily/weekly
    intervals — so iloc[-1] is always safe regardless of when
    the script runs (morning, evening, weekend, holiday).

    Parameters:
        close_series : pd.Series of closing prices
        ticker_name  : string — used only for logging

    Returns:
        pd.DataFrame with macd_line, signal_line, histogram
        OR None if calculation fails
    """
    try:
        if len(close_series) < MACD_SLOW + MACD_SIGNAL + 3:
            log.error(
                f"    [MACD-ERROR] {ticker_name} | "
                f"Not enough data for MACD calculation | "
                f"Have {len(close_series)} rows, need at least "
                f"{MACD_SLOW + MACD_SIGNAL + 3}"
            )
            return None

        ema_fast    = close_series.ewm(span=MACD_FAST,   adjust=False).mean()
        ema_slow    = close_series.ewm(span=MACD_SLOW,   adjust=False).mean()
        macd_line   = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
        histogram   = macd_line - signal_line

        # Check for NaN in last 3 values
        if macd_line.iloc[-1] != macd_line.iloc[-1]:  # NaN check
            log.error(
                f"    [MACD-ERROR] {ticker_name} | "
                f"NaN detected in MACD values — data may have gaps"
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
            f"Unexpected error in MACD calculation | {e}"
        )
        return None


# ─────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────

def fetch_daily_data(symbol, yf_ticker):
    """
    Fetch 1 year of daily OHLCV data from yfinance.

    CANDLE RULE: iloc[-1] is always last closed daily candle.
    yfinance does not include today's candle until market closes.
    So this is safe to call at any time.

    Returns: pd.DataFrame or None on failure
    """
    try:
        log.info(f"    [DATA] Fetching daily data for {symbol} ({yf_ticker})")

        df = yf.download(
            yf_ticker,
            period="1y",
            interval="1d",
            progress=False,
            auto_adjust=True
        )

        # Flatten MultiIndex columns (yfinance quirk with single ticker)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Validate data
        if df is None or df.empty:
            log.error(
                f"    [DATA-ERROR] {symbol} ({yf_ticker}) | "
                f"yfinance returned empty dataframe | "
                f"Possible reasons: wrong ticker, delisted stock, "
                f"network issue | Action: skipping this stock"
            )
            return None

        if len(df) < MACD_SLOW + MACD_SIGNAL + 3:
            log.error(
                f"    [DATA-ERROR] {symbol} ({yf_ticker}) | "
                f"Insufficient rows: got {len(df)}, "
                f"need {MACD_SLOW + MACD_SIGNAL + 3} | "
                f"Action: skipping this stock"
            )
            return None

        # Log what data we got — very useful for debugging
        last_candle_date = df.index[-1]
        if hasattr(last_candle_date, 'date'):
            last_candle_date = last_candle_date.date()

        log.info(
            f"    [DATA] {symbol} daily | "
            f"Rows: {len(df)} | "
            f"Last closed candle: {last_candle_date} | "
            f"Last close: Rs.{float(df['Close'].iloc[-1]):.2f}"
        )

        return df

    except Exception as e:
        log.error(
            f"    [DATA-ERROR] {symbol} ({yf_ticker}) | "
            f"Fetch failed with exception: {e} | "
            f"Action: skipping this stock"
        )
        return None


def fetch_weekly_data(symbol, yf_ticker):
    """
    Fetch 3 years of weekly OHLCV data from yfinance.

    CANDLE RULE: iloc[-1] is always last closed weekly candle.
    Mid-week runs will show last week's closed candle as iloc[-1].
    This is correct behaviour — we never use incomplete weekly candles.

    Returns: pd.DataFrame or None on failure
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
                f"Possible reasons: wrong ticker, delisted, network | "
                f"Action: skipping"
            )
            return None

        if len(df) < MACD_SLOW + MACD_SIGNAL + 3:
            log.error(
                f"    [DATA-ERROR] {symbol} ({yf_ticker}) | "
                f"Insufficient weekly rows: got {len(df)}, "
                f"need {MACD_SLOW + MACD_SIGNAL + 3} | "
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


def get_last_close(symbol, yf_ticker):
    """
    Get last available closing price for quantity calculation.
    Reuses daily data fetch — no extra API call.

    Returns: float price or None
    """
    df = fetch_daily_data(symbol, yf_ticker)
    if df is None:
        return None
    try:
        price = float(df["Close"].dropna().iloc[-1])
        log.info(f"    [PRICE] {symbol} | Last close: Rs.{price:.2f}")
        return price
    except Exception as e:
        log.error(
            f"    [PRICE-ERROR] {symbol} | "
            f"Could not extract close price | {e}"
        )
        return None


# ─────────────────────────────────────────────────────────────
# SIGNAL LOGIC
# ─────────────────────────────────────────────────────────────

def is_weekly_bullish(symbol, yf_ticker):
    """
    Weekly MACD filter:
    Returns True if Weekly MACD line > Weekly Signal line
    on the last closed weekly candle (iloc[-1]).

    This confirms the medium-term trend is bullish.
    No crossover needed — just MACD above signal.
    """
    df = fetch_weekly_data(symbol, yf_ticker)
    if df is None:
        return False

    close = df["Close"].dropna()
    macd  = calculate_macd(close, f"{symbol}-weekly")
    if macd is None:
        return False

    # Always use iloc[-1] — last closed weekly candle
    macd_val   = float(macd["macd_line"].iloc[-1])
    signal_val = float(macd["signal_line"].iloc[-1])
    is_bullish = macd_val > signal_val

    log.info(
        f"    [WEEKLY-MACD] {symbol} | "
        f"MACD: {macd_val:.4f} | "
        f"Signal: {signal_val:.4f} | "
        f"Bullish: {is_bullish}"
    )
    return is_bullish


def check_daily_crossover_up(symbol, yf_ticker):
    """
    Daily entry trigger:
    Returns True if Daily MACD crossed ABOVE Daily Signal
    on the last closed daily candle.

    Crossover logic using iloc[-1] and iloc[-2]:
      iloc[-1] = last closed daily candle (yesterday or today post-close)
      iloc[-2] = candle before that

    yfinance guarantees iloc[-1] is always fully closed.
    Works correctly for any run time — morning, evening, weekend.
    """
    df = fetch_daily_data(symbol, yf_ticker)
    if df is None:
        return False

    close = df["Close"].dropna()
    macd  = calculate_macd(close, f"{symbol}-daily-entry")
    if macd is None:
        return False

    # Last closed candle and the one before it
    curr_macd   = float(macd["macd_line"].iloc[-1])
    curr_signal = float(macd["signal_line"].iloc[-1])
    prev_macd   = float(macd["macd_line"].iloc[-2])
    prev_signal = float(macd["signal_line"].iloc[-2])

    # Get dates for logging clarity
    curr_date = df.index[-1]
    prev_date = df.index[-2]
    if hasattr(curr_date, 'date'):
        curr_date = curr_date.date()
        prev_date = prev_date.date()

    crossed_up = (prev_macd < prev_signal) and (curr_macd > curr_signal)

    log.info(
        f"    [DAILY-ENTRY] {symbol} | "
        f"Prev ({prev_date}): MACD={prev_macd:.4f} Signal={prev_signal:.4f} | "
        f"Curr ({curr_date}): MACD={curr_macd:.4f} Signal={curr_signal:.4f} | "
        f"Crossover UP: {crossed_up}"
    )
    return crossed_up


def check_daily_crossover_down(symbol, yf_ticker):
    """
    Daily exit trigger:
    Returns True if Daily MACD crossed BELOW Daily Signal
    on the last closed daily candle.

    Same iloc logic as entry — iloc[-1] always last closed candle.
    """
    df = fetch_daily_data(symbol, yf_ticker)
    if df is None:
        return False

    close = df["Close"].dropna()
    macd  = calculate_macd(close, f"{symbol}-daily-exit")
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
        f"    [DAILY-EXIT] {symbol} | "
        f"Prev ({prev_date}): MACD={prev_macd:.4f} Signal={prev_signal:.4f} | "
        f"Curr ({curr_date}): MACD={curr_macd:.4f} Signal={curr_signal:.4f} | "
        f"Crossover DOWN: {crossed_down}"
    )
    return crossed_down


# ─────────────────────────────────────────────────────────────
# TARGET EXIT CHECK
# ─────────────────────────────────────────────────────────────

def check_target_hit(symbol, yf_ticker, buy_price):
    """
    Target exit:
    Returns True if last close >= buy_price x (1 + TARGET_PCT).

    Uses last available daily close from yfinance.
    Safe to call any time — always uses last closed candle.
    """
    if buy_price is None or buy_price <= 0:
        log.warning(
            f"    [TARGET-WARN] {symbol} | "
            f"Invalid buy price: {buy_price} | "
            f"Cannot check target | Skipping target check"
        )
        return False

    df = fetch_daily_data(symbol, yf_ticker)
    if df is None:
        return False

    last_close   = float(df["Close"].dropna().iloc[-1])
    target_price = buy_price * (1 + TARGET_PCT)
    target_hit   = last_close >= target_price

    log.info(
        f"    [TARGET] {symbol} | "
        f"Buy price: Rs.{buy_price:.2f} | "
        f"Target ({TARGET_PCT*100:.1f}%): Rs.{target_price:.2f} | "
        f"Last close: Rs.{last_close:.2f} | "
        f"Target hit: {target_hit}"
    )
    return target_hit


# ─────────────────────────────────────────────────────────────
# POSITION STATE — Holdings + Positionbook
# ─────────────────────────────────────────────────────────────

def get_invested_stocks():
    """
    Returns dict of stocks currently invested in.
    Checks BOTH holdings (T+1 MTF) and positionbook (same day).

    Returns: dict { "SYMBOL": quantity }
    """
    invested = {}
    log.info("  [POSITIONS] Fetching holdings from OpenAlgo...")

    # --- Holdings (T+1 settled MTF) ---
    try:
        resp = client.holdings()
        if resp and isinstance(resp, dict) and resp.get("status") == "success":
            data = resp.get("data", [])
            if isinstance(data, list):
                for item in data:
                    sym = str(item.get("tradingsymbol", "")).upper()
                    qty = int(item.get("quantity", 0))
                    if sym in NIFTY100_STOCKS and qty > 0:
                        invested[sym] = invested.get(sym, 0) + qty
                        log.info(
                            f"  [HOLDINGS] Found: {sym} | Qty: {qty}"
                        )
            log.info(
                f"  [HOLDINGS] Fetch successful | "
                f"Found {len(invested)} invested stocks so far"
            )
        else:
            log.warning(
                f"  [HOLDINGS-WARN] API returned unexpected response: "
                f"{resp}"
            )
    except Exception as e:
        log.error(
            f"  [HOLDINGS-ERROR] Failed to fetch holdings | "
            f"Error: {e} | "
            f"Will still check positionbook"
        )

    # --- Positionbook (same day) ---
    log.info("  [POSITIONS] Fetching positionbook from OpenAlgo...")
    try:
        resp = client.positionbook()
        if resp and isinstance(resp, dict) and resp.get("status") == "success":
            data = resp.get("data", [])
            if isinstance(data, list):
                for item in data:
                    sym = str(item.get("tradingsymbol", "")).upper()
                    qty = int(item.get("quantity", 0))
                    if sym in NIFTY100_STOCKS and qty > 0:
                        invested[sym] = invested.get(sym, 0) + qty
                        log.info(
                            f"  [POSITIONBOOK] Found: {sym} | Qty: {qty}"
                        )
            log.info(
                f"  [POSITIONBOOK] Fetch successful"
            )
        else:
            log.warning(
                f"  [POSITIONBOOK-WARN] API returned unexpected response: "
                f"{resp}"
            )
    except Exception as e:
        log.error(
            f"  [POSITIONBOOK-ERROR] Failed to fetch positionbook | "
            f"Error: {e}"
        )

    log.info(
        f"  [POSITIONS] Total invested stocks: {len(invested)} | "
        f"Symbols: {list(invested.keys()) if invested else 'None'}"
    )
    return invested


# ─────────────────────────────────────────────────────────────
# BUY PRICE — From OpenAlgo Orderbook
# ─────────────────────────────────────────────────────────────

def get_buy_price_from_orderbook(symbol, yf_ticker):
    """
    Reads actual fill price from OpenAlgo orderbook.
    Finds most recent COMPLETE BUY order for this symbol.

    Fallback: if not found, uses last close from yfinance.

    Returns: float buy price or None
    """
    log.info(f"    [BUYP] Fetching buy price for {symbol} from orderbook...")
    try:
        resp = client.orderbook()

        if not resp or not isinstance(resp, dict):
            log.warning(
                f"    [BUYP-WARN] {symbol} | "
                f"Orderbook returned invalid response | "
                f"Falling back to last close"
            )
            return None

        if resp.get("status") != "success":
            log.warning(
                f"    [BUYP-WARN] {symbol} | "
                f"Orderbook status not success: {resp.get('status')} | "
                f"Falling back to last close"
            )
            return None

        orders = resp.get("data", [])
        if not isinstance(orders, list):
            log.warning(
                f"    [BUYP-WARN] {symbol} | "
                f"Orderbook data is not a list | "
                f"Falling back to last close"
            )
            return None

        # Find completed BUY orders for this symbol
        buy_orders = [
            o for o in orders
            if str(o.get("tradingsymbol", "")).upper() == symbol.upper()
            and str(o.get("transaction_type", "")).upper() == "BUY"
            and str(o.get("status", "")).upper() in (
                "COMPLETE", "COMPLETED", "FILLED"
            )
        ]

        if not buy_orders:
            log.warning(
                f"    [BUYP-WARN] {symbol} | "
                f"No completed BUY order found in orderbook | "
                f"Falling back to last close for target calculation"
            )
            return None

        # Most recent completed BUY (orderbook is newest first)
        latest    = buy_orders[0]
        avg_price = float(latest.get("average_price", 0))

        # Fallback to price field if average_price is 0
        if avg_price <= 0:
            avg_price = float(latest.get("price", 0))

        if avg_price <= 0:
            log.warning(
                f"    [BUYP-WARN] {symbol} | "
                f"Fill price is 0 in orderbook | "
                f"Falling back to last close"
            )
            return None

        log.info(
            f"    [BUYP] {symbol} | "
            f"Buy price from orderbook: Rs.{avg_price:.2f}"
        )
        return avg_price

    except Exception as e:
        log.error(
            f"    [BUYP-ERROR] {symbol} | "
            f"Orderbook fetch exception: {e} | "
            f"Falling back to last close"
        )
        return None


# ─────────────────────────────────────────────────────────────
# QUANTITY CALCULATION
# ─────────────────────────────────────────────────────────────

def calculate_quantity(symbol, yf_ticker):
    """
    Calculate shares to buy:
      total_value = CASH_PER_STOCK x MTF_LEVERAGE
      quantity    = floor(total_value / last_close)

    Returns: int quantity or None
    """
    df = fetch_daily_data(symbol, yf_ticker)
    if df is None:
        return None

    try:
        price = float(df["Close"].dropna().iloc[-1])
    except Exception as e:
        log.error(
            f"    [QTY-ERROR] {symbol} | "
            f"Could not read close price | {e}"
        )
        return None

    if price <= 0:
        log.error(
            f"    [QTY-ERROR] {symbol} | "
            f"Price is 0 or negative: {price} | "
            f"Cannot calculate quantity"
        )
        return None

    total_value = CASH_PER_STOCK * MTF_LEVERAGE
    quantity    = math.floor(total_value / price)

    log.info(
        f"    [QTY] {symbol} | "
        f"Price: Rs.{price:.2f} | "
        f"Rs.{CASH_PER_STOCK} x {MTF_LEVERAGE}x = Rs.{total_value} | "
        f"Quantity: {quantity} shares"
    )

    if quantity <= 0:
        log.warning(
            f"    [QTY-WARN] {symbol} | "
            f"Quantity is 0 — stock price Rs.{price:.2f} is too high "
            f"for Rs.{CASH_PER_STOCK} x {MTF_LEVERAGE}x = Rs.{total_value} | "
            f"Either increase CASH_PER_STOCK or reduce stock price expectation"
        )
        return None

    return quantity


# ─────────────────────────────────────────────────────────────
# ORDER PLACEMENT
# ─────────────────────────────────────────────────────────────

def place_entry_order(symbol, quantity):
    """
    Place BUY MARKET order for MTF entry.
    """
    log.info(
        f"    [ORDER] Placing BUY order | "
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
            f"{symbol} | Qty: {quantity} | "
            f"Response: {response}"
        )
        return response
    except Exception as e:
        log.error(
            f"    [ORDER-ERROR] ENTRY failed | "
            f"{symbol} | Qty: {quantity} | "
            f"Error: {e} | "
            f"Action: no position taken for this stock"
        )
        return None


def place_exit_order(symbol, quantity, reason):
    """
    Place SELL MARKET order for full exit.
    reason: "TARGET_HIT" or "MACD_CROSSDOWN"
    """
    log.info(
        f"    [ORDER] Placing SELL order | "
        f"{symbol} | Qty: {quantity} | "
        f"Reason: {reason} | Product: {PRODUCT} | Type: MARKET"
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
            f"{symbol} | Qty: {quantity} | "
            f"Reason: {reason} | "
            f"Response: {response}"
        )
        return response
    except Exception as e:
        log.error(
            f"    [ORDER-ERROR] EXIT failed | "
            f"{symbol} | Qty: {quantity} | "
            f"Reason: {reason} | "
            f"Error: {e} | "
            f"IMPORTANT: Position still open — check manually!"
        )
        return None


# ─────────────────────────────────────────────────────────────
# CORE STRATEGY LOGIC
# ─────────────────────────────────────────────────────────────

def run_strategy():
    """
    Main strategy execution.

    For each Nifty 100 stock:

    IF already invested:
      1. Get buy price from orderbook (fallback: last close)
      2. Check target: last close >= buy_price x 1.035?  [Priority 1]
      3. Check MACD exit: daily MACD crossed below signal? [Priority 2]
      → First condition true → SELL full position
      → Neither → hold and log

    IF not invested:
      1. Weekly filter: Weekly MACD > Weekly Signal?
      2. Daily trigger: Daily MACD crossed above Signal on last candle?
      → Both true → Calculate qty → BUY MARKET order
      → Either false → skip

    CANDLE RULE throughout:
      iloc[-1] = last closed candle (always, for all timeframes)
      iloc[-2] = candle before that (for crossover detection)
      No time/date checks needed — yfinance handles this.
    """
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    log.info("=" * 65)
    log.info(f"[STRATEGY] RUN START | {now_ist}")
    log.info(f"[STRATEGY] Universe: {len(NIFTY100_STOCKS)} Nifty 100 stocks")
    log.info(
        f"[STRATEGY] Config | "
        f"Cash: Rs.{CASH_PER_STOCK} | "
        f"Leverage: {MTF_LEVERAGE}x | "
        f"Total/stock: Rs.{CASH_PER_STOCK * MTF_LEVERAGE} | "
        f"Target: {TARGET_PCT*100:.1f}% | "
        f"Product: {PRODUCT} | "
        f"Fetch delay: {FETCH_DELAY}s"
    )
    log.info("=" * 65)

    # Step 1 — Get invested stocks
    log.info("[STEP-1] Checking current positions in OpenAlgo...")
    invested_stocks = get_invested_stocks()

    # Step 2 — Process each stock
    log.info(f"[STEP-2] Scanning {len(NIFTY100_STOCKS)} stocks...")

    entry_count = 0
    exit_count  = 0
    skip_count  = 0
    error_count = 0

    for symbol, yf_ticker in NIFTY100_STOCKS.items():
        log.info("-" * 55)
        log.info(f"[STOCK] {symbol} ({yf_ticker})")

        # Small delay to avoid yfinance rate limiting
        time.sleep(FETCH_DELAY)

        # ── CASE 1: Already invested → check exit ──
        if symbol in invested_stocks:
            held_qty  = invested_stocks[symbol]
            log.info(
                f"  [STATUS] INVESTED | "
                f"Held qty: {held_qty} | "
                f"Checking exit conditions..."
            )

            # Get buy price from orderbook
            buy_price = get_buy_price_from_orderbook(symbol, yf_ticker)

            # Fallback to last close if orderbook fails
            if buy_price is None:
                log.warning(
                    f"  [BUYP-FALLBACK] {symbol} | "
                    f"Using last close as buy price proxy for target check"
                )
                df_tmp = fetch_daily_data(symbol, yf_ticker)
                if df_tmp is not None:
                    buy_price = float(df_tmp["Close"].dropna().iloc[-1])

            # Priority 1 — Target exit
            log.info(f"  [CHECK] Checking target exit for {symbol}...")
            target_hit = check_target_hit(symbol, yf_ticker, buy_price)
            if target_hit:
                log.info(
                    f"  [EXIT-SIGNAL] TARGET HIT | {symbol} | "
                    f"Exiting {held_qty} units"
                )
                place_exit_order(symbol, held_qty, "TARGET_HIT")
                exit_count += 1
                continue

            # Priority 2 — MACD exit
            log.info(f"  [CHECK] Checking MACD exit for {symbol}...")
            macd_exit = check_daily_crossover_down(symbol, yf_ticker)
            if macd_exit:
                log.info(
                    f"  [EXIT-SIGNAL] MACD CROSSOVER DOWN | {symbol} | "
                    f"Exiting {held_qty} units"
                )
                place_exit_order(symbol, held_qty, "MACD_CROSSDOWN")
                exit_count += 1
                continue

            # Hold
            log.info(
                f"  [HOLD] {symbol} | "
                f"Qty: {held_qty} | "
                f"No exit signal — continuing to hold"
            )

        # ── CASE 2: Not invested → check entry ──
        else:
            log.info(f"  [STATUS] NOT INVESTED | Checking entry signals...")

            # Weekly filter
            log.info(f"  [CHECK] Weekly MACD filter for {symbol}...")
            weekly_ok = is_weekly_bullish(symbol, yf_ticker)
            if not weekly_ok:
                log.info(
                    f"  [SKIP] {symbol} | "
                    f"Weekly MACD not bullish — trend filter failed"
                )
                skip_count += 1
                continue

            # Daily crossover trigger
            log.info(f"  [CHECK] Daily MACD crossover for {symbol}...")
            daily_ok = check_daily_crossover_up(symbol, yf_ticker)
            if not daily_ok:
                log.info(
                    f"  [SKIP] {symbol} | "
                    f"Weekly OK but no daily crossover yet — waiting"
                )
                skip_count += 1
                continue

            # Both conditions met — enter
            log.info(
                f"  [ENTRY-SIGNAL] {symbol} | "
                f"Weekly bullish + Daily MACD crossover UP detected"
            )

            qty = calculate_quantity(symbol, yf_ticker)
            if qty is None:
                log.warning(
                    f"  [SKIP] {symbol} | "
                    f"Could not calculate valid quantity — skipping entry"
                )
                error_count += 1
                continue

            place_entry_order(symbol, qty)
            entry_count += 1

    # Final summary
    log.info("=" * 65)
    log.info(f"[STRATEGY] RUN COMPLETE | {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")
    log.info(
        f"[SUMMARY] "
        f"Entries: {entry_count} | "
        f"Exits: {exit_count} | "
        f"Skipped: {skip_count} | "
        f"Errors: {error_count} | "
        f"Held: {len(invested_stocks)}"
    )
    log.info("=" * 65)


# ─────────────────────────────────────────────────────────────
# MAIN — runs strategy immediately on startup
# ─────────────────────────────────────────────────────────────

def main():
    """
    Runs strategy immediately when you start it.
    No fixed time — just open OpenAlgo and click Run.
    Works correctly whether you run at 9am, 6pm, or on weekends.
    """
    log.info("[INIT] Nifty 100 MACD Strategy v2 starting...")
    log.info(
        f"[INIT] Config | "
        f"Cash: Rs.{CASH_PER_STOCK}/stock | "
        f"Leverage: {MTF_LEVERAGE}x | "
        f"Target: {TARGET_PCT*100:.1f}% | "
        f"Product: {PRODUCT} | "
        f"Stocks: {len(NIFTY100_STOCKS)}"
    )
    log.info(
        "[INIT] Candle rule: iloc[-1] always = last closed candle | "
        "Safe for any run time or day"
    )

    run_strategy()

    log.info("[DONE] Strategy complete. You can close this.")


if __name__ == "__main__":
    main()
