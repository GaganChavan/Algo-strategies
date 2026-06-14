"""
MACD Dual-Timeframe Backtest — Streamlit App
=============================================
Tab 1 : ETF Strategy    — Monthly filter + Weekly MACD crossover
Tab 2 : Nifty 100       — Weekly filter  + Daily  MACD crossover + Target exit

Entry  : Next candle's Open  (ETF → Monday open | Nifty 100 → next trading day open)
Costs  : Zerodha brokerage ₹20/order + STT + exchange + SEBI + stamp + GST
MTF    : Daily interest on borrowed amount at user-defined annual rate
"""

import time
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="MACD Backtest",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("📈 MACD Dual-Timeframe Backtest")
st.caption(
    "ETF Strategy (Monthly + Weekly)  |  Nifty 100 Strategy (Weekly + Daily)  |  "
    "Includes actual Zerodha costs & MTF interest"
)

RISK_FREE_RATE = 0.065  # 6.5% India — used for Sharpe / Sortino

# ─────────────────────────────────────────────────────────────
# UNIVERSE
# ─────────────────────────────────────────────────────────────

ALL_ETFS = {
    "NIFTYBEES":  "NIFTYBEES.NS",
    "JUNIORBEES": "JUNIORBEES.NS",
    "MOM100":     "MOM100.NS",
    "HDFCSML250": "HDFCSML250.NS",
    "BANKBEES":   "BANKBEES.NS",
    "ITBEES":     "ITBEES.NS",
    "PSUBNKBEES": "PSUBNKBEES.NS",
    "ICICIB22":   "ICICIB22.NS",
    "INFRABEES":  "INFRABEES.NS",
    "CONSUMBEES": "CONSUMBEES.NS",
    "PHARMABEES": "PHARMABEES.NS",
    "HEALTHIETF": "HEALTHIETF.NS",
    "MOM30IETF":  "MOM30IETF.NS",
    "ALPHA":      "ALPHA.NS",
    "MODEFENCE":  "MODEFENCE.NS",
    "ALPL30IETF": "ALPL30IETF.NS",
    "MIDCAPETF":  "MIDCAPETF.NS",
    "OILIETF":    "OILIETF.NS",
    "MOSMALL250": "MOSMALL250.NS",
    "MOVALUE":    "MOVALUE.NS",
    "GOLDBEES":   "GOLDBEES.NS",
}

NIFTY100_STOCKS = {
    "HDFCBANK":   "HDFCBANK.NS",   "RELIANCE":   "RELIANCE.NS",
    "ICICIBANK":  "ICICIBANK.NS",  "BHARTIARTL": "BHARTIARTL.NS",
    "INFY":       "INFY.NS",       "LT":         "LT.NS",
    "SBIN":       "SBIN.NS",       "ITC":        "ITC.NS",
    "AXISBANK":   "AXISBANK.NS",   "M&M":        "M&M.NS",
    "NTPC":       "NTPC.NS",       "KOTAKBANK":  "KOTAKBANK.NS",
    "TITAN":      "TITAN.NS",      "HCLTECH":    "HCLTECH.NS",
    "ONGC":       "ONGC.NS",       "ULTRACEMCO": "ULTRACEMCO.NS",
    "SUNPHARMA":  "SUNPHARMA.NS",  "MARUTI":     "MARUTI.NS",
    "BAJFINANCE": "BAJFINANCE.NS", "HINDUNILVR": "HINDUNILVR.NS",
    "WIPRO":      "WIPRO.NS",      "ADANIENT":   "ADANIENT.NS",
    "POWERGRID":  "POWERGRID.NS",  "NESTLEIND":  "NESTLEIND.NS",
    "TATASTEEL":  "TATASTEEL.NS",  "TECHM":      "TECHM.NS",
    "JSWSTEEL":   "JSWSTEEL.NS",   "COALINDIA":  "COALINDIA.NS",
    "HINDALCO":   "HINDALCO.NS",   "BAJAJFINSV": "BAJAJFINSV.NS",
    "GRASIM":     "GRASIM.NS",     "DRREDDY":    "DRREDDY.NS",
    "TCS":        "TCS.NS",        "CIPLA":      "CIPLA.NS",
    "DIVISLAB":   "DIVISLAB.NS",   "EICHERMOT":  "EICHERMOT.NS",
    "APOLLOHOSP": "APOLLOHOSP.NS", "TATACONSUM": "TATACONSUM.NS",
    "ASIANPAINT": "ASIANPAINT.NS", "BAJAJ-AUTO": "BAJAJ-AUTO.NS",
    "BRITANNIA":  "BRITANNIA.NS",  "HEROMOTOCO": "HEROMOTOCO.NS",
    "SHRIRAMFIN": "SHRIRAMFIN.NS", "BPCL":       "BPCL.NS",
    "TRENT":      "TRENT.NS",      "INDUSINDBK": "INDUSINDBK.NS",
    "LICI":       "LICI.NS",       "SBILIFE":    "SBILIFE.NS",
    "HDFCLIFE":   "HDFCLIFE.NS",   "TATAMOTORS": "TATAMOTORS.BO",
    "ADANIPORTS": "ADANIPORTS.NS", "ADANIGREEN": "ADANIGREEN.NS",
    "ADANIPOWER": "ADANIPOWER.NS", "SIEMENS":    "SIEMENS.NS",
    "HAVELLS":    "HAVELLS.NS",    "PIDILITIND": "PIDILITIND.NS",
    "BERGEPAINT": "BERGEPAINT.NS", "GODREJCP":   "GODREJCP.NS",
    "MUTHOOTFIN": "MUTHOOTFIN.NS", "CHOLAFIN":   "CHOLAFIN.NS",
    "MOTHERSON":  "MOTHERSON.NS",  "TORNTPHARM": "TORNTPHARM.NS",
    "DABUR":      "DABUR.NS",      "MARICO":     "MARICO.NS",
    "COLPAL":     "COLPAL.NS",     "LUPIN":      "LUPIN.NS",
    "BIOCON":     "BIOCON.NS",     "ICICIPRULI": "ICICIPRULI.NS",
    "ICICIGI":    "ICICIGI.NS",    "HDFCAMC":    "HDFCAMC.NS",
    "MCDOWELL-N": "MCDOWELL-N.NS", "VEDL":       "VEDL.NS",
    "ZOMATO":     "ZOMATO.NS",     "NYKAA":      "NYKAA.NS",
    "PAYTM":      "PAYTM.NS",      "DMART":      "DMART.NS",
    "AMBUJACEM":  "AMBUJACEM.NS",  "ACC":        "ACC.NS",
    "SHREECEM":   "SHREECEM.NS",   "INDIGO":     "INDIGO.NS",
    "BANKBARODA": "BANKBARODA.NS", "PNB":        "PNB.NS",
    "CANBK":      "CANBK.NS",      "UNIONBANK":  "UNIONBANK.NS",
    "NHPC":       "NHPC.NS",       "RECLTD":     "RECLTD.NS",
    "PFC":        "PFC.NS",        "IRFC":       "IRFC.NS",
    "HAL":        "HAL.NS",        "BEL":        "BEL.NS",
    "BHEL":       "BHEL.NS",       "GAIL":       "GAIL.NS",
    "IOC":        "IOC.NS",        "HINDPETRO":  "HINDPETRO.NS",
    "ZYDUSLIFE":  "ZYDUSLIFE.NS",  "ALKEM":      "ALKEM.NS",
    "PERSISTENT": "PERSISTENT.NS", "MPHASIS":    "MPHASIS.NS",
    "LTIM":       "LTIM.NS",       "OFSS":       "OFSS.NS",
}

# ─────────────────────────────────────────────────────────────
# DATA FETCHING  (cached per ticker + interval, 1-hour TTL)
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_data(ticker: str, interval: str):
    try:
        df = yf.download(ticker, period="max", interval=interval,
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df is None or df.empty:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_nifty50():
    return fetch_data("^NSEI", "1d")

# ─────────────────────────────────────────────────────────────
# MACD  (pre-computed on full series — no look-ahead bias
#        because EWM at index i only uses data 0..i)
# ─────────────────────────────────────────────────────────────

def calc_macd(close: pd.Series, fast: int, slow: int, sig: int):
    if len(close) < slow + sig + 3:
        return None
    ema_f  = close.ewm(span=fast, adjust=False).mean()
    ema_s  = close.ewm(span=slow, adjust=False).mean()
    macd   = ema_f - ema_s
    signal = macd.ewm(span=sig, adjust=False).mean()
    return pd.DataFrame({"macd": macd, "signal": signal}, index=close.index)

# ─────────────────────────────────────────────────────────────
# TRANSACTION COSTS  (Zerodha, delivery / MTF)
# ─────────────────────────────────────────────────────────────

def txn_costs(qty: int, entry: float, exit_p: float) -> float:
    """Full round-trip cost: brokerage + STT + exchange + SEBI + stamp + GST."""
    buy_val  = qty * entry
    sell_val = qty * exit_p
    turnover = buy_val + sell_val

    brokerage = 40.0                      # ₹20 per leg × 2
    stt       = 0.001  * sell_val         # 0.1% on sell side (delivery)
    exchange  = 0.0000335 * turnover      # NSE transaction charge
    sebi      = 0.000001  * turnover      # SEBI charges
    stamp     = 0.00015   * buy_val       # Stamp duty on buy
    gst       = 0.18 * (brokerage + exchange + sebi)

    return brokerage + stt + exchange + sebi + stamp + gst


def mtf_cost(entry: float, qty: int, leverage: int,
             days: int, annual_rate: float) -> float:
    """Daily MTF interest on borrowed amount for holding period."""
    if leverage <= 1:
        return 0.0
    position_val = entry * qty
    borrowed     = position_val * (leverage - 1) / leverage
    return borrowed * (annual_rate / 365) * days

# ─────────────────────────────────────────────────────────────
# ETF BACKTEST ENGINE
# Entry : Monthly MACD > Signal (trend filter)
#         + Weekly MACD crosses ABOVE Signal  → enter next week's open
# Exit  : Weekly MACD crosses BELOW Signal    → exit  next week's open
# ─────────────────────────────────────────────────────────────

def run_etf_backtest(etf_dict, fast, slow, sig_p, cash, leverage, rate,
                     start_date=None, end_date=None):
    trades, failed = [], []
    lookback = slow + sig_p + 2
    prog = st.progress(0)
    stat = st.empty()

    for n, (sym, ticker) in enumerate(etf_dict.items()):
        stat.text(f"Fetching {sym}  ({n+1}/{len(etf_dict)})...")
        prog.progress((n + 1) / len(etf_dict))

        wk = fetch_data(ticker, "1wk")
        mo = fetch_data(ticker, "1mo")

        if wk is None or mo is None:
            failed.append(sym)
            continue

        # Apply date range filter AFTER fetching (data is cached unfiltered)
        if start_date is not None:
            wk = wk[wk.index >= start_date]
            mo = mo[mo.index >= start_date]
        if end_date is not None:
            wk = wk[wk.index <= end_date]
            mo = mo[mo.index <= end_date]

        if len(wk) < lookback + 2:
            failed.append(sym)
            continue

        wk_m = calc_macd(wk["Close"].dropna(), fast, slow, sig_p)
        mo_m = calc_macd(mo["Close"].dropna(), fast, slow, sig_p)
        if wk_m is None or mo_m is None:
            failed.append(sym)
            continue

        in_pos, ep, ed, qty_ = False, 0.0, None, 0

        for i in range(lookback, len(wk) - 1):
            w_date = wk.index[i]

            if not in_pos:
                # Monthly trend filter
                mo_slice = mo_m[mo_m.index <= w_date]
                if len(mo_slice) < 2:
                    continue
                if mo_slice["macd"].iloc[-1] <= mo_slice["signal"].iloc[-1]:
                    continue

                # Weekly crossover UP
                pm = wk_m["macd"].iloc[i - 1];   ps = wk_m["signal"].iloc[i - 1]
                cm = wk_m["macd"].iloc[i];        cs = wk_m["signal"].iloc[i]
                if pd.isna(pm) or pd.isna(cm):
                    continue
                if not (pm < ps and cm > cs):
                    continue

                # Enter at next week's open (Monday open)
                next_open = wk["Open"].iloc[i + 1]
                if pd.isna(next_open) or float(next_open) <= 0:
                    continue

                qty_ = int((cash * leverage) // float(next_open))
                if qty_ <= 0:
                    continue

                ep, ed, in_pos = float(next_open), wk.index[i + 1], True

            else:
                # Weekly crossover DOWN → exit
                pm = wk_m["macd"].iloc[i - 1];   ps = wk_m["signal"].iloc[i - 1]
                cm = wk_m["macd"].iloc[i];        cs = wk_m["signal"].iloc[i]
                if pd.isna(pm) or pd.isna(cm):
                    continue
                if not (pm > ps and cm < cs):
                    continue

                xp   = float(wk["Open"].iloc[i + 1])
                xd   = wk.index[i + 1]
                days = max((xd - ed).days, 1)
                gp   = (xp - ep) * qty_
                cst  = txn_costs(qty_, ep, xp)
                mti  = mtf_cost(ep, qty_, leverage, days, rate)
                np_  = gp - cst - mti
                cash_used = ep * qty_ / leverage

                trades.append(dict(
                    symbol=sym, entry_date=ed, exit_date=xd,
                    entry_price=round(ep, 2), exit_price=round(xp, 2),
                    qty=qty_, holding_days=days,
                    gross_pnl=round(gp, 2), costs=round(cst, 2),
                    mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                    return_pct=round(np_ / cash_used * 100, 2),
                    status="CLOSED",
                ))
                in_pos, ep, ed, qty_ = False, 0.0, None, 0

        # Mark open position at last close
        if in_pos:
            xp   = float(wk["Close"].iloc[-1])
            xd   = wk.index[-1]
            days = max((xd - ed).days, 1)
            gp   = (xp - ep) * qty_
            cst  = txn_costs(qty_, ep, xp)
            mti  = mtf_cost(ep, qty_, leverage, days, rate)
            np_  = gp - cst - mti
            cash_used = ep * qty_ / leverage
            trades.append(dict(
                symbol=sym, entry_date=ed, exit_date=xd,
                entry_price=round(ep, 2), exit_price=round(xp, 2),
                qty=qty_, holding_days=days,
                gross_pnl=round(gp, 2), costs=round(cst, 2),
                mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                return_pct=round(np_ / cash_used * 100, 2),
                status="OPEN (MTM)",
            ))

        time.sleep(0.25)

    prog.empty()
    stat.empty()
    return pd.DataFrame(trades), failed

# ─────────────────────────────────────────────────────────────
# NIFTY 100 BACKTEST ENGINE
# Entry : Weekly MACD > Signal (trend filter)
#         + Daily MACD crosses ABOVE Signal   → enter next day's open
# Exit  : Daily MACD crosses BELOW Signal     → exit next day's open
#         OR last close >= entry × (1 + target%) → exit next day's open
# ─────────────────────────────────────────────────────────────

def run_nifty100_backtest(stock_dict, fast, slow, sig_p, cash,
                          leverage, rate, target_pct,
                          start_date=None, end_date=None):
    trades, failed = [], []
    lookback = slow + sig_p + 2
    prog = st.progress(0)
    stat = st.empty()

    for n, (sym, ticker) in enumerate(stock_dict.items()):
        stat.text(f"Fetching {sym}  ({n+1}/{len(stock_dict)})...")
        prog.progress((n + 1) / len(stock_dict))

        dy = fetch_data(ticker, "1d")
        wk = fetch_data(ticker, "1wk")

        if dy is None or wk is None:
            failed.append(sym)
            continue

        if start_date is not None:
            dy = dy[dy.index >= start_date]
            wk = wk[wk.index >= start_date]
        if end_date is not None:
            dy = dy[dy.index <= end_date]
            wk = wk[wk.index <= end_date]

        if len(dy) < lookback + 2:
            failed.append(sym)
            continue

        dy_m = calc_macd(dy["Close"].dropna(), fast, slow, sig_p)
        wk_m = calc_macd(wk["Close"].dropna(), fast, slow, sig_p)
        if dy_m is None or wk_m is None:
            failed.append(sym)
            continue

        in_pos, ep, ed, qty_ = False, 0.0, None, 0

        for i in range(lookback, len(dy) - 1):
            d_date = dy.index[i]

            if not in_pos:
                # Weekly trend filter
                wk_slice = wk_m[wk_m.index <= d_date]
                if len(wk_slice) < 2:
                    continue
                if wk_slice["macd"].iloc[-1] <= wk_slice["signal"].iloc[-1]:
                    continue

                # Daily crossover UP
                pm = dy_m["macd"].iloc[i - 1];   ps = dy_m["signal"].iloc[i - 1]
                cm = dy_m["macd"].iloc[i];        cs = dy_m["signal"].iloc[i]
                if pd.isna(pm) or pd.isna(cm):
                    continue
                if not (pm < ps and cm > cs):
                    continue

                next_open = dy["Open"].iloc[i + 1]
                if pd.isna(next_open) or float(next_open) <= 0:
                    continue

                qty_ = int((cash * leverage) // float(next_open))
                if qty_ <= 0:
                    continue

                ep, ed, in_pos = float(next_open), dy.index[i + 1], True

            else:
                last_close  = float(dy["Close"].iloc[i])
                target_hit  = last_close >= ep * (1 + target_pct)

                pm = dy_m["macd"].iloc[i - 1];   ps = dy_m["signal"].iloc[i - 1]
                cm = dy_m["macd"].iloc[i];        cs = dy_m["signal"].iloc[i]
                macd_exit = False if (pd.isna(pm) or pd.isna(cm)) \
                            else (pm > ps and cm < cs)

                if not (target_hit or macd_exit):
                    continue

                reason = "TARGET" if target_hit else "MACD_EXIT"
                xp     = float(dy["Open"].iloc[i + 1])
                xd     = dy.index[i + 1]
                days   = max((xd - ed).days, 1)
                gp     = (xp - ep) * qty_
                cst    = txn_costs(qty_, ep, xp)
                mti    = mtf_cost(ep, qty_, leverage, days, rate)
                np_    = gp - cst - mti
                cash_used = ep * qty_ / leverage

                trades.append(dict(
                    symbol=sym, entry_date=ed, exit_date=xd,
                    entry_price=round(ep, 2), exit_price=round(xp, 2),
                    qty=qty_, holding_days=days, exit_reason=reason,
                    gross_pnl=round(gp, 2), costs=round(cst, 2),
                    mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                    return_pct=round(np_ / cash_used * 100, 2),
                    status="CLOSED",
                ))
                in_pos, ep, ed, qty_ = False, 0.0, None, 0

        if in_pos:
            xp   = float(dy["Close"].iloc[-1])
            xd   = dy.index[-1]
            days = max((xd - ed).days, 1)
            gp   = (xp - ep) * qty_
            cst  = txn_costs(qty_, ep, xp)
            mti  = mtf_cost(ep, qty_, leverage, days, rate)
            np_  = gp - cst - mti
            cash_used = ep * qty_ / leverage
            trades.append(dict(
                symbol=sym, entry_date=ed, exit_date=xd,
                entry_price=round(ep, 2), exit_price=round(xp, 2),
                qty=qty_, holding_days=days, exit_reason="OPEN",
                gross_pnl=round(gp, 2), costs=round(cst, 2),
                mtf_interest=round(mti, 2), net_pnl=round(np_, 2),
                return_pct=round(np_ / cash_used * 100, 2),
                status="OPEN (MTM)",
            ))

        time.sleep(0.1)

    prog.empty()
    stat.empty()
    return pd.DataFrame(trades), failed

# ─────────────────────────────────────────────────────────────
# EQUITY CURVE  (daily, using business-day calendar)
# ─────────────────────────────────────────────────────────────

def build_equity_curve(trades_df: pd.DataFrame, total_capital: float) -> pd.Series:
    if trades_df.empty:
        return pd.Series(dtype=float)
    t = trades_df.sort_values("exit_date")
    start = t["entry_date"].min()
    end   = t["exit_date"].max()
    dates = pd.bdate_range(start, end)
    daily_pnl = t.groupby("exit_date")["net_pnl"].sum().reindex(dates, fill_value=0.0)
    return (total_capital + daily_pnl.cumsum()).ffill()

# ─────────────────────────────────────────────────────────────
# PERFORMANCE METRICS
# ─────────────────────────────────────────────────────────────

def compute_metrics(trades_df: pd.DataFrame,
                    equity: pd.Series, total_capital: float) -> dict:
    if trades_df.empty or equity.empty:
        return {}

    wins   = trades_df[trades_df["net_pnl"] > 0]
    losses = trades_df[trades_df["net_pnl"] <= 0]
    loss_sum = losses["net_pnl"].sum()

    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max * 100

    years    = max((equity.index[-1] - equity.index[0]).days / 365.25, 0.01)
    cagr     = ((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) * 100

    dr       = equity.pct_change().dropna()
    ann_ret  = (1 + dr.mean()) ** 252 - 1
    ann_std  = dr.std() * np.sqrt(252)
    sharpe   = (ann_ret - RISK_FREE_RATE) / ann_std if ann_std > 0 else 0.0
    d_std    = dr[dr < 0].std() * np.sqrt(252)
    sortino  = (ann_ret - RISK_FREE_RATE) / d_std if d_std > 0 else 0.0

    return {
        "num_trades":       len(trades_df),
        "total_net_pnl":    trades_df["net_pnl"].sum(),
        "total_gross_pnl":  trades_df["gross_pnl"].sum(),
        "total_costs":      trades_df["costs"].sum(),
        "total_mti":        trades_df["mtf_interest"].sum(),
        "total_return_pct": (equity.iloc[-1] / total_capital - 1) * 100,
        "cagr":             cagr,
        "max_drawdown":     drawdown.min(),
        "win_rate":         len(wins) / len(trades_df) * 100,
        "profit_factor":    abs(wins["net_pnl"].sum() / loss_sum)
                            if loss_sum != 0 else float("inf"),
        "sharpe":           sharpe,
        "sortino":          sortino,
        "avg_win":          wins["net_pnl"].mean()   if not wins.empty else 0,
        "avg_loss":         losses["net_pnl"].mean() if not losses.empty else 0,
        "best_trade":       trades_df["net_pnl"].max(),
        "worst_trade":      trades_df["net_pnl"].min(),
        "avg_hold":         trades_df["holding_days"].mean(),
        "open_positions":   (trades_df["status"] == "OPEN (MTM)").sum(),
    }

# ─────────────────────────────────────────────────────────────
# BUY-AND-HOLD BENCHMARK  (equal-weighted, same symbols)
# ─────────────────────────────────────────────────────────────

def buy_and_hold_series(sym_dict: dict, interval: str, start_date=None):
    """
    Equal-weighted buy-and-hold normalized to 1.0 at start_date.
    Each stock is normalized from start_date (or its own first date if no data
    at start_date). Stocks with no data in the period are skipped.
    Uses mean of available stocks per day (no dropna) to avoid losing history
    when some stocks have shorter listing history.
    """
    normals = []
    for sym, ticker in sym_dict.items():
        df = fetch_data(ticker, interval)
        if df is None or df.empty:
            continue
        close = df["Close"].dropna()
        # Clip to start_date so normalization base = start of backtest period
        if start_date is not None:
            close = close[close.index >= pd.Timestamp(start_date)]
        if len(close) < 2:
            continue
        normals.append(close / close.iloc[0])   # normalized to 1.0 at start_date
    if not normals:
        return None
    # mean(axis=1) ignores NaN per row — handles stocks with different listing dates
    aligned = pd.concat(normals, axis=1)
    return aligned.mean(axis=1)

# ─────────────────────────────────────────────────────────────
# CHARTS
# ─────────────────────────────────────────────────────────────

def equity_chart(equity: pd.Series, nifty50,
                 bnh, title: str) -> go.Figure:
    fig  = go.Figure()
    base = equity.iloc[0]

    fig.add_trace(go.Scatter(
        x=equity.index, y=(equity / base * 100),
        name="Strategy", line=dict(color="#00C9A7", width=2.5),
    ))

    if nifty50 is not None:
        n = nifty50["Close"].dropna()
        n = n[(n.index >= equity.index[0]) & (n.index <= equity.index[-1])]
        if not n.empty:
            fig.add_trace(go.Scatter(
                x=n.index, y=(n / n.iloc[0] * 100),
                name="Nifty 50", line=dict(color="#FF6B6B", width=1.5, dash="dot"),
            ))

    if bnh is not None:
        bnh_clip = bnh[(bnh.index >= equity.index[0]) & (bnh.index <= equity.index[-1])]
        bnh_clip = bnh_clip.dropna()
        if not bnh_clip.empty and bnh_clip.iloc[0] != 0:
            fig.add_trace(go.Scatter(
                x=bnh_clip.index, y=(bnh_clip / bnh_clip.iloc[0] * 100),
                name="Buy & Hold (same symbols)",
                line=dict(color="#FFA500", width=1.5, dash="dash"),
            ))

    fig.update_layout(
        title=title, height=430,
        xaxis_title="Date", yaxis_title="Normalized Value (Start = 100)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def pnl_dist_chart(trades_df: pd.DataFrame) -> go.Figure:
    colors = ["#00C9A7" if v >= 0 else "#FF6B6B" for v in trades_df["net_pnl"]]
    fig = go.Figure(go.Histogram(
        x=trades_df["net_pnl"], nbinsx=30, marker_color=colors,
    ))
    fig.update_layout(
        title="Net P&L Distribution per Trade",
        xaxis_title="Net P&L (₹)", yaxis_title="# Trades", height=320,
    )
    return fig


def per_symbol_chart(trades_df: pd.DataFrame) -> go.Figure:
    s = (trades_df.groupby("symbol")["net_pnl"]
         .sum().sort_values(ascending=True))
    colors = ["#00C9A7" if v >= 0 else "#FF6B6B" for v in s]
    fig = go.Figure(go.Bar(
        x=s.values, y=s.index, orientation="h",
        marker_color=colors,
        text=[f"₹{v:,.0f}" for v in s.values], textposition="outside",
    ))
    fig.update_layout(
        title="Net P&L by Symbol",
        height=max(320, len(s) * 28), xaxis_title="Net P&L (₹)",
    )
    return fig


def drawdown_chart(equity: pd.Series) -> go.Figure:
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max * 100
    fig = go.Figure(go.Scatter(
        x=dd.index, y=dd.values,
        fill="tozeroy", line=dict(color="#FF6B6B", width=1),
        fillcolor="rgba(255,107,107,0.3)", name="Drawdown",
    ))
    fig.update_layout(
        title="Drawdown (%)", height=250,
        xaxis_title="Date", yaxis_title="Drawdown %", hovermode="x unified",
    )
    return fig

# ─────────────────────────────────────────────────────────────
# METRIC CARDS  (shared UI component)
# ─────────────────────────────────────────────────────────────

def show_metrics(m: dict, label: str = ""):
    if not m:
        return
    st.markdown(f"### {label} — Performance Summary")

    if m.get("open_positions", 0) > 0:
        st.info(
            f"ℹ️  {m['open_positions']} position(s) still open — "
            "marked to market at last available close. "
            "Costs & MTF interest included up to that date."
        )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net P&L",      f"₹{m['total_net_pnl']:,.0f}",
              f"{m['total_return_pct']:.1f}% total return")
    c2.metric("CAGR",         f"{m['cagr']:.1f}%")
    c3.metric("Max Drawdown", f"{m['max_drawdown']:.1f}%")
    c4.metric("Win Rate",     f"{m['win_rate']:.1f}%",
              f"{m['num_trades']} trades")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Profit Factor", f"{m['profit_factor']:.2f}")
    c6.metric("Sharpe Ratio",  f"{m['sharpe']:.2f}")
    c7.metric("Sortino Ratio", f"{m['sortino']:.2f}")
    c8.metric("Avg Hold",      f"{m['avg_hold']:.0f} days")

    with st.expander("🔍 Detailed Cost & Trade Breakdown"):
        d1, d2, d3 = st.columns(3)
        d1.metric("Gross P&L",          f"₹{m['total_gross_pnl']:,.0f}")
        d2.metric("Transaction Costs",  f"₹{m['total_costs']:,.0f}")
        d3.metric("MTF Interest Paid",  f"₹{m['total_mti']:,.0f}")

        d4, d5, d6 = st.columns(3)
        d4.metric("Avg Winning Trade",  f"₹{m['avg_win']:,.0f}")
        d5.metric("Avg Losing Trade",   f"₹{m['avg_loss']:,.0f}")
        d6.metric("Best / Worst Trade",
                  f"₹{m['best_trade']:,.0f} / ₹{m['worst_trade']:,.0f}")

# ─────────────────────────────────────────────────────────────
# TRADE LOG DISPLAY
# ─────────────────────────────────────────────────────────────

def show_trade_log(trades_df: pd.DataFrame, filename: str):
    st.subheader("📋 Trade Log")

    preferred = ["symbol", "entry_date", "exit_date", "entry_price",
                 "exit_price", "qty", "holding_days", "exit_reason",
                 "gross_pnl", "costs", "mtf_interest", "net_pnl",
                 "return_pct", "status"]
    cols = [c for c in preferred if c in trades_df.columns]

    def color_pnl(val):
        if isinstance(val, (int, float)):
            return "color: #00C9A7" if val > 0 else "color: #FF6B6B"
        return ""

    styled = (
        trades_df[cols]
        .sort_values("entry_date", ascending=False)
        .style.map(color_pnl, subset=["net_pnl"])
    )
    st.dataframe(styled, use_container_width=True, height=420)

    csv = trades_df.to_csv(index=False)
    st.download_button("⬇️ Download Trade Log (CSV)", csv, filename, "text/csv")

# ─────────────────────────────────────────────────────────────
# CONFIG PANEL  (shared layout helper)
# ─────────────────────────────────────────────────────────────

def config_panel(key_prefix: str, universe: dict,
                 default_fast: int, default_slow: int, default_sig: int,
                 has_target: bool = False):
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        selected = st.multiselect(
            "Select symbols", options=list(universe.keys()),
            default=list(universe.keys()),
            key=f"{key_prefix}_symbols",
        )
        dcol1, dcol2 = st.columns(2)
        with dcol1:
            from datetime import date as date_type
            start_date = st.date_input(
                "Backtest from",
                value=date_type(2015, 1, 1),
                min_value=date_type(2000, 1, 1),
                max_value=date_type.today(),
                key=f"{key_prefix}_start",
                help="Symbols with no data before this date will start from their listing date"
            )
        with dcol2:
            end_date = st.date_input(
                "Backtest to",
                value=date_type.today(),
                min_value=date_type(2000, 1, 1),
                max_value=date_type.today(),
                key=f"{key_prefix}_end",
            )

    with col2:
        fast   = st.number_input("MACD Fast",   value=default_fast,
                                  min_value=2, max_value=50,  key=f"{key_prefix}_fast")
        slow   = st.number_input("MACD Slow",   value=default_slow,
                                  min_value=5, max_value=200, key=f"{key_prefix}_slow")
        signal = st.number_input("MACD Signal", value=default_sig,
                                  min_value=2, max_value=50,  key=f"{key_prefix}_sig")

    with col3:
        cash     = st.number_input("Cash per symbol (₹)", value=10000, step=1000,
                                    key=f"{key_prefix}_cash")
        leverage = st.selectbox(
            "Leverage", [1, 2, 3, 4, 5], index=3,
            format_func=lambda x: f"{x}x  ({'CNC' if x == 1 else 'MTF'})",
            key=f"{key_prefix}_lev",
        )
        rate     = st.number_input("MTF rate (% p.a.)", value=14.0,
                                    min_value=0.0, max_value=30.0, step=0.5,
                                    key=f"{key_prefix}_rate") / 100
        target   = None
        if has_target:
            target = st.number_input("Target exit (%)", value=3.5,
                                      min_value=0.5, max_value=50.0, step=0.5,
                                      key=f"{key_prefix}_target") / 100

    run = st.button("🚀 Run Backtest", type="primary",
                    use_container_width=True, key=f"{key_prefix}_run")

    return (selected, int(fast), int(slow), int(signal),
            cash, int(leverage), rate, target, run,
            pd.Timestamp(start_date), pd.Timestamp(end_date))

# ─────────────────────────────────────────────────────────────
# MAIN TABS
# ─────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["📊 ETF Strategy", "📈 Nifty 100 Strategy"])

# ════════════════════════════════════════════════════════════
# TAB 1 — ETF STRATEGY
# ════════════════════════════════════════════════════════════

with tab1:
    st.subheader("ETF Strategy — Monthly MACD Filter + Weekly Crossover")
    st.caption(
        "Entry: Monthly MACD > Signal  **AND**  Weekly MACD crosses above Signal  →  "
        "enter next Monday open  |  "
        "Exit: Weekly MACD crosses below Signal  →  exit next Monday open"
    )

    with st.expander("⚙️ Configure & Run", expanded=True):
        (e_syms, e_fast, e_slow, e_sig,
         e_cash, e_lev, e_rate, _, e_run,
         e_start, e_end) = config_panel(
            "etf", ALL_ETFS, 12, 24, 3, has_target=False
        )

    if e_run:
        if not e_syms:
            st.error("Select at least one ETF.")
        else:
            sel_etfs  = {k: ALL_ETFS[k] for k in e_syms}
            total_cap = e_cash * len(sel_etfs)

            st.info(
                f"Running on **{len(sel_etfs)} ETFs** | "
                f"₹{e_cash:,} × {e_lev}x = ₹{e_cash * e_lev:,} per ETF | "
                f"Total capital: ₹{total_cap:,} | "
                f"Period: **{e_start.date()} → {e_end.date()}**"
            )

            with st.spinner("Fetching data & running backtest..."):
                tdf, failed = run_etf_backtest(
                    sel_etfs, e_fast, e_slow, e_sig, e_cash, e_lev, e_rate,
                    start_date=e_start, end_date=e_end
                )

            if failed:
                st.warning(f"⚠️ No data for: {', '.join(failed)}")

            if tdf.empty:
                st.error("No trades generated. Try adjusting MACD parameters or date range.")
            else:
                equity  = build_equity_curve(tdf, total_cap)
                metrics = compute_metrics(tdf, equity, total_cap)
                n50     = fetch_nifty50()
                bnh     = buy_and_hold_series(sel_etfs, "1wk", start_date=equity.index[0])

                first_trade = tdf["entry_date"].min().date()
                last_trade  = tdf["exit_date"].max().date()
                years_tested = (tdf["exit_date"].max() - tdf["entry_date"].min()).days / 365.25
                st.success(
                    f"📅 **Backtest period: {first_trade}  →  {last_trade} "
                    f"({years_tested:.1f} years)**  |  "
                    f"Symbols with data before {e_start.date()} started from their "
                    f"listing date instead"
                )

                # Per-symbol data range table
                with st.expander("📊 Per-symbol data range"):
                    sym_summary = (
                        tdf.groupby("symbol")
                        .agg(first_trade=("entry_date", "min"),
                             last_trade=("exit_date", "max"),
                             num_trades=("net_pnl", "count"),
                             net_pnl=("net_pnl", "sum"))
                        .reset_index()
                        .sort_values("first_trade")
                    )
                    sym_summary["first_trade"] = sym_summary["first_trade"].dt.date
                    sym_summary["last_trade"]  = sym_summary["last_trade"].dt.date
                    sym_summary["net_pnl"]     = sym_summary["net_pnl"].map("₹{:,.0f}".format)
                    st.dataframe(sym_summary, use_container_width=True)

                show_metrics(metrics, "ETF Strategy")
                st.plotly_chart(
                    equity_chart(equity, n50, bnh,
                                 "ETF Strategy — Equity Curve vs Benchmarks"),
                    use_container_width=True,
                )
                st.plotly_chart(drawdown_chart(equity), use_container_width=True)

                ca, cb = st.columns(2)
                with ca:
                    st.plotly_chart(pnl_dist_chart(tdf), use_container_width=True)
                with cb:
                    st.plotly_chart(per_symbol_chart(tdf), use_container_width=True)

                show_trade_log(tdf, "etf_backtest_trades.csv")

# ════════════════════════════════════════════════════════════
# TAB 2 — NIFTY 100 STRATEGY
# ════════════════════════════════════════════════════════════

with tab2:
    st.subheader("Nifty 100 Strategy — Weekly MACD Filter + Daily Crossover + Target Exit")
    st.caption(
        "Entry: Weekly MACD > Signal  **AND**  Daily MACD crosses above Signal  →  "
        "enter next day open  |  "
        "Exit: Daily MACD crosses below Signal  **OR**  Target hit  →  exit next day open"
    )

    with st.expander("⚙️ Configure & Run", expanded=True):
        (n_syms, n_fast, n_slow, n_sig,
         n_cash, n_lev, n_rate, n_target, n_run,
         n_start, n_end) = config_panel(
            "n100", NIFTY100_STOCKS, 12, 24, 3, has_target=True
        )

    if n_run:
        if not n_syms:
            st.error("Select at least one stock.")
        else:
            sel_stocks = {k: NIFTY100_STOCKS[k] for k in n_syms}
            total_cap  = n_cash * len(sel_stocks)

            st.info(
                f"Running on **{len(sel_stocks)} stocks** | "
                f"₹{n_cash:,} × {n_lev}x = ₹{n_cash * n_lev:,} per stock | "
                f"Total capital: ₹{total_cap:,} | "
                f"Target: {n_target*100:.1f}% | "
                f"Period: **{n_start.date()} → {n_end.date()}**"
            )
            if len(sel_stocks) > 30:
                st.warning(
                    f"Fetching {len(sel_stocks)} stocks takes 2–4 minutes. "
                    "Data is cached — subsequent runs with different MACD params are instant."
                )

            with st.spinner("Fetching data & running backtest..."):
                tdf, failed = run_nifty100_backtest(
                    sel_stocks, n_fast, n_slow, n_sig,
                    n_cash, n_lev, n_rate, n_target,
                    start_date=n_start, end_date=n_end
                )

            if failed:
                st.warning(f"⚠️ No data for: {', '.join(failed)}")

            if tdf.empty:
                st.error("No trades generated. Try adjusting MACD parameters or date range.")
            else:
                equity  = build_equity_curve(tdf, total_cap)
                metrics = compute_metrics(tdf, equity, total_cap)
                n50     = fetch_nifty50()
                bnh     = buy_and_hold_series(sel_stocks, "1d", start_date=equity.index[0])

                first_trade  = tdf["entry_date"].min().date()
                last_trade   = tdf["exit_date"].max().date()
                years_tested = (tdf["exit_date"].max() - tdf["entry_date"].min()).days / 365.25
                st.success(
                    f"📅 **Backtest period: {first_trade}  →  {last_trade} "
                    f"({years_tested:.1f} years)**  |  "
                    f"Stocks listed after {n_start.date()} start from their listing date instead"
                )

                with st.expander("📊 Per-symbol data range"):
                    sym_summary = (
                        tdf.groupby("symbol")
                        .agg(first_trade=("entry_date", "min"),
                             last_trade=("exit_date", "max"),
                             num_trades=("net_pnl", "count"),
                             net_pnl=("net_pnl", "sum"))
                        .reset_index()
                        .sort_values("first_trade")
                    )
                    sym_summary["first_trade"] = sym_summary["first_trade"].dt.date
                    sym_summary["last_trade"]  = sym_summary["last_trade"].dt.date
                    sym_summary["net_pnl"]     = sym_summary["net_pnl"].map("₹{:,.0f}".format)
                    st.dataframe(sym_summary, use_container_width=True)

                show_metrics(metrics, "Nifty 100 Strategy")
                st.plotly_chart(
                    equity_chart(equity, n50, bnh,
                                 "Nifty 100 Strategy — Equity Curve vs Benchmarks"),
                    use_container_width=True,
                )
                st.plotly_chart(drawdown_chart(equity), use_container_width=True)

                ca, cb = st.columns(2)
                with ca:
                    st.plotly_chart(pnl_dist_chart(tdf), use_container_width=True)
                with cb:
                    st.plotly_chart(per_symbol_chart(tdf), use_container_width=True)

                # Exit reason summary
                if "exit_reason" in tdf.columns:
                    st.subheader("Exit Reason Breakdown")
                    rc = tdf["exit_reason"].value_counts()
                    r1, r2, r3 = st.columns(3)
                    r1.metric("MACD Crossover Exit", int(rc.get("MACD_EXIT", 0)))
                    r2.metric("Target Hit",           int(rc.get("TARGET",   0)))
                    r3.metric("Still Open (MTM)",     int(rc.get("OPEN",     0)))

                show_trade_log(tdf, "nifty100_backtest_trades.csv")
