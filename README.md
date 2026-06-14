# ETF Portfolio Tracker — Python Scripts

A collection of Python scripts that automatically pull live market data and update a Google Sheet called **"My ETF Portfolio tracker"** with performance metrics, MACD signals, and smart investment allocations.

All scripts use **yfinance** to fetch price data and **gspread** to read/write Google Sheets.

---

## Scripts Overview

| Script | Sheet Tab | What It Tracks |
|--------|-----------|---------------|
| `etf_efficient_macd.py` | Efficient ETFs 1 | Indian ETFs — weights & frontier |
| `etf_global_macd.py` | Efficient ETFs 1 | Indian + International ETFs combined |
| `etf_leveraged_macd.py` | US ETF | US ETFs — weekly MACD signal |
| `etf_india_mtf_macd.py` | Indian ETF MTF | Indian NSE ETFs — weekly MACD signal |
| `etf_sheet13_tracker.py` | QQQ | Any US ticker — quick performance check |

---

## 1. `etf_efficient_macd.py`
### Indian ETF Optimizer (Efficient Frontier)

**What it does:**
This script looks at your Indian ETFs (NSE-listed, `.NS` suffix) and figures out the best way to split your next investment among them using a technique called the **Efficient Frontier** — a math-based method that maximizes return for a given level of risk.

**Step-by-step flow:**
1. Reads your ETF symbols from the **"Efficient ETFs 1"** sheet (rows 4–11, column B).
2. Calculates for each ETF over the past 1 year:
   - **Average Daily Return** — how much it grows on a typical day
   - **Volatility** — how much it swings up and down
   - **Sharpe Ratio** — return relative to risk (higher = better)
3. Calculates **Monthly MACD (12, 24, 3)** — a momentum signal:
   - If MACD is **negative** → that ETF gets a fixed minimum weight (6.25%) — it's in a downtrend
   - If MACD is **positive** → that ETF is eligible for a higher, optimized weight
4. Runs 5,000 random portfolio simulations and picks the one with the best Sharpe Ratio.
5. Calculates **1-Year Return** for each ETF.
6. Fetches live **CMP** (Current Market Price) from NSE.
7. Calculates **QTY** (how many units to buy = Investment ÷ CMP).
8. Plots the **Efficient Frontier chart** with the Capital Market Line and saves it as `my_plot.png`.
9. Writes everything back to Google Sheets.

**Investment amount** is read from cell `H1` of the sheet.

---

## 2. `etf_global_macd.py`
### Global ETF Optimizer (India + International)

**What it does:**
Same idea as `etf_efficient_macd.py`, but handles a **mixed portfolio** of both Indian ETFs (NSE) and International ETFs (e.g., US-listed like VOO, QQQ). International ETF prices are converted from USD to INR using a live exchange rate.

**Step-by-step flow:**
1. Reads ETF symbols from **"Efficient ETFs 1"** sheet (rows 15–22, column B).
2. Automatically classifies each ETF as Indian (`.NS`) or International based on a pre-defined list.
3. Fetches the live **USD/INR rate** (falls back to ₹85 if unavailable).
4. Calculates for each ETF (independently, to avoid mixing Indian/US trading calendar gaps):
   - Average Daily Return, Volatility, and Sharpe Ratio (1-year data)
5. Calculates **Monthly MACD (12, 24, 3)**:
   - Negative MACD → fixed minimum weight (6.25%)
   - Positive MACD → optimized via Efficient Frontier simulation
6. Runs 5,000 portfolio simulations on positive-MACD ETFs to find the best Sharpe Ratio mix.
7. Calculates **1-Year Return** for each ETF.
8. Fetches **CMP** in INR (international ETFs: USD price × USD/INR rate).
9. Calculates **QTY** (units to buy).
10. Plots the **Efficient Frontier** and saves as `my_plot_global.png`.
11. Writes all results back to Google Sheets.

**Investment amount** is read from cell `H1` of the sheet.

---

## 3. `etf_leveraged_macd.py`
### US ETF Weekly MACD Tracker

**What it does:**
Scans a large list of US (and global exchange) ETFs and calculates their **weekly MACD signal** along with 1-year return and volatility. It tells you whether each ETF is in a bullish or bearish trend, and for how many weeks.

**Step-by-step flow:**
1. Reads ETF symbols and exchange names from the **"US ETF"** sheet.
2. Converts exchange names (e.g., "NYSE ARCA", "LSE", "NSE") to the correct yfinance ticker suffix automatically.
3. Downloads **3 years of daily price data** in batches of 20 tickers at a time (to stay within Yahoo Finance rate limits).
4. For each ETF computes:
   - **1-Year Return %** — total return over the past year
   - **Daily Volatility %** — how much it moves day-to-day (outlier days filtered out)
   - **Weekly MACD (12, 24, 3)** — momentum signal using Friday weekly closes
   - **MACD Signal label** — plain English description like:
     - `"Strong Buy"` — just turned bullish this week
     - `"Green 5 weeks"` — has been bullish for 5 weeks
     - `"Red 3 weeks"` — has been bearish for 3 weeks
     - `"Strong Sell"` — just turned bearish
5. Retries individual tickers that fail in batch downloads.
6. Writes all results back to the sheet in chunks of 25 rows.

---

## 4. `etf_india_mtf_macd.py`
### Indian NSE ETF Weekly MACD Tracker (MTF Sheet)

**What it does:**
Same concept as `etf_leveraged_macd.py`, but built specifically for **Indian NSE ETFs**. It handles renamed tickers on Yahoo Finance (some NSE symbols don't match their Yahoo Finance names), and writes results to the **"Indian ETF MTF"** sheet — creating the sheet automatically if it doesn't exist yet.

**Step-by-step flow:**
1. Reads ETF symbols from the **"Indian ETF MTF"** sheet (column A). You manage columns A–D; the script only writes to E–H.
2. Applies a **symbol override map** for ETFs whose Yahoo Finance ticker differs from their NSE symbol (e.g., `UTINIFTETF` → `NIFTYBETA.NS`).
3. Skips comment or divider rows (rows starting with `#` or `--`).
4. Downloads **3 years of daily data** in batches of 20.
5. For each ETF computes:
   - **1-Year Return %**
   - **Daily Volatility %** (outliers stripped — days with >50% moves ignored)
   - **Weekly MACD (12, 24, 3)** using completed Friday closes only (respects NSE market hours)
   - **MACD Signal label** — same plain English format as above
6. Retries failed tickers individually with exponential backoff (2s, 4s, 8s).
7. Writes results back to the sheet in chunks.

**Creates the "Indian ETF MTF" worksheet automatically** if it's not already in your spreadsheet.

---

## 5. `etf_sheet13_tracker.py`
### Quick US Ticker Performance Snapshot

**What it does:**
The simplest script of the five. Give it a list of any US stock or ETF tickers in the **"QQQ"** sheet, and it fetches basic performance metrics for each one and updates the sheet. Great for quick comparisons.

**Step-by-step flow:**
1. Reads tickers from the **"QQQ"** sheet (column B, starting row 2).
2. For each ticker fetches:
   - **Full Name** — e.g., "Invesco QQQ Trust"
   - **CMP** (Current Market Price in USD)
   - **Avg Daily Return** — average daily % gain over the past year
   - **Volatility** — daily standard deviation over the past year
   - **Sharpe Ratio** — return-to-risk score (risk-free rate = 7% annual)
3. Writes all 5 values into columns A–F of the sheet, one row per ticker.
4. Prints a clean comparison table in the terminal at the end.

---

## Setup Requirements

```bash
pip install yfinance pandas gspread google-auth matplotlib numpy
```

- A **Google Service Account** JSON key file is required (stored at the path in the scripts).
- The service account must have **Editor access** to the "My ETF Portfolio tracker" Google Sheet.
- All scripts read the investment amount or ticker list directly from the sheet — no hardcoding needed.# Finance-Strategies
