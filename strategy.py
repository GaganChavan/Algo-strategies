"""
ETF MACD Weekly Strategy
Buys NSE ETFs when weekly MACD (12,24,3) crosses above signal line.
Exits when weekly MACD crosses below signal line.
Uses CNC product for equity delivery / MTF on Zerodha via OpenAlgo.

Usage:
  python strategy.py          -> runs scheduler (fires every Monday 09:20 AM)
  python strategy.py --now    -> runs signal check immediately (for testing)
  python strategy.py --pf     -> prints current paper portfolio and exits
"""
import os
import sys
import time
from datetime import datetime

import schedule
from openalgo import api

from config import (
    API_KEY, HOST_URL, WS_URL,
    STRATEGY_NAME, PAPER_TRADING,
    LOOP_SLEEP
)
from signals      import get_all_signals
from executor     import execute_signals
from paper_trader import print_paper_portfolio


# --- Initialise OpenAlgo client (matches the official template) ---
client = api(
    api_key=API_KEY,
    host_url=HOST_URL
)


def print_mode_banner():
    if PAPER_TRADING:
        print("=" * 55)
        print("  PAPER TRADING MODE - no real orders will be placed")
        print("  Set PAPER_TRADING = False in config.py to go live")
        print("=" * 55)
    else:
        print("=" * 55)
        print("  LIVE TRADING MODE - real orders will be placed")
        print("=" * 55)


def run_strategy():
    """
    Core strategy logic - called once per scheduled run.
    1. Fetch weekly MACD signals for all ETFs
    2. Execute BUY / SELL orders (paper or live)
    3. Print portfolio summary (paper mode only)
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{STRATEGY_NAME}] Signal check at {now}")
    print_mode_banner()

    # Step 1: Compute MACD signals
    print("\nComputing weekly MACD signals...")
    signals = get_all_signals(client)

    print("\nSignal summary:")
    for symbol, signal in signals.items():
        print(f"  {symbol:15s} -> {signal}")

    # Step 2: Execute orders
    print("\nExecuting orders...")
    results = execute_signals(client, signals)

    # Step 3: Print results
    print(f"\n{len(results)} order(s) placed:")
    for r in results:
        status   = r["response"].get("status", "unknown")
        order_id = r["response"].get("orderid", "N/A")
        print(f"  {r['action']:4s} {r['symbol']:15s} -> status={status} orderid={order_id}")

    # Step 4: Show paper portfolio after every run
    if PAPER_TRADING:
        print_paper_portfolio(client)

    print(f"\nDone at {datetime.now().strftime('%H:%M:%S')}")


def main():
    """Main entry point - matches OpenAlgo template structure."""
    print(f"Strategy started: {STRATEGY_NAME}")
    print_mode_banner()

    # Show paper portfolio and exit
    if "--pf" in sys.argv:
        print_paper_portfolio(client)
        return

    # Run immediately (for testing)
    if "--now" in sys.argv:
        print("Running signal check now (--now flag)...")
        run_strategy()
        return

    # Scheduled mode - every Monday at 09:20 AM IST
    schedule.every().monday.at("09:20").do(run_strategy)
    print("Scheduler active. Will run every Monday at 09:20 AM IST.")
    print("Press Ctrl+C to stop.\n")

    while True:
        schedule.run_pending()
        time.sleep(LOOP_SLEEP)


if __name__ == "__main__":
    main()
