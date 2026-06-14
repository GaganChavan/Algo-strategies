import yfinance as yf
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread
import time

# Google Sheets Integration
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(
    r'/Users/gagankumarchavan/Documents/API Cred/noble-aquifer-437514-k4-a50658fe7247.json',
    scopes=scope
)
client = gspread.authorize(creds)
sheet = client.open("My ETF Portfolio tracker").worksheet("QQQ")

HEADER_ROW = 1
DATA_START_ROW = 2

# Read tickers from column B starting at row 2 (works for any US stock or ETF)
tickers = [t.strip() for t in sheet.col_values(2)[DATA_START_ROW - 1:] if t.strip()]
print(f"Tickers found: {tickers}")

RISK_FREE_RATE_DAILY = 0.07 / 252


def extract_price_col(df, ticker):
    if isinstance(df.columns, pd.MultiIndex):
        for label in ['Adj Close', 'Close']:
            if (label, ticker) in df.columns:
                return (label, ticker)
        return None
    for label in ['Adj Close', 'Close']:
        if label in df.columns:
            return label
    return None


def get_name(ticker):
    try:
        info = yf.Ticker(ticker).info
        # info dict will be nearly empty for invalid tickers
        name = info.get('longName') or info.get('shortName') or ''
        if not name:
            print(f"  WARNING: '{ticker}' returned no name — may be an invalid ticker symbol.")
        return name or ticker
    except Exception:
        return ticker


def get_cmp(ticker):
    try:
        data = yf.download(ticker, period="5d", progress=False)
        if data.empty:
            print(f"  WARNING: No price data for '{ticker}' — check if the ticker symbol is correct.")
            return ''
        price_col = extract_price_col(data, ticker)
        if price_col is None:
            return ''
        return round(float(data[price_col].iloc[-1].item()), 2)
    except Exception as e:
        print(f"Error fetching CMP for {ticker}: {e}")
        return ''


def get_metrics(ticker):
    """Returns (avg_daily_return, volatility, sharpe_ratio) from 1 year of data."""
    try:
        data = yf.download(ticker, period="1y", progress=False)
        if data.empty:
            return '', '', ''
        price_col = extract_price_col(data, ticker)
        if price_col is None:
            return '', '', ''
        daily_returns = data[price_col].pct_change().dropna()
        avg_return = float(daily_returns.mean())
        volatility = float(daily_returns.std())
        sharpe = 0.0 if volatility == 0 or pd.isna(volatility) else (avg_return - RISK_FREE_RATE_DAILY) / volatility
        return round(avg_return, 6), round(volatility, 6), round(sharpe, 6)
    except Exception as e:
        print(f"Error calculating metrics for {ticker}: {e}")
        return '', '', ''


# ── Main Execution ──────────────────────────────────────────────────────────────

results = []

for i, ticker in enumerate(tickers):
    row = DATA_START_ROW + i
    print(f"\nProcessing {ticker} (row {row})...")

    name = get_name(ticker)
    cmp = get_cmp(ticker)
    avg_return, volatility, sharpe = get_metrics(ticker)

    sheet.update(
        range_name=f'A{row}:F{row}',
        values=[[name, ticker, cmp, avg_return, volatility, sharpe]]
    )
    print(f"  Name       : {name}")
    print(f"  CMP (USD)  : {cmp}")
    print(f"  Avg Return : {avg_return}")
    print(f"  Volatility : {volatility}")
    print(f"  Sharpe     : {sharpe}")
    print(f"  Row {row} updated.")
    results.append((ticker, cmp, avg_return, volatility, sharpe))
    time.sleep(1)

# ── Comparison Summary ───────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print(f"{'Ticker':<10} {'CMP (USD)':>10} {'Avg Ret':>10} {'Volatility':>12} {'Sharpe':>10}")
print("-" * 65)
for ticker, cmp, avg_ret, vol, sharpe in results:
    cmp_str    = f"${cmp}"      if cmp      != '' else 'N/A'
    ret_str    = f"{avg_ret}"   if avg_ret  != '' else 'N/A'
    vol_str    = f"{vol}"       if vol      != '' else 'N/A'
    sharpe_str = f"{sharpe}"    if sharpe   != '' else 'N/A'
    print(f"{ticker:<10} {cmp_str:>10} {ret_str:>10} {vol_str:>12} {sharpe_str:>10}")
print("=" * 65)
print("All done! Sheet updated.")
