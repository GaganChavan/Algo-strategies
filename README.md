# OpenAlgo – Context & Reference (Zerodha | Python | NSE Equity & F&O)

## My Setup
- **Broker:** Zerodha (Kite)
- **Language:** Python
- **Segments:** NSE Equity, NSE F&O (NIFTY, BANKNIFTY, FINNIFTY, Stocks)
- **Host:** `http://127.0.0.1:5000` (local) — swap with ngrok/custom domain for remote
- **WebSocket:** `ws://127.0.0.1:8765`
- **API Key:** stored in env var `OPENALGO_API_KEY`

---

## Installation & Initialization

```bash
pip install openalgo
```

```python
import os
from openalgo import api

client = api(
    api_key=os.environ["OPENALGO_API_KEY"],
    host="http://127.0.0.1:5000",
    ws_url="ws://127.0.0.1:8765"   # needed only for WebSocket streaming
)
```

---

## Order Constants

### Exchange
| Constant | Use For |
|----------|---------|
| `NSE`    | NSE Equity (cash segment) |
| `NFO`    | NSE F&O (futures & options) |
| `NSE_INDEX` | Index-based options orders (NIFTY, BANKNIFTY, etc.) via optionsorder API |
| `BSE`    | BSE Equity (if needed) |

### Product Type
| Constant | Meaning |
|----------|---------|
| `MIS`    | Intraday (auto-squared off by broker) |
| `CNC`    | Delivery / Cash & Carry (equity only) |
| `NRML`   | Carry forward F&O positions overnight |

> ⚠️ `CNC` is **not** supported for options trading. Use `MIS` or `NRML` for F&O.

### Price Type
| Constant | Meaning |
|----------|---------|
| `MARKET` | Execute at market price |
| `LIMIT`  | Execute at specified price |
| `SL`     | Stoploss Limit order (needs `price` + `trigger_price`) |
| `SL-M`   | Stoploss Market order (needs `trigger_price`) |

### Action
| Constant | Meaning |
|----------|---------|
| `BUY`    | Buy / Long entry |
| `SELL`   | Sell / Short entry or exit |

---

## Symbol Format

### NSE Equity
Plain uppercase ticker: `RELIANCE`, `INFY`, `TATAMOTORS`, `HDFCBANK`

### NSE Futures (NFO)
`NIFTY25JULFUT`, `BANKNIFTY25MAYFUT`, `RELIANCE25JUNFUT`
Format: `{UNDERLYING}{YY}{MON}FUT`

### NSE Options (NFO)
`NIFTY25MAY24000CE`, `BANKNIFTY25APR52000PE`
Format: `{UNDERLYING}{YY}{MON}{STRIKE}{CE|PE}`

> For options, prefer using the `optionsorder` API (auto-resolves symbol) rather than hardcoding option symbols manually.

### Index Underlying (for optionsorder)
| Index | Underlying String |
|-------|-------------------|
| Nifty 50 | `NIFTY` |
| Bank Nifty | `BANKNIFTY` |
| Fin Nifty | `FINNIFTY` |
| Midcap Nifty | `MIDCPNIFTY` |

### Lot Sizes (as of 2025)
| Index | Lot Size |
|-------|----------|
| NIFTY | 75 |
| BANKNIFTY | 30 |
| FINNIFTY | 65 |

---

## Core Order APIs

### 1. placeorder — Standard Order
```python
# Market order (equity intraday)
response = client.placeorder(
    strategy="MyStrategy",
    symbol="RELIANCE",
    action="BUY",
    exchange="NSE",
    price_type="MARKET",
    product="MIS",
    quantity=1
)

# Limit order (equity delivery)
response = client.placeorder(
    strategy="MyStrategy",
    symbol="INFY",
    action="BUY",
    exchange="NSE",
    price_type="LIMIT",
    product="CNC",
    quantity=1,
    price="1500",
    trigger_price="0",
    disclosed_quantity="0"
)

# F&O futures order
response = client.placeorder(
    strategy="MyStrategy",
    symbol="NIFTY25JULFUT",
    action="BUY",
    exchange="NFO",
    price_type="MARKET",
    product="NRML",
    quantity=75
)
```

### 2. placesmartorder — With Position Sizing
Automatically checks your open position and adjusts order quantity to reach `position_size`.
```python
response = client.placesmartorder(
    strategy="MyStrategy",
    symbol="NIFTY25JULFUT",
    action="BUY",
    exchange="NFO",
    price_type="MARKET",
    product="NRML",
    quantity=75,
    position_size=75   # desired net position
)
```
> Use `position_size=0` to close/flatten a position.

### 3. optionsorder — Auto-Resolve Options Symbol
Avoids hardcoding option symbols. System resolves the actual symbol based on underlying + offset.
```python
# Buy ATM NIFTY CE
response = client.optionsorder(
    strategy="NiftyStrategy",
    underlying="NIFTY",
    exchange="NSE_INDEX",
    expiry_date="30DEC25",   # format: DDMMMYY e.g. "03APR25"
    offset="ATM",            # ATM, ITM1, ITM2, OTM1, OTM2, ...
    option_type="CE",        # CE or PE
    action="BUY",
    quantity=75,
    pricetype="MARKET",
    product="MIS"
)
```

### 4. basketorder — Multiple Orders at Once
```python
orders = [
    {"symbol": "RELIANCE", "exchange": "NSE", "action": "BUY",  "quantity": 1, "pricetype": "MARKET", "product": "MIS"},
    {"symbol": "INFY",     "exchange": "NSE", "action": "SELL", "quantity": 1, "pricetype": "MARKET", "product": "MIS"},
]
response = client.basketorder(orders=orders)
```

### 5. splitorder — Break Large Orders
```python
response = client.splitorder(
    symbol="YESBANK",
    exchange="NSE",
    action="SELL",
    quantity=105,
    splitsize=20,
    price_type="MARKET",
    product="MIS"
)
```

---

## Order Management APIs

### Modify Order
```python
response = client.modifyorder(
    order_id="250408001002736",
    strategy="MyStrategy",
    symbol="RELIANCE",
    action="BUY",
    exchange="NSE",
    price_type="LIMIT",
    product="CNC",
    quantity=1,
    price=2900.5
)
```

### Cancel Specific Order
```python
response = client.cancelorder(order_id="250408001002736")
```

### Cancel All Orders
```python
response = client.cancelallorder()
```

### Close All Positions
```python
response = client.closeposition()
```

### Order Status
```python
response = client.orderstatus(
    order_id="250408001002736",
    strategy="MyStrategy"
)
# response["data"]["order_status"] → "complete" | "open" | "rejected" etc.
```

### Open Position for a Symbol
```python
response = client.openposition(
    strategy="MyStrategy",
    symbol="NIFTY25JULFUT",
    exchange="NFO",
    product="NRML"
)
```

---

## Account & Portfolio APIs

```python
# Order book
response = client.orderbook()

# Trade book
response = client.tradebook()

# Position book (open positions)
response = client.positionbook()

# Holdings (equity delivery)
response = client.holdings()

# Available funds
response = client.funds()

# Margin required for a trade
response = client.margin(
    symbol="NIFTY25JULFUT",
    exchange="NFO",
    action="BUY",
    product="NRML",
    quantity=75,
    price_type="MARKET"
)
```

---

## Market Data APIs

### Quotes (Snapshot)
```python
response = client.quotes(symbol="RELIANCE", exchange="NSE")
# Returns: ltp, open, high, low, close, volume, etc.
```

### Market Depth
```python
response = client.depth(symbol="NIFTY25JULFUT", exchange="NFO")
```

### Historical Data
```python
response = client.history(
    symbol="NIFTY25JULFUT",
    exchange="NFO",
    interval="5m",          # 1m, 3m, 5m, 10m, 15m, 30m, 1h, 1d
    start_date="2025-01-01",
    end_date="2025-01-31"
)
# Returns a pandas DataFrame or list of OHLCV candles
```

### Supported Intervals
```python
response = client.intervals()
```

---

## WebSocket Streaming (Real-Time)

```python
import time

# LTP streaming
instruments = [
    {"exchange": "NSE", "symbol": "RELIANCE"},
    {"exchange": "NFO", "symbol": "NIFTY25JULFUT"}
]

def on_ltp(data):
    print("LTP:", data)

client.connect()
client.subscribe_ltp(instruments, on_data_received=on_ltp)

try:
    time.sleep(30)
finally:
    client.unsubscribe_ltp(instruments)
    client.disconnect()
```

Other subscribe methods: `subscribe_quotes()`, `subscribe_depth()`

---

## Utility APIs

```python
# Search for a symbol
response = client.search(query="NIFTY", exchange="NFO")

# Resolve exact option symbol
response = client.optionsymbol(
    underlying="NIFTY",
    exchange="NSE_INDEX",
    expiry_date="03APR25",
    offset="ATM",
    option_type="CE"
)

# Get option chain
response = client.optionchain(underlying="NIFTY", exchange="NSE_INDEX", expiry_date="03APR25")

# Get expiry dates
response = client.expiry(underlying="NIFTY", exchange="NSE_INDEX")

# Option greeks
response = client.optiongreeks(underlying="NIFTY", exchange="NSE_INDEX", expiry_date="03APR25")
```

---

## Typical Response Format

```json
{
  "status": "success",
  "orderid": "250408001002736"
}
```

Error response:
```json
{
  "status": "error",
  "message": "Reason for failure"
}
```

Always check `response["status"] == "success"` before proceeding.

---

## Strategy Pattern Template

```python
import os
from openalgo import api

client = api(
    api_key=os.environ["OPENALGO_API_KEY"],
    host="http://127.0.0.1:5000"
)

STRATEGY = "MyStrategyName"

def place_buy(symbol, exchange, product, quantity, price_type="MARKET", price=0):
    resp = client.placeorder(
        strategy=STRATEGY,
        symbol=symbol,
        action="BUY",
        exchange=exchange,
        price_type=price_type,
        product=product,
        quantity=quantity,
        price=str(price) if price else "0"
    )
    if resp.get("status") == "success":
        print(f"BUY order placed: {resp['orderid']}")
    else:
        print(f"BUY failed: {resp.get('message')}")
    return resp

def place_sell(symbol, exchange, product, quantity, price_type="MARKET", price=0):
    resp = client.placeorder(
        strategy=STRATEGY,
        symbol=symbol,
        action="SELL",
        exchange=exchange,
        price_type=price_type,
        product=product,
        quantity=quantity,
        price=str(price) if price else "0"
    )
    if resp.get("status") == "success":
        print(f"SELL order placed: {resp['orderid']}")
    else:
        print(f"SELL failed: {resp.get('message')}")
    return resp
```

---

## Common Gotchas

- `quantity` and `price` are sometimes expected as strings — pass `str(value)` when in doubt.
- `CNC` is only valid for equity (NSE/BSE). Never use it for NFO.
- For F&O intraday use `MIS`; for overnight/positional use `NRML`.
- `optionsorder` uses `pricetype` (no underscore), while `placeorder` uses `price_type` (with underscore). Watch the key name.
- Option lot sizes must be multiples of the lot size (75 for NIFTY, 30 for BANKNIFTY, 65 for FINNIFTY).
- Always start OpenAlgo server before running strategies: `python app.py` inside the repo.
- Zerodha Kite login session must be active (refreshed daily).
- For expiry_date format use: `03APR25`, `30DEC25` (DDMMMYY, uppercase).

---

## HTTP Rate Limiting
OpenAlgo applies rate limiting. Space out bulk order calls with `time.sleep(0.2)` between requests to avoid hitting limits.

---

## Links
- Docs: https://docs.openalgo.in
- GitHub: https://github.com/marketcalls/openalgo
- PyPI: https://pypi.org/project/openalgo/
