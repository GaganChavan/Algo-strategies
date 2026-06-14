import yfinance as yf
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread
import gspread.utils
from datetime import date, timedelta
import time

# ── Config ─────────────────────────────────────────────────────────────────────
CREDS_PATH = r'/Users/gagankumarchavan/Documents/API Cred/noble-aquifer-437514-k4-a50658fe7247.json'
SHEET_NAME = "My ETF Portfolio tracker"
WORKSHEET_NAME = "US ETF"

HEADER_ROW = 1
START_ROW = 2
COL_SYMBOL = 1    # A
COL_EXCHANGE = 5  # E

COL_1Y_RETURN = 11   # K
COL_VOLATILITY = 12  # L
COL_MACD_DIFF = 13   # M
COL_SIGNAL = 14      # N

MACD_FAST = 12
MACD_SLOW = 24
MACD_SIG = 3
MAX_WEEKS = 52

BATCH_SIZE = 20          # tickers per yfinance batch call
SLEEP_BETWEEN_BATCHES = 3.0   # seconds between batch downloads
SLEEP_INDIVIDUAL = 2.0        # seconds before an individual retry download
MAX_RETRIES = 3               # retry attempts per individual ticker

# ── Exchange → yfinance suffix map ─────────────────────────────────────────────
EXCHANGE_SUFFIX = {
    'NYSE ARCA': '', 'NYSE': '', 'NASDAQ': '', 'CBOE': '', 'BATS': '',
    'TSX VENTURE': '.V', 'TSX': '.TO', 'TORONTO': '.TO',
    'LSE': '.L', 'LONDON': '.L',
    'XETRA': '.DE', 'FRANKFURT': '.DE',
    'EURONEXT PARIS': '.PA', 'PARIS': '.PA',
    'EURONEXT AMSTERDAM': '.AS', 'AMSTERDAM': '.AS',
    'EURONEXT BRUSSELS': '.BR',
    'NSE': '.NS', 'BSE': '.BO',
    'HKEX': '.HK', 'HONG KONG': '.HK',
    'TSE': '.T', 'TOKYO': '.T',
    'ASX': '.AX', 'AUSTRALIA': '.AX',
    'SGX': '.SI', 'SINGAPORE': '.SI',
    'KRX': '.KS', 'KOREA': '.KS',
}


def get_yf_ticker(symbol, exchange):
    ex = exchange.upper().strip()
    for key, suffix in EXCHANGE_SUFFIX.items():
        if key in ex:
            return symbol + suffix
    return symbol


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


def last_completed_friday():
    """Most recent Friday whose market session is fully closed."""
    today = date.today()
    days_back = (today.weekday() - 4) % 7
    if days_back == 0:   # today IS Friday — session may still be open
        days_back = 7
    return today - timedelta(days=days_back)


def download_individual(ticker, symbol):
    """Download a single ticker with exponential backoff retry."""
    for attempt in range(MAX_RETRIES):
        try:
            df = yf.download(ticker, period="3y", interval="1d", progress=False)
            if not df.empty:
                return df
            # Empty but no exception — bad ticker, not a rate limit
            print(f"  ⚠️  {symbol} ({ticker}): empty response")
            return pd.DataFrame()
        except Exception as e:
            wait = 2 ** (attempt + 1)   # 2s, 4s, 8s
            if attempt < MAX_RETRIES - 1:
                print(f"  ↩️  {symbol} retry {attempt + 1}/{MAX_RETRIES - 1} in {wait}s — {e}")
                time.sleep(wait)
            else:
                print(f"  ❌ {symbol}: all retries exhausted — {e}")
    return pd.DataFrame()


def get_prices(batch_df, ticker, batch_tickers, symbol):
    """
    Extract a clean price Series for one ticker.
    Uses the batch result when valid; falls back to individual download.
    Returns (prices_series, source_df) where source_df is what was used.
    """
    if not batch_df.empty:
        if len(batch_tickers) == 1:
            # Single-ticker download — regular (non-MultiIndex) DataFrame
            price_col = extract_price_col(batch_df, ticker)
            if price_col:
                s = batch_df[price_col].dropna()
                if len(s) > 0:
                    return s, batch_df
        else:
            # Multi-ticker batch — MultiIndex DataFrame
            for label in ['Adj Close', 'Close']:
                col = (label, ticker)
                if col in batch_df.columns:
                    s = batch_df[col].dropna()
                    if len(s) > 0:
                        return s, batch_df

    # Ticker missing or all-NaN in batch → individual download
    print(f"  ↩️  {symbol} ({ticker}): not in batch, downloading individually...")
    time.sleep(SLEEP_INDIVIDUAL)
    ind_df = download_individual(ticker, symbol)
    if ind_df.empty:
        return pd.Series(dtype=float), pd.DataFrame()
    price_col = extract_price_col(ind_df, ticker)
    if price_col is None:
        return pd.Series(dtype=float), pd.DataFrame()
    return ind_df[price_col].dropna(), ind_df


def compute_metrics(prices, completed_fri):
    """Return (1y_return%, daily_vol%, macd_diff, signal_label) from a price Series."""
    r1y = rvol = rmacd = rsig = ''

    last_date = prices.index.max()

    # 1-Year Return
    year_ago = last_date - pd.Timedelta(days=365)
    idx = prices.index.get_indexer([year_ago], method='nearest')[0]
    if idx >= 0:
        ret = float(prices.iloc[-1]) / float(prices.iloc[idx]) - 1
        r1y = round(ret * 100, 2)

    # Daily Volatility (1 year) — exclude days > 50% move to guard against
    # fund restructuring / reverse-split artefacts in Yahoo Finance raw data
    prices_1y = prices[prices.index >= (last_date - pd.Timedelta(days=365))]
    if len(prices_1y) > 1:
        daily_rets = prices_1y.pct_change().dropna()
        daily_rets = daily_rets[daily_rets.abs() <= 0.50]
        if len(daily_rets) > 1:
            rvol = round(float(daily_rets.std()) * 100, 4)

    # Weekly MACD (12, 24, 3) — completed weeks only
    weekly = prices.resample('W-FRI').last().dropna()
    weekly = weekly[weekly.index.date <= completed_fri]

    min_bars = MACD_SLOW + MACD_SIG
    if len(weekly) < min_bars:
        rsig = 'Insufficient Data'
    else:
        ema_fast = weekly.ewm(span=MACD_FAST, adjust=False).mean()
        ema_slow = weekly.ewm(span=MACD_SLOW, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=MACD_SIG, adjust=False).mean()
        diff = macd_line - signal_line

        current_diff = float(diff.iloc[-1])
        rmacd = round(current_diff, 4)
        is_bullish = current_diff > 0

        weeks = 0
        for j in range(len(diff) - 1, -1, -1):
            val = float(diff.iloc[j])
            if is_bullish and val > 0:
                weeks += 1
            elif not is_bullish and val <= 0:
                weeks += 1
            else:
                break
            if weeks >= MAX_WEEKS:
                break

        w_str = f"{weeks}+" if weeks >= MAX_WEEKS else str(weeks)
        if is_bullish:
            rsig = "Strong Buy" if weeks == 1 else f"Green {w_str} weeks"
        else:
            rsig = "Strong Sell" if weeks == 1 else f"Red {w_str} weeks"

    return r1y, rvol, rmacd, rsig


# ── Google Sheets Setup ────────────────────────────────────────────────────────
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(
    r'/Users/gagankumarchavan/Documents/API Cred/noble-aquifer-437514-k4-a50658fe7247.json',
    scopes=scope
)
client = gspread.authorize(creds)
sheet = client.open("My ETF Portfolio tracker").worksheet("US ETF")

header_row_vals = sheet.row_values(HEADER_ROW)

def ensure_header(col_idx, label):
    if len(header_row_vals) < col_idx or not header_row_vals[col_idx - 1].strip():
        cell = gspread.utils.rowcol_to_a1(HEADER_ROW, col_idx)
        sheet.update(range_name=cell, values=[[label]])
        print(f"  Header written: {label} → {cell}")

ensure_header(COL_1Y_RETURN, '1 Year Return %')
ensure_header(COL_VOLATILITY, 'Daily Volatility %')
ensure_header(COL_MACD_DIFF, 'Weekly MACD Diff')
ensure_header(COL_SIGNAL, 'MACD Signal')

# ── Read ETF rows ──────────────────────────────────────────────────────────────
all_rows = sheet.get_all_values()
etfs = []
for i, row in enumerate(all_rows[START_ROW - 1:], start=START_ROW):
    symbol = row[COL_SYMBOL - 1].strip() if len(row) >= COL_SYMBOL else ''
    if not symbol:
        continue
    exchange = row[COL_EXCHANGE - 1].strip() if len(row) >= COL_EXCHANGE else ''
    etfs.append({
        'row': i,
        'symbol': symbol,
        'ticker': get_yf_ticker(symbol, exchange),
    })

completed_fri = last_completed_friday()
total_batches = (len(etfs) - 1) // BATCH_SIZE + 1
print(f"Found {len(etfs)} ETFs across {total_batches} batches  |  Completed weeks up to: {completed_fri}")
print("─" * 65)

# ── Main loop: batch download → per-ticker metrics ─────────────────────────────
batch_updates = []

for b_start in range(0, len(etfs), BATCH_SIZE):
    batch = etfs[b_start:b_start + BATCH_SIZE]
    b_num = b_start // BATCH_SIZE + 1
    batch_tickers = [item['ticker'] for item in batch]

    print(f"\n⬇️  Batch {b_num}/{total_batches} — downloading {len(batch_tickers)} tickers...")
    try:
        if len(batch_tickers) == 1:
            batch_df = yf.download(batch_tickers[0], period="3y", interval="1d", progress=False)
        else:
            batch_df = yf.download(batch_tickers, period="3y", interval="1d", progress=False)
        print(f"   Batch {b_num} downloaded — {len(batch_df)} daily rows")
    except Exception as e:
        print(f"   ⚠️  Batch {b_num} failed ({e}) — will fall back to individual downloads")
        batch_df = pd.DataFrame()

    for item in batch:
        symbol = item['symbol']
        ticker = item['ticker']
        row_num = item['row']

        r1y = rvol = rmacd = rsig = ''
        try:
            prices, _ = get_prices(batch_df, ticker, batch_tickers, symbol)
            if prices.empty:
                print(f"   ⚠️  {symbol:8}: no usable price data")
            else:
                r1y, rvol, rmacd, rsig = compute_metrics(prices, completed_fri)
                print(f"   ✅ {symbol:8} | 1Y={str(r1y)+'%':>9}  Vol={str(rvol)+'%':>8}  MACD={str(rmacd):>10}  → {rsig}")
        except Exception as e:
            print(f"   ❌ {symbol:8}: {e}")

        start_cell = gspread.utils.rowcol_to_a1(row_num, COL_1Y_RETURN)
        end_cell = gspread.utils.rowcol_to_a1(row_num, COL_SIGNAL)
        batch_updates.append({
            'range': f"{start_cell}:{end_cell}",
            'values': [[r1y, rvol, rmacd, rsig]]
        })

    # Pause between batches to respect Yahoo Finance rate limits
    if b_start + BATCH_SIZE < len(etfs):
        print(f"   ⏳ Waiting {SLEEP_BETWEEN_BATCHES}s before next batch...")
        time.sleep(SLEEP_BETWEEN_BATCHES)

# ── Batch write to Google Sheet ────────────────────────────────────────────────
print(f"\n📤 Writing {len(batch_updates)} rows to Google Sheet...")
CHUNK = 25
for i in range(0, len(batch_updates), CHUNK):
    sheet.batch_update(batch_updates[i:i + CHUNK])
    time.sleep(1)

print(f"✅ Done! {len(etfs)} ETFs updated in '{WORKSHEET_NAME}'.")
