import yfinance as yf
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread
import gspread.utils
from datetime import date, timedelta
import time

# ── Config ─────────────────────────────────────────────────────────────────────
CREDS_PATH     = r'/Users/gagankumarchavan/Documents/API Cred/noble-aquifer-437514-k4-a50658fe7247.json'
SHEET_NAME     = "My ETF Portfolio tracker"
WORKSHEET_NAME = "Indian ETF MTF"

HEADER_ROW = 1
START_ROW  = 2

# Column positions — must match what is in the sheet
COL_SYMBOL   = 1  # A  ← you manage this column; script reads it
COL_NAME     = 2  # B  ← you manage this column; script reads it
COL_CATEGORY = 3  # C  ← you manage this column; script reads it
COL_MTF_LEV  = 4  # D  ← you manage this column; script reads it

# Columns the script computes and writes back
COL_1Y_RETURN  = 5  # E
COL_VOLATILITY = 6  # F
COL_MACD_DIFF  = 7  # G
COL_SIGNAL     = 8  # H

MACD_FAST = 12
MACD_SLOW = 24
MACD_SIG  = 3
MAX_WEEKS = 52

# Yahoo Finance download settings
BATCH_SIZE            = 20   # tickers per yfinance batch call
SLEEP_BETWEEN_BATCHES = 3.0  # seconds between batch downloads
SLEEP_INDIVIDUAL      = 2.0  # seconds before an individual retry
MAX_RETRIES           = 3

# Google Sheets write settings
WRITE_CHUNK = 25  # rows per batch_update call (stay well under API rate limits)

# ── Yahoo Finance ticker overrides ─────────────────────────────────────────────
# Some NSE symbols were renamed on Yahoo Finance.  Column A in the sheet always
# holds the real NSE/Kite symbol.  This map tells the script which Yahoo Finance
# ticker to use instead for downloading data.  Add new entries here only if a
# new ETF you add to the sheet fails to download and you discover its YF ticker
# is different from the NSE symbol.
YF_SYMBOL_OVERRIDE = {
    "UTINIFTETF": "NIFTYBETA",  # renamed on Yahoo Finance Dec 2025
    "ICICINIFTY": "NIFTYIETF",
    "KOTAKNIFTY": "NIFTY1",
    "HDFCMFGETF": "HDFCGOLD",
    "KOTAKGOLD":  "GOLD1",
    "KOTAKSILVE": "SILVER1",
}

NSE_SUFFIX = ".NS"


# ── Helpers ────────────────────────────────────────────────────────────────────
def get_yf_ticker(symbol):
    return YF_SYMBOL_OVERRIDE.get(symbol, symbol) + NSE_SUFFIX


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
    """Most recent Friday whose weekly session is fully closed.
    If today is Friday and it is past 4 PM IST (NSE closes 3:30 PM),
    today's Friday is treated as completed.
    """
    from datetime import datetime, timezone
    IST       = timezone(timedelta(hours=5, minutes=30))
    today     = date.today()
    days_back = (today.weekday() - 4) % 7   # 0 means today is Friday
    if days_back == 0:
        now_ist = datetime.now(IST)
        if now_ist.hour < 16:    # before 4 PM IST — session not yet closed
            days_back = 7
    return today - timedelta(days=days_back)


def download_individual(ticker, symbol):
    for attempt in range(MAX_RETRIES):
        try:
            df = yf.download(ticker, period="3y", interval="1d", progress=False)
            if not df.empty:
                return df
            print(f"  ⚠️  {symbol} ({ticker}): empty response")
            return pd.DataFrame()
        except Exception as e:
            wait = 2 ** (attempt + 1)
            if attempt < MAX_RETRIES - 1:
                print(f"  ↩️  {symbol} retry {attempt + 1}/{MAX_RETRIES - 1} in {wait}s — {e}")
                time.sleep(wait)
            else:
                print(f"  ❌ {symbol}: all retries exhausted — {e}")
    return pd.DataFrame()


def get_prices(batch_df, ticker, batch_tickers, symbol):
    if not batch_df.empty:
        if len(batch_tickers) == 1:
            price_col = extract_price_col(batch_df, ticker)
            if price_col:
                s = batch_df[price_col].dropna()
                if len(s) > 0:
                    return s, batch_df
        else:
            for label in ['Adj Close', 'Close']:
                col = (label, ticker)
                if col in batch_df.columns:
                    s = batch_df[col].dropna()
                    if len(s) > 0:
                        return s, batch_df

    print(f"  ↩️  {symbol} ({ticker}): not in batch — downloading individually...")
    time.sleep(SLEEP_INDIVIDUAL)
    ind_df = download_individual(ticker, symbol)
    if ind_df.empty:
        return pd.Series(dtype=float), pd.DataFrame()
    price_col = extract_price_col(ind_df, ticker)
    if price_col is None:
        return pd.Series(dtype=float), pd.DataFrame()
    return ind_df[price_col].dropna(), ind_df


def compute_metrics(prices, completed_fri):
    r1y = rvol = rmacd = rsig = ''

    last_date = prices.index.max()

    # 1-Year Return
    year_ago = last_date - pd.Timedelta(days=365)
    idx = prices.index.get_indexer([year_ago], method='nearest')[0]
    if idx >= 0:
        ret = float(prices.iloc[-1]) / float(prices.iloc[idx]) - 1
        r1y = round(ret * 100, 2)

    # Daily Volatility (1 year, outliers stripped)
    prices_1y  = prices[prices.index >= (last_date - pd.Timedelta(days=365))]
    if len(prices_1y) > 1:
        daily_rets = prices_1y.pct_change().dropna()
        daily_rets = daily_rets[daily_rets.abs() <= 0.50]
        if len(daily_rets) > 1:
            rvol = round(float(daily_rets.std()) * 100, 4)

    # Weekly MACD (12, 24, 3) — completed Friday bars only
    weekly = prices.resample('W-FRI').last().dropna()
    weekly = weekly[weekly.index.date <= completed_fri]

    min_bars = MACD_SLOW + MACD_SIG
    if len(weekly) < min_bars:
        rsig = 'Insufficient Data'
    else:
        ema_fast    = weekly.ewm(span=MACD_FAST, adjust=False).mean()
        ema_slow    = weekly.ewm(span=MACD_SLOW, adjust=False).mean()
        macd_line   = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=MACD_SIG, adjust=False).mean()
        diff        = macd_line - signal_line

        current_diff = float(diff.iloc[-1])
        rmacd    = round(current_diff, 4)
        is_bull  = current_diff > 0

        weeks = 0
        for j in range(len(diff) - 1, -1, -1):
            val = float(diff.iloc[j])
            if (is_bull and val > 0) or (not is_bull and val <= 0):
                weeks += 1
            else:
                break
            if weeks >= MAX_WEEKS:
                break

        w_str = f"{weeks}+" if weeks >= MAX_WEEKS else str(weeks)
        rsig = (
            ("Strong Buy"          if weeks == 1 else f"Green {w_str} weeks")
            if is_bull else
            ("Strong Sell"         if weeks == 1 else f"Red {w_str} weeks")
        )

    return r1y, rvol, rmacd, rsig


# ── Google Sheets connection ───────────────────────────────────────────────────
scope  = ["https://spreadsheets.google.com/feeds",
          "https://www.googleapis.com/auth/drive"]
creds  = Credentials.from_service_account_file(CREDS_PATH, scopes=scope)
client = gspread.authorize(creds)

spreadsheet = client.open(SHEET_NAME)
existing_ws = [ws.title for ws in spreadsheet.worksheets()]
if WORKSHEET_NAME not in existing_ws:
    spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows=200, cols=10)
    print(f"  Created new worksheet: '{WORKSHEET_NAME}'")
sheet = spreadsheet.worksheet(WORKSHEET_NAME)

# ── Ensure metric headers exist (never overwrite your data columns A–D) ────────
header = sheet.row_values(HEADER_ROW)

def ensure_header(col_idx, label):
    if len(header) < col_idx or not header[col_idx - 1].strip():
        cell = gspread.utils.rowcol_to_a1(HEADER_ROW, col_idx)
        sheet.update(range_name=cell, values=[[label]])
        print(f"  Header added: '{label}' → {cell}")
        time.sleep(0.5)

ensure_header(COL_1Y_RETURN,  '1 Year Return %')
ensure_header(COL_VOLATILITY, 'Daily Volatility %')
ensure_header(COL_MACD_DIFF,  'Weekly MACD Diff')
ensure_header(COL_SIGNAL,     'MACD Signal')

# ── Read ETF list from sheet (source of truth) ─────────────────────────────────
all_rows = sheet.get_all_values()
etfs = []
skipped = []

for i, row in enumerate(all_rows[START_ROW - 1:], start=START_ROW):
    symbol = row[COL_SYMBOL - 1].strip() if len(row) >= COL_SYMBOL else ''
    if not symbol:
        continue
    # Skip comment/section rows (e.g. rows where col A starts with # or --)
    if symbol.startswith('#') or symbol.startswith('--'):
        skipped.append(symbol)
        continue
    etfs.append({
        'row':    i,
        'symbol': symbol,
        'ticker': get_yf_ticker(symbol),
    })

if skipped:
    print(f"  Skipped {len(skipped)} comment/divider rows: {skipped}")

completed_fri = last_completed_friday()
total_batches = max(1, (len(etfs) - 1) // BATCH_SIZE + 1)
print(f"\nFound {len(etfs)} ETFs across {total_batches} batch(es) "
      f"| Completed weeks up to: {completed_fri}")
print("─" * 65)

if not etfs:
    print("No ETF symbols found in sheet — add symbols to column A and re-run.")
    raise SystemExit(0)

# ── Batch download → compute metrics ──────────────────────────────────────────
batch_updates = []   # collected throughout; written in one pass at the end

for b_start in range(0, len(etfs), BATCH_SIZE):
    batch         = etfs[b_start : b_start + BATCH_SIZE]
    b_num         = b_start // BATCH_SIZE + 1
    batch_tickers = [item['ticker'] for item in batch]

    print(f"\n⬇️  Batch {b_num}/{total_batches} — "
          f"downloading {len(batch_tickers)} tickers...")
    try:
        if len(batch_tickers) == 1:
            batch_df = yf.download(
                batch_tickers[0], period="3y", interval="1d", progress=False)
        else:
            batch_df = yf.download(
                batch_tickers, period="3y", interval="1d", progress=False)
        print(f"   Batch {b_num} downloaded — {len(batch_df)} daily rows")
    except Exception as e:
        print(f"   ⚠️  Batch {b_num} download failed ({e}) "
              f"— will retry each ticker individually")
        batch_df = pd.DataFrame()

    for item in batch:
        symbol  = item['symbol']
        ticker  = item['ticker']
        row_num = item['row']

        r1y = rvol = rmacd = rsig = ''
        try:
            prices, _ = get_prices(batch_df, ticker, batch_tickers, symbol)
            if prices.empty:
                print(f"   ⚠️  {symbol:14}: no usable price data")
            else:
                r1y, rvol, rmacd, rsig = compute_metrics(prices, completed_fri)
                print(f"   ✅ {symbol:14} | "
                      f"1Y={str(r1y)+'%':>9}  "
                      f"Vol={str(rvol)+'%':>8}  "
                      f"MACD={str(rmacd):>10}  → {rsig}")
        except Exception as e:
            print(f"   ❌ {symbol:14}: {e}")

        start_cell = gspread.utils.rowcol_to_a1(row_num, COL_1Y_RETURN)
        end_cell   = gspread.utils.rowcol_to_a1(row_num, COL_SIGNAL)
        batch_updates.append({
            'range':  f"{start_cell}:{end_cell}",
            'values': [[r1y, rvol, rmacd, rsig]],
        })

    if b_start + BATCH_SIZE < len(etfs):
        print(f"   ⏳ Waiting {SLEEP_BETWEEN_BATCHES}s before next batch...")
        time.sleep(SLEEP_BETWEEN_BATCHES)

# ── Write all results back to sheet in chunks ──────────────────────────────────
print(f"\n📤 Writing {len(batch_updates)} rows back to sheet "
      f"({WRITE_CHUNK} rows per API call)...")

for i in range(0, len(batch_updates), WRITE_CHUNK):
    chunk = batch_updates[i : i + WRITE_CHUNK]
    sheet.batch_update(chunk)
    print(f"   Wrote rows {i + 1}–{min(i + WRITE_CHUNK, len(batch_updates))}")
    time.sleep(1)   # stay inside Google Sheets API quota

print(f"\n✅ Done — {len(etfs)} ETFs updated in '{WORKSHEET_NAME}'.")
print(f"   Tip: add new ETFs directly in the sheet (col A = NSE symbol), "
      f"then re-run this script.")
