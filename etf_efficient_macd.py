import yfinance as yf
import pandas as pd
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
import gspread
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import numpy as np
import time
# Google Sheets Integration
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(r'/Users/gagankumarchavan/Documents/API Cred/noble-aquifer-437514-k4-a50658fe7247.json', scopes=scope)
client = gspread.authorize(creds)
#sheet = client.open("My ETF Portfolio tracker").worksheet("Efficient ETFs")
sheet = client.open("My ETF Portfolio tracker").worksheet("Efficient ETFs 1")
# Fetch column names from row 2
column_names = sheet.row_values(3)
# Find column indices for CMP
column_indices = {}
column_indices['CMP'] = column_names.index('CMP') + 1
# Fetch stock symbols from column B (Script column)
stock_symbols = sheet.col_values(2)[3:11]  # Skipping header rows
def get_daily_returns(etfs, period="1y"):
    df = pd.DataFrame()
    for symbol in etfs:
        data = yf.download(symbol + ".NS", period=period, progress=False)
        if data.empty:
            print(f"No data for {symbol}")
            continue
        price_col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
        df[symbol] = data[price_col].pct_change()
    return df.dropna()
def update_return_volatility_sharpe(sheet, stock_symbols):
    col_names = sheet.row_values(3)
    col_indices = {
        'Avg Daily Return': col_names.index('Avg Daily Return') + 1,
        'Volatility': col_names.index('Volatility') + 1,
        'Sharpe Ratio (Daily)': col_names.index('Sharpe Ratio (Daily)') + 1
    }
    start_row = 4
    risk_free_rate_daily = 0.07 / 252
    for i, symbol in enumerate(stock_symbols):
        try:
            ticker = symbol + ".NS"
            data = yf.download(ticker, period="1y", progress=False)
            if data.empty:
                print(f"No data for {symbol}, skipping.")
                continue
            price_col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
            daily_returns = data[price_col].pct_change().dropna()
            avg_return = float(daily_returns.mean())
            volatility = float(daily_returns.std())
            sharpe_ratio = 0 if volatility == 0 or pd.isna(volatility) else (avg_return - risk_free_rate_daily) / volatility
            row = start_row + i
            update_range = f"{gspread.utils.rowcol_to_a1(row, col_indices['Avg Daily Return'])}:{gspread.utils.rowcol_to_a1(row, col_indices['Sharpe Ratio (Daily)'])}"
            update_values = [[round(avg_return, 6), round(volatility, 6), round(sharpe_ratio, 6)]]
            sheet.update(range_name=update_range, values=update_values)
            print(f"✅ Metrics updated for {symbol}  Sharpe={sharpe_ratio:.4f}")
        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")
def check_macd_negative(etfs):
    """
    Check which ETFs have negative monthly MACD difference.
    Returns a dictionary with ETF symbols as keys and boolean values indicating negative MACD.
    """
    macd_status = {}
    
    for symbol in etfs:
        actual_ticker = symbol + ".NS"
        try:
            # Download DAILY data for >3 years
            df = yf.download(actual_ticker, period="1100d", interval="1d", progress=False)
            
            # Fallback logic for price_col
            if isinstance(df.columns, pd.MultiIndex):
                if ('Adj Close', actual_ticker) in df.columns:
                    price_col = ('Adj Close', actual_ticker)
                elif ('Close', actual_ticker) in df.columns:
                    price_col = ('Close', actual_ticker)
                else:
                    price_col = None
            else:
                if 'Adj Close' in df.columns:
                    price_col = 'Adj Close'
                elif 'Close' in df.columns:
                    price_col = 'Close'
                else:
                    price_col = None

            # MACD Monthly (12,24,3) Calculation
            if price_col and df.shape[0] > 0:
                monthly = df[price_col].resample('ME').last().dropna()
                if len(monthly) >= 27:  # 24 for EMA24 + signal
                    ema_fast = monthly.ewm(span=12, adjust=False).mean()
                    ema_slow = monthly.ewm(span=24, adjust=False).mean()
                    macd_line = ema_fast - ema_slow
                    signal_line = macd_line.ewm(span=3, adjust=False).mean()
                    macd_diff = macd_line.iloc[-1] - signal_line.iloc[-1]
                    
                    macd_status[symbol] = macd_diff < 0
                    print(f"{symbol} MACD Difference: {macd_diff} ({'Negative' if macd_diff < 0 else 'Positive/Neutral'})")
                else:
                    macd_status[symbol] = False
            else:
                macd_status[symbol] = False
                
        except Exception as e:
            print(f"Error checking MACD for {symbol}: {e}")
            macd_status[symbol] = False
            
    return macd_status

def calculate_optimal_weights_and_update(etfs, sheet, investment_amount, risk_free_rate_annual=0.065, min_weight=0.0625):
    print("🔄 Calculating Efficient Frontier Weights...")
    
    # Check MACD status for all ETFs
    macd_status = check_macd_negative(etfs)
    
    # Identify ETFs with negative MACD
    negative_macd_etfs = [etf for etf, is_negative in macd_status.items() if is_negative]
    positive_macd_etfs = [etf for etf, is_negative in macd_status.items() if not is_negative]
    
    print(f"🚨 ETFs with negative MACD (fixed at 6.25%): {negative_macd_etfs}")
    print(f"✅ ETFs with positive/neutral MACD (to be optimized): {positive_macd_etfs}")
    
    # Calculate total fixed weight for negative MACD ETFs
    num_negative_etfs = len(negative_macd_etfs)
    total_fixed_weight = num_negative_etfs * min_weight
    
    # Check if we can accommodate minimum weights for all ETFs
    total_min_weight_required = len(etfs) * min_weight
    
    if total_min_weight_required > 1.0:
        print(f"⚠️ Cannot allocate minimum {min_weight*100}% to each of {len(etfs)} ETFs (would require {total_min_weight_required*100}%). Using equal allocation.")
        equal_weight = 1.0 / len(etfs)
        optimal_weights = np.array([equal_weight] * len(etfs))
    else:
        # Initialize weights array
        optimal_weights = np.zeros(len(etfs))
        
        # Set fixed weights for negative MACD ETFs
        for i, etf in enumerate(etfs):
            if etf in negative_macd_etfs:
                optimal_weights[i] = min_weight
        
        # Calculate remaining weight to allocate among positive MACD ETFs
        remaining_weight = 1.0 - total_fixed_weight
        num_positive_etfs = len(positive_macd_etfs)
        
        if num_positive_etfs == 0:
            # All ETFs have negative MACD
            print("All ETFs have negative MACD. All weights set to 6.25%.")
        elif remaining_weight <= 0:
            print("No remaining weight to allocate. All weights set to minimum.")
        else:
            # Check if remaining weight can satisfy minimum constraints for positive ETFs
            min_weight_for_positive = num_positive_etfs * min_weight
            
            if remaining_weight < min_weight_for_positive:
                print(f"⚠️ Remaining weight ({remaining_weight*100:.2f}%) insufficient for minimum allocation to positive MACD ETFs.")
                print("Setting all positive MACD ETFs to minimum weight and redistributing.")
                
                # Set all positive ETFs to minimum weight
                for i, etf in enumerate(etfs):
                    if etf in positive_macd_etfs:
                        optimal_weights[i] = min_weight
                
                # Normalize to ensure sum = 1
                optimal_weights = optimal_weights / optimal_weights.sum()
            else:
                # Optimize positive MACD ETFs with minimum weight constraint
                if num_positive_etfs == 1:
                    # Only one positive ETF gets all remaining weight
                    for i, etf in enumerate(etfs):
                        if etf in positive_macd_etfs:
                            optimal_weights[i] = remaining_weight
                else:
                    # Optimize multiple positive ETFs
                    returns_df = get_daily_returns(positive_macd_etfs)
                    
                    if not returns_df.empty:
                        avg_returns = returns_df.mean()
                        cov_matrix = returns_df.cov()
                        risk_free_daily = risk_free_rate_annual / 252
                        
                        np.random.seed(42)
                        results = {'Sharpe': [], 'Weights': []}
                        iterations = 0
                        valid_portfolios = 0
                        max_iterations = 10000
                        
                        while valid_portfolios < 5000 and iterations < max_iterations:
                            iterations += 1
                            
                            # Generate random weights that sum to remaining_weight
                            temp_weights = np.random.dirichlet(np.ones(num_positive_etfs), 1)[0]
                            scaled_weights = temp_weights * remaining_weight
                            
                            # Check if all weights meet minimum requirement
                            if np.all(scaled_weights >= min_weight):
                                port_return = np.dot(scaled_weights, avg_returns)
                                port_vol = np.sqrt(np.dot(scaled_weights.T, np.dot(cov_matrix, scaled_weights)))
                                sharpe = (port_return - risk_free_daily) / port_vol if port_vol > 0 else 0
                                
                                results['Sharpe'].append(sharpe)
                                results['Weights'].append(scaled_weights)
                                valid_portfolios += 1

                        if results['Weights']:
                            # Find best portfolio
                            df_results = pd.DataFrame
                            df_results = pd.DataFrame(results)
                            best_idx = df_results['Sharpe'].idxmax()
                            best_weights = df_results.loc[best_idx, 'Weights']
                            
                            # Assign optimized weights to positive MACD ETFs
                            positive_etf_idx = 0
                            for i, etf in enumerate(etfs):
                                if etf in positive_macd_etfs:
                                    optimal_weights[i] = best_weights[positive_etf_idx]
                                    positive_etf_idx += 1
                                    
                            print(f"✅ Optimized {num_positive_etfs} ETFs with {valid_portfolios} valid portfolios found.")
                        else:
                            print(f"⚠️ No valid portfolios found with minimum weight {min_weight*100}%. Using equal allocation for positive MACD ETFs.")
                            # Fallback: distribute remaining weight equally among positive ETFs
                            equal_remaining_weight = remaining_weight / num_positive_etfs
                            for i, etf in enumerate(etfs):
                                if etf in positive_macd_etfs:
                                    optimal_weights[i] = max(equal_remaining_weight, min_weight)
                            
                            # Renormalize if needed
                            if optimal_weights.sum() != 1.0:
                                optimal_weights = optimal_weights / optimal_weights.sum()
                    else:
                        print("⚠️ No returns data available for optimization. Using equal allocation for positive MACD ETFs.")
                        # Fallback: distribute remaining weight equally
                        equal_remaining_weight = remaining_weight / num_positive_etfs
                        for i, etf in enumerate(etfs):
                            if etf in positive_macd_etfs:
                                optimal_weights[i] = max(equal_remaining_weight, min_weight)
                        
                        # Renormalize if needed
                        if optimal_weights.sum() != 1.0:
                            optimal_weights = optimal_weights / optimal_weights.sum()

    # Verify all weights meet minimum requirement
    for i, (etf, weight) in enumerate(zip(etfs, optimal_weights)):
        if weight < min_weight - 1e-6:  # Small tolerance for floating point errors
            print(f"⚠️ Warning: {etf} weight {weight*100:.2f}% is below minimum {min_weight*100}%")

    # Calculate allocation amounts
    allocation_amounts = optimal_weights * investment_amount
    allocation_data = []
    
    # Print detailed weight allocation summary
    print("\n📊 Final Weight Allocation:")
    print("-" * 60)
    total_negative_allocation = 0
    total_positive_allocation = 0
    
    for i, (etf, weight, amount) in enumerate(zip(etfs, optimal_weights, allocation_amounts)):
        if etf in negative_macd_etfs:
            status = "🚨 Fixed (Negative MACD)"
            total_negative_allocation += weight
        else:
            status = "✅ Optimized (Min 6.25%)"
            total_positive_allocation += weight
            
        print(f"{etf:12} {weight*100:6.2f}% (₹{amount:8.2f}) - {status}")
        
        allocation_data.append([
            round(weight * 100, 2),
            round(amount, 2)
        ])
    
    print("-" * 60)
    print(f"Negative MACD ETFs: {len(negative_macd_etfs)} ETFs, {total_negative_allocation*100:.2f}% total weight")
    print(f"Positive MACD ETFs: {len(positive_macd_etfs)} ETFs, {total_positive_allocation*100:.2f}% total weight")
    print(f"Total allocation: {optimal_weights.sum()*100:.2f}%")
    
    # Verify minimum weight constraint
    min_actual_weight = optimal_weights.min()
    print(f"Minimum actual weight: {min_actual_weight*100:.2f}% (Required: {min_weight*100:.2f}%)")
    
    # Update the sheet
    header_row = sheet.row_values(3)
    weight_col = header_row.index('Optimal Weight %') + 1
    invest_col = header_row.index('Next Invest ₹') + 1
    start_row = 4

    range_to_update = f"{chr(64+weight_col)}{start_row}:{chr(64+invest_col)}{start_row + len(allocation_data) - 1}"
    
    try:
        sheet.update(range_to_update, allocation_data)
        print("\n✅ Weights updated successfully with both MACD constraints and minimum weight requirements!")
    except Exception as e:
        print(f"❌ Error updating sheet: {e}")

def update_macd_and_1y_return(sheet, stock_symbols):
    macd_diffs = []
    one_year_returns = []
    for symbol in stock_symbols:
        actual_ticker = symbol + ".NS"
        try:
            # --- Download DAILY data for >3 years ---
            df = yf.download(actual_ticker, period="1100d", interval="1d", progress=False)
            # Fallback logic for price_col
            if isinstance(df.columns, pd.MultiIndex):
                if ('Adj Close', actual_ticker) in df.columns:
                    price_col = ('Adj Close', actual_ticker)
                elif ('Close', actual_ticker) in df.columns:
                    price_col = ('Close', actual_ticker)
                else:
                    price_col = None
            else:
                if 'Adj Close' in df.columns:
                    price_col = 'Adj Close'
                elif 'Close' in df.columns:
                    price_col = 'Close'
                else:
                    price_col = None
            print(f"{symbol}: price_col={price_col}, df shape={df.shape}")
            print(df.head(2))  # For debugging
            # --- MACD Monthly (12,24,3) Calculation ---
            if price_col and df.shape[0] > 0:
                monthly = df[price_col].resample('ME').last().dropna()
                if len(monthly) >= 27:  # 24 for EMA24 + signal
                    ema_fast = monthly.ewm(span=12, adjust=False).mean()
                    ema_slow = monthly.ewm(span=24, adjust=False).mean()
                    macd_line = ema_fast - ema_slow
                    signal_line = macd_line.ewm(span=3, adjust=False).mean()
                    macd_diff = macd_line.iloc[-1] - signal_line.iloc[-1]
                    macd_diffs.append(round(float(macd_diff), 2))
                else:
                    macd_diffs.append('')
            else:
                macd_diffs.append('')
            # --- Accurate 1Y Return Calculation ---
            if price_col and df.shape[0] > 0:
                # Get latest trading day in your data (max index)
                last_day = df.index.max()
                past_day = last_day - pd.Timedelta(days=365)
                price_series = df[price_col].dropna()
                # Find nearest trading day to "1 year ago"
                nearest_idx = price_series.index.get_indexer([past_day], method='nearest')[0]
                price_1y_ago = price_series.iloc[nearest_idx]
                price_curr = price_series.iloc[-1]
                one_year_return = (price_curr / price_1y_ago) - 1
                one_year_returns.append(round(float(one_year_return) * 100, 2))
            else:
                one_year_returns.append('')
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            macd_diffs.append('')
            one_year_returns.append('')
    # Update sheet with values (ensure lengths match stock_symbols)
    start_row = 4
    end_row = start_row + len(stock_symbols) - 1
    print("MACD DIFFS:", macd_diffs)
    print("1Y RETURNS:", one_year_returns)
    sheet.batch_update([
        {'range': f'G{start_row}:G{end_row}', 'values': [[v] for v in macd_diffs]},
        {'range': f'H{start_row}:H{end_row}', 'values': [[v] for v in one_year_returns]}
    ])
def plot_efficient_frontier_with_cml(stock_symbols, risk_free_rate_annual=0.065):
    print("📊 Plotting Efficient Frontier and Capital Market Line...")
    returns_df = get_daily_returns(stock_symbols)
    if returns_df.empty:
        print("No return data found. Exiting.")
        return
    avg_returns = returns_df.mean()
    cov_matrix = returns_df.cov()
    num_assets = len(stock_symbols)
    risk_free_daily = risk_free_rate_annual / 252
    np.random.seed(42)
    results = {
        'Return': [],
        'Volatility': [],
        'Sharpe': [],
        'Weights': []
    }
    for _ in range(5000):
        weights = np.random.dirichlet(np.ones(num_assets), 1)[0]
        port_return = np.dot(weights, avg_returns)
        port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        sharpe = (port_return - risk_free_daily) / port_vol
        results['Return'].append(port_return)
        results['Volatility'].append(port_vol)
        results['Sharpe'].append(sharpe)
        results['Weights'].append(weights)
    df = pd.DataFrame(results)
    max_sharpe_idx = df['Sharpe'].idxmax()
    # Extract optimal portfolio stats
    max_sharpe_return = df.loc[max_sharpe_idx, 'Return']
    max_sharpe_vol = df.loc[max_sharpe_idx, 'Volatility']
    # Capital Market Line
    cml_x = np.linspace(0, max(df['Volatility']), 100)
    cml_y = risk_free_daily + (max_sharpe_return - risk_free_daily) / max_sharpe_vol * cml_x
    # Plot
    plt.figure(figsize=(10, 6))
    plt.scatter(df['Volatility'], df['Return'], c=df['Sharpe'], cmap='viridis', alpha=0.6, label='Portfolios')
    plt.colorbar(label='Sharpe Ratio')
    plt.plot(cml_x, cml_y, color='red', linestyle='--', label='Capital Market Line (CML)')
    plt.scatter(max_sharpe_vol, max_sharpe_return, color='gold', s=80, edgecolors='black', label='Max Sharpe Portfolio')
    plt.title('Efficient Frontier with Capital Market Line')
    plt.xlabel('Volatility (Standard Deviation)')
    plt.ylabel('Expected Return (Daily)')
    plt.legend()
    plt.grid(True)
    plt.savefig("my_plot.png", dpi=300, bbox_inches='tight')  # You can change the filename and format
    plt.show(block=False)   # 👈 Non-blocking show
    plt.pause(3)            # 👈 Pause for 3 seconds
    plt.close()             # 👈 Close the plot window
def update_qty_column(sheet, num_rows):
    header_row = sheet.row_values(3)
    cmp_col = header_row.index('CMP') + 1
    next_invest_col = header_row.index('Next Invest ₹') + 1
    qty_col = header_row.index('QTY') + 1
    start_row = 4
    end_row = start_row + num_rows - 1
    cmp_values = [sheet.cell(row, cmp_col).value for row in range(start_row, end_row + 1)]
    next_invest_values = [sheet.cell(row, next_invest_col).value for row in range(start_row, end_row + 1)]
    qty_values = []
    for invest, cmp in zip(next_invest_values, cmp_values):
        try:
            invest_amt = float(invest)
            cmp_val = float(cmp)
            qty = int(invest_amt // cmp_val) if cmp_val > 0 else 0
        except (ValueError, TypeError):
            qty = ''
        qty_values.append([qty])
    qty_range = f"{gspread.utils.rowcol_to_a1(start_row, qty_col)}:{gspread.utils.rowcol_to_a1(end_row, qty_col)}"
    sheet.update(qty_range, qty_values)
    print("✅ QTY column updated!")
def to_scalar(value):
    if isinstance(value, pd.Series):
        return float(value.iloc[0])
    return float(value) if not pd.isna(value) else None
# 2. For CMP batch update (fix start row, and pass C explicitly):
def batch_update(sheet, start_row, data, col_letter="C"):
    range_to_update = f"{col_letter}{start_row}:{col_letter}{start_row + len(data) - 1}"
    try:
        sheet.update(range_to_update, data)
        print(f"Batch update successful for rows {start_row} to {start_row + len(data) - 1}.")
    except Exception as e:
        print(f"Error during batch update: {e}")
def update_cmp_one_by_one(sheet, stock_symbols, start_row=4):
    """
    Update CMP for each stock symbol one by one (no batching).
    :param sheet: Google Sheet object
    :param stock_symbols: List of stock symbols
    :param start_row: Starting row in the sheet (default is 4)
    """
    for i, stock in enumerate(stock_symbols):
        try:
            print(f"Fetching CMP for {stock}...")
            data = yf.download(stock + ".NS", start="2024-05-01", end=datetime.today().strftime('%Y-%m-%d'))
            if data.empty:
                print(f"No data fetched for {stock}. Skipping.")
                continue
            cmp = float(data['Close'].iloc[-1].item())
            row_index = start_row + i
            sheet.update(f'C{row_index}', [[cmp]])  # Assuming CMP is in column C
            print(f"{stock} CMP updated: {cmp}")
        except Exception as e:
            print(f"Error fetching CMP for {stock}: {e}")
        time.sleep(1)  # Short wait to avoid request limits
# Main execution
investment_amount_cell = sheet.acell('H1').value
try:
    investment_amount = float(investment_amount_cell)
except (TypeError, ValueError):
    print("Invalid value in cell H1 for investment amount! Using default 50000.")
    investment_amount = 50000  # fallback
update_return_volatility_sharpe(sheet, stock_symbols)
calculate_optimal_weights_and_update(stock_symbols, sheet, investment_amount)
plot_efficient_frontier_with_cml(stock_symbols, risk_free_rate_annual=0.065)
update_macd_and_1y_return(sheet, stock_symbols)
update_cmp_one_by_one(sheet, stock_symbols, start_row=4)
update_qty_column(sheet, len(stock_symbols))