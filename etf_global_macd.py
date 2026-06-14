import yfinance as yf
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np
import time

# Google Sheets Integration
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(
    r'/Users/gagankumarchavan/Documents/API Cred/noble-aquifer-437514-k4-a50658fe7247.json',
    scopes=scope
)
client = gspread.authorize(creds)
sheet = client.open("My ETF Portfolio tracker").worksheet("Efficient ETFs 1")

# Header at row 14, data rows 15-22
HEADER_ROW = 14
START_ROW = 15

# Read tickers from the sheet (column B, rows 15-22)
stock_symbols = [s for s in sheet.col_values(2)[14:22] if s.strip()]

# Pre-defined split: avoids noisy .NS probing for known international ETFs
INDIAN_ETFS = {'NIFTYIETF', 'MOMOMENTUM', 'GOLDCASE', 'SILVERIETF'}

ticker_map = {sym: (sym + ".NS" if sym in INDIAN_ETFS else sym) for sym in stock_symbols}
indian_symbols = [s for s in stock_symbols if s in INDIAN_ETFS]
international_symbols = [s for s in stock_symbols if s not in INDIAN_ETFS]
print(f"Indian ETFs   (.NS): {indian_symbols}")
print(f"International ETFs : {international_symbols}")


def get_usd_inr_rate():
    """Fetch live USD/INR rate; fallback to 85 if unavailable."""
    try:
        df = yf.download("USDINR=X", period="5d", progress=False)
        if not df.empty:
            price_col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
            return float(df[price_col].iloc[-1].item())
    except Exception as e:
        print(f"Warning: Could not fetch USD/INR rate: {e}")
    return 85.0


def extract_price_col(df, ticker):
    """Extract the correct price column from a yfinance DataFrame (handles MultiIndex)."""
    if isinstance(df.columns, pd.MultiIndex):
        for label in ['Adj Close', 'Close']:
            if (label, ticker) in df.columns:
                return (label, ticker)
        return None
    for label in ['Adj Close', 'Close']:
        if label in df.columns:
            return label
    return None


def get_daily_returns(etf_symbols, period="1y"):
    """Download daily % returns for a list of ETF symbols (uses ticker_map for correct tickers)."""
    df = pd.DataFrame()
    for symbol in etf_symbols:
        ticker = ticker_map.get(symbol, symbol)
        data = yf.download(ticker, period=period, progress=False)
        if data.empty:
            print(f"No data for {symbol} ({ticker})")
            continue
        price_col = extract_price_col(data, ticker)
        if price_col is None:
            print(f"No price column found for {symbol}")
            continue
        df[symbol] = data[price_col].pct_change()
    return df.dropna()


def update_return_volatility_sharpe(sheet, stock_symbols):
    """
    Calculates metrics for each ETF independently from its own full 1-year data.
    This avoids the cross-calendar dropna() bias that occurs when mixing Indian
    and US ETFs in a single aligned DataFrame.
    """
    col_names = sheet.row_values(HEADER_ROW)
    col_indices = {
        'Avg Daily Return': col_names.index('Avg Daily Return') + 1,
        'Volatility': col_names.index('Volatility') + 1,
        'Sharpe Ratio (Daily)': col_names.index('Sharpe Ratio (Daily)') + 1,
    }
    risk_free_rate_daily = 0.07 / 252
    for i, symbol in enumerate(stock_symbols):
        try:
            ticker = ticker_map.get(symbol, symbol)
            data = yf.download(ticker, period="1y", progress=False)
            if data.empty:
                print(f"No data for {symbol} ({ticker}), skipping.")
                continue
            price_col = extract_price_col(data, ticker)
            if price_col is None:
                print(f"No price column for {symbol}, skipping.")
                continue
            daily_returns = data[price_col].pct_change().dropna()
            avg_return = float(daily_returns.mean())
            volatility = float(daily_returns.std())
            sharpe = 0 if volatility == 0 or pd.isna(volatility) else (avg_return - risk_free_rate_daily) / volatility
            row = START_ROW + i
            update_range = (
                f"{gspread.utils.rowcol_to_a1(row, col_indices['Avg Daily Return'])}:"
                f"{gspread.utils.rowcol_to_a1(row, col_indices['Sharpe Ratio (Daily)'])}"
            )
            sheet.update(range_name=update_range, values=[[round(avg_return, 6), round(volatility, 6), round(sharpe, 6)]])
            print(f"✅ Metrics updated for {symbol} ({ticker})  Sharpe={sharpe:.4f}")
        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")


def read_macd_from_sheet(sheet, etfs):
    """
    Read MACD diff values already written to the sheet (col G).
    Returns dict {symbol: bool} — True if MACD diff is negative.
    Avoids re-downloading data that update_macd_and_1y_return already computed.
    """
    macd_col_values = sheet.col_values(7)          # column G (1-indexed)
    macd_status = {}
    for i, symbol in enumerate(etfs):
        sheet_row_idx = START_ROW - 1 + i          # 0-indexed into col_values list
        try:
            val = macd_col_values[sheet_row_idx]
            is_negative = bool(float(val) < 0)
            label = "Negative" if is_negative else "Positive"
            print(f"{symbol} MACD from sheet: {float(val):.4f} ({label})")
            macd_status[symbol] = is_negative
        except (IndexError, ValueError, TypeError):
            # Empty cell or non-numeric → insufficient data → treat as neutral
            print(f"{symbol} MACD from sheet: no value — treating as neutral")
            macd_status[symbol] = False
    return macd_status


def calculate_optimal_weights_and_update(etfs, sheet, investment_amount, risk_free_rate_annual=0.065, min_weight=0.0625):
    print("🔄 Calculating Efficient Frontier Weights (India + International)...")

    # Read MACD from sheet — same values already displayed, no second download
    macd_status = read_macd_from_sheet(sheet, etfs)
    negative_macd_etfs = [e for e, neg in macd_status.items() if neg]
    positive_macd_etfs = [e for e, neg in macd_status.items() if not neg]

    print(f"🚨 Negative MACD (fixed at {min_weight*100:.2f}%): {negative_macd_etfs}")
    print(f"✅ Positive/Neutral MACD (optimized): {positive_macd_etfs}")

    total_min_required = len(etfs) * min_weight
    if total_min_required > 1.0:
        print(f"⚠️ Cannot allocate {min_weight*100}% minimum to {len(etfs)} ETFs. Using equal weights.")
        optimal_weights = np.full(len(etfs), 1.0 / len(etfs))
    else:
        optimal_weights = np.zeros(len(etfs))
        for i, etf in enumerate(etfs):
            if etf in negative_macd_etfs:
                optimal_weights[i] = min_weight

        total_fixed_weight = len(negative_macd_etfs) * min_weight
        remaining_weight = 1.0 - total_fixed_weight
        num_positive = len(positive_macd_etfs)

        if num_positive == 0:
            print("All ETFs have negative MACD — all weights set to minimum.")
        elif remaining_weight <= 0:
            print("No remaining weight to allocate.")
        elif remaining_weight < num_positive * min_weight:
            # Not enough room to give every positive ETF the minimum —
            # split remaining_weight equally among them.
            # Negative MACD ETFs stay fixed at min_weight; do NOT normalise all weights.
            eq = remaining_weight / num_positive
            for i, etf in enumerate(etfs):
                if etf in positive_macd_etfs:
                    optimal_weights[i] = eq
        elif num_positive == 1:
            for i, etf in enumerate(etfs):
                if etf in positive_macd_etfs:
                    optimal_weights[i] = remaining_weight
        else:
            returns_df = get_daily_returns(positive_macd_etfs)
            if not returns_df.empty:
                avg_returns = returns_df.mean()
                cov_matrix = returns_df.cov()
                risk_free_daily = risk_free_rate_annual / 252
                np.random.seed(42)
                results = {'Sharpe': [], 'Weights': []}
                iterations, valid_portfolios = 0, 0

                while valid_portfolios < 5000 and iterations < 10000:
                    iterations += 1
                    temp = np.random.dirichlet(np.ones(num_positive), 1)[0]
                    scaled = temp * remaining_weight
                    if np.all(scaled >= min_weight):
                        ret = np.dot(scaled, avg_returns)
                        vol = np.sqrt(np.dot(scaled.T, np.dot(cov_matrix, scaled)))
                        sharpe = (ret - risk_free_daily) / vol if vol > 0 else 0
                        results['Sharpe'].append(sharpe)
                        results['Weights'].append(scaled)
                        valid_portfolios += 1

                if results['Weights']:
                    df_res = pd.DataFrame(results)
                    best_weights = df_res.loc[df_res['Sharpe'].idxmax(), 'Weights']
                    pos_idx = 0
                    for i, etf in enumerate(etfs):
                        if etf in positive_macd_etfs:
                            optimal_weights[i] = best_weights[pos_idx]
                            pos_idx += 1
                    print(f"✅ Optimized with {valid_portfolios} valid portfolios.")
                else:
                    print("⚠️ No valid portfolios found — using equal split for positive ETFs.")
                    eq = remaining_weight / num_positive
                    for i, etf in enumerate(etfs):
                        if etf in positive_macd_etfs:
                            optimal_weights[i] = eq
            else:
                print("⚠️ No returns data — using equal split for positive ETFs.")
                eq = remaining_weight / num_positive
                for i, etf in enumerate(etfs):
                    if etf in positive_macd_etfs:
                        optimal_weights[i] = eq

    # Sanity check
    for etf, weight in zip(etfs, optimal_weights):
        if weight < min_weight - 1e-6:
            print(f"⚠️ {etf} weight {weight*100:.2f}% is below minimum {min_weight*100}%")

    allocation_amounts = optimal_weights * investment_amount
    allocation_data = []

    print("\n📊 Final Weight Allocation (India + International):")
    print("-" * 75)
    for etf, weight, amount in zip(etfs, optimal_weights, allocation_amounts):
        etf_type = "🇮🇳" if ticker_map.get(etf, etf).endswith(".NS") else "🌍"
        status = "🚨 Fixed (Neg MACD)" if etf in negative_macd_etfs else "✅ Optimized"
        print(f"{etf_type} {etf:15} {weight*100:6.2f}%  ₹{amount:9.2f}  {status}")
        allocation_data.append([round(weight * 100, 2), round(amount, 2)])
    print("-" * 75)
    print(f"Total allocation: {optimal_weights.sum()*100:.2f}%")

    header_row = sheet.row_values(HEADER_ROW)
    weight_col = header_row.index('Optimal Weight %') + 1
    invest_col = header_row.index('Next Invest ₹') + 1
    end_row = START_ROW + len(allocation_data) - 1
    update_range = f"{chr(64 + weight_col)}{START_ROW}:{chr(64 + invest_col)}{end_row}"
    try:
        sheet.update(values=allocation_data, range_name=update_range)
        print("✅ Weights and Next Invest amounts updated in sheet!")
    except Exception as e:
        print(f"❌ Error updating sheet: {e}")


def update_macd_and_1y_return(sheet, stock_symbols):
    macd_diffs = []
    one_year_returns = []
    for symbol in stock_symbols:
        actual_ticker = ticker_map.get(symbol, symbol)
        try:
            df = yf.download(actual_ticker, period="1100d", interval="1d", progress=False)
            price_col = extract_price_col(df, actual_ticker)
            print(f"{symbol} ({actual_ticker}): price_col={price_col}, shape={df.shape}")

            # Monthly MACD (12, 24, 3)
            if price_col and df.shape[0] > 0:
                monthly = df[price_col].resample('ME').last().dropna()
                if len(monthly) >= 27:
                    ema_fast = monthly.ewm(span=12, adjust=False).mean()
                    ema_slow = monthly.ewm(span=24, adjust=False).mean()
                    macd_line = ema_fast - ema_slow
                    signal_line = macd_line.ewm(span=3, adjust=False).mean()
                    macd_diff = macd_line.iloc[-1] - signal_line.iloc[-1]
                    macd_diffs.append(round(float(macd_diff), 4))
                else:
                    macd_diffs.append('')
            else:
                macd_diffs.append('')

            # 1Y Return
            if price_col and df.shape[0] > 0:
                price_series = df[price_col].dropna()
                last_day = price_series.index.max()
                past_day = last_day - pd.Timedelta(days=365)
                nearest_idx = price_series.index.get_indexer([past_day], method='nearest')[0]
                one_year_return = (price_series.iloc[-1] / price_series.iloc[nearest_idx]) - 1
                one_year_returns.append(round(float(one_year_return) * 100, 2))
            else:
                one_year_returns.append('')
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            macd_diffs.append('')
            one_year_returns.append('')

    end_row = START_ROW + len(stock_symbols) - 1
    print("MACD DIFFS:", macd_diffs)
    print("1Y RETURNS:", one_year_returns)
    sheet.batch_update([
        {'range': f'G{START_ROW}:G{end_row}', 'values': [[v] for v in macd_diffs]},
        {'range': f'H{START_ROW}:H{end_row}', 'values': [[v] for v in one_year_returns]},
    ])
    print("✅ MACD and 1Y Return columns updated!")


def plot_efficient_frontier_with_cml(stock_symbols, risk_free_rate_annual=0.065):
    print("📊 Plotting Efficient Frontier with CML (India + International)...")
    returns_df = get_daily_returns(stock_symbols)
    if returns_df.empty:
        print("No return data. Skipping plot.")
        return
    avg_returns = returns_df.mean()
    cov_matrix = returns_df.cov()
    num_assets = len(stock_symbols)
    risk_free_daily = risk_free_rate_annual / 252
    np.random.seed(42)
    results = {'Return': [], 'Volatility': [], 'Sharpe': []}
    for _ in range(5000):
        w = np.random.dirichlet(np.ones(num_assets), 1)[0]
        ret = np.dot(w, avg_returns)
        vol = np.sqrt(np.dot(w.T, np.dot(cov_matrix, w)))
        results['Return'].append(ret)
        results['Volatility'].append(vol)
        results['Sharpe'].append((ret - risk_free_daily) / vol)
    df = pd.DataFrame(results)
    best = df.loc[df['Sharpe'].idxmax()]
    cml_x = np.linspace(0, df['Volatility'].max(), 100)
    cml_y = risk_free_daily + (best['Return'] - risk_free_daily) / best['Volatility'] * cml_x
    plt.figure(figsize=(10, 6))
    plt.scatter(df['Volatility'], df['Return'], c=df['Sharpe'], cmap='viridis', alpha=0.6, label='Portfolios')
    plt.colorbar(label='Sharpe Ratio')
    plt.plot(cml_x, cml_y, color='red', linestyle='--', label='Capital Market Line')
    plt.scatter(best['Volatility'], best['Return'], color='gold', s=100, edgecolors='black', label='Max Sharpe Portfolio')
    plt.title('Efficient Frontier — India + International ETFs')
    plt.xlabel('Volatility (Daily Std Dev)')
    plt.ylabel('Expected Return (Daily)')
    plt.legend()
    plt.grid(True)
    plt.savefig("my_plot_global.png", dpi=300, bbox_inches='tight')
    plt.show(block=False)
    plt.pause(3)
    plt.close()


def update_cmp_one_by_one(sheet, stock_symbols, usd_inr_rate):
    """
    Fetches CMP for each ETF.
    International ETFs: stores CMP in INR (USD × USD/INR rate) so QTY calc is consistent.
    """
    for i, stock in enumerate(stock_symbols):
        actual_ticker = ticker_map.get(stock, stock)
        is_international = not actual_ticker.endswith(".NS")
        try:
            print(f"Fetching CMP for {stock} ({actual_ticker})...")
            data = yf.download(actual_ticker, start="2024-05-01", end=datetime.today().strftime('%Y-%m-%d'))
            if data.empty:
                print(f"No data for {stock}. Skipping.")
                continue
            cmp_raw = float(data['Close'].iloc[-1].item())
            if is_international:
                cmp_inr = round(cmp_raw * usd_inr_rate, 2)
                print(f"{stock}: ${cmp_raw:.2f} × ₹{usd_inr_rate:.2f} = ₹{cmp_inr:.2f}")
                cmp_display = cmp_inr
            else:
                cmp_display = round(cmp_raw, 2)
                print(f"{stock}: ₹{cmp_display:.2f}")
            sheet.update(values=[[cmp_display]], range_name=f'C{START_ROW + i}')
        except Exception as e:
            print(f"Error fetching CMP for {stock}: {e}")
        time.sleep(1)


def update_qty_column(sheet, num_rows):
    """QTY = Next Invest ₹ ÷ CMP (CMP already stored in INR for all ETFs)."""
    header_row = sheet.row_values(HEADER_ROW)
    cmp_col = header_row.index('CMP') + 1
    next_invest_col = header_row.index('Next Invest ₹') + 1
    qty_col = header_row.index('QTY') + 1
    end_row = START_ROW + num_rows - 1

    cmp_values = [sheet.cell(r, cmp_col).value for r in range(START_ROW, end_row + 1)]
    invest_values = [sheet.cell(r, next_invest_col).value for r in range(START_ROW, end_row + 1)]
    qty_values = []
    for invest, cmp in zip(invest_values, cmp_values):
        try:
            qty = int(float(invest) // float(cmp)) if float(cmp) > 0 else 0
        except (ValueError, TypeError):
            qty = ''
        qty_values.append([qty])

    qty_range = (
        f"{gspread.utils.rowcol_to_a1(START_ROW, qty_col)}:"
        f"{gspread.utils.rowcol_to_a1(end_row, qty_col)}"
    )
    sheet.update(values=qty_values, range_name=qty_range)
    print("✅ QTY column updated!")


# ── Main Execution ──────────────────────────────────────────────────────────────

investment_amount_cell = sheet.acell('H1').value
try:
    investment_amount = float(investment_amount_cell)
except (TypeError, ValueError):
    print("Invalid value in H1. Using default ₹50,000.")
    investment_amount = 50000

usd_inr_rate = get_usd_inr_rate()
print(f"💱 USD/INR Rate: ₹{usd_inr_rate:.2f}\n")

update_return_volatility_sharpe(sheet, stock_symbols)
update_macd_and_1y_return(sheet, stock_symbols)           # ← MACD written first
calculate_optimal_weights_and_update(stock_symbols, sheet, investment_amount)  # ← reads MACD from sheet
plot_efficient_frontier_with_cml(stock_symbols, risk_free_rate_annual=0.065)
update_cmp_one_by_one(sheet, stock_symbols, usd_inr_rate)
update_qty_column(sheet, len(stock_symbols))
