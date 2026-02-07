# IBKR Paper Trading API

This project now has a **single recommended integration API**:

- `execute_trade(payload) -> TradeResult`

It performs validation, order construction, submission, and optional wait-for-terminal in one call.

Lower-level functions still exist in `src/service_api.py`, but backend integrations should normally call `execute_trade` only.

## 1) Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure env:

```bash
cp .env.example .env
```

`.env` values:
- `IB_HOST` default `127.0.0.1`
- `IB_PORT` default `7497` (TWS paper)
- `IB_CLIENT_ID` default `7`
- `ORDER_DB_PATH` default `data/orders.db`

## 2) Single In-Process API

Module: `src/trade_api.py`

Top-level exports from `src`:
- `TradeRequest`
- `execute_trade`
- `TradeResult`

### 2.1 Signature

```python
execute_trade(
    payload: dict | TradeRequest,
    *,
    config: Config | None = None,
    logger: logging.Logger | None = None,
    on_update: Callable[[dict], None] | None = None,
) -> TradeResult
```

### 2.2 Trade Payload

```python
{
  "order": {...},
  "transmit": false,
  "dry_run": false,
  "wait_for_terminal": false,
  "timeout": 5.0,
  "poll_interval": 1.0,
  "max_wait": null
}
```

`order` accepted shapes:
- `dict`
- JSON `str`
- `OrderRequest` object (internal/advanced use)

Behavior:
- `dry_run=True`: validates and builds order/contract, no submission.
- `wait_for_terminal=True`: after submit, waits for terminal status (`FILLED`, `CANCELLED`, etc.).
- `transmit=False` by default for safety.

### 2.3 TradeResult

```python
@dataclass(frozen=True)
class TradeResult:
    ok: bool
    submitted: bool = False
    dry_run: bool = False
    order_id: int | None = None
    status: str | None = None
    terminal: bool | None = None
    state: dict | None = None
    updates: list[dict] | None = None
    contract: dict | None = None
    order_payload: dict | None = None
    order_request: dict | None = None
    effective_order_ref: str | None = None
    errors: list[dict] | None = None
    error: str | None = None
```

Interpretation:
- `ok=True` means the requested workflow completed successfully.
- `submitted=True` means order submission was attempted and accepted by client path.
- `dry_run=True` means no network submission happened.
- `errors` is validation/runtime structured detail.
- `error` is top-level operation error (connect failure, watch timeout, etc).

## 3) Backend Integration Examples

### 3.1 Minimal Submit

```python
from src import execute_trade

result = execute_trade(
    {
        "order": {
            "action": "BUY",
            "symbol": "AAPL",
            "order_type": "MKT",
            "quantity": 1,
        },
        "transmit": False,
    }
)

if not result.ok:
    print(result.error, result.errors)
else:
    print(result.order_id, result.status)
```

### 3.2 Dry Run (No Submission)

```python
from src import execute_trade

result = execute_trade(
    {
        "order": {
            "action": "SELL",
            "symbol": "MSFT",
            "order_type": "LMT",
            "quantity": 2,
            "limit_price": 450.0,
        },
        "dry_run": True,
    }
)

print(result.ok, result.dry_run)
print(result.contract)
print(result.order_payload)
```

### 3.3 Submit + Wait for Terminal

```python
from src import execute_trade


def on_update(event: dict) -> None:
    print("update", event)


result = execute_trade(
    {
        "order": {
            "action": "BUY",
            "symbol": "AAPL",
            "order_type": "MKT",
            "quantity": 1,
        },
        "wait_for_terminal": True,
        "max_wait": 120,
    },
    on_update=on_update,
)

print(result.ok, result.terminal, result.status, result.error)
```

## 4) Order Schema

`OrderRequest` is defined in `src/domain/order_request.py`.

Required:
- `action`: `"BUY" | "SELL"`
- `symbol`: non-empty string
- `order_type`: `"MKT" | "LMT"`
- `quantity`: positive number

Defaults:
- `sec_type="STK"`
- `exchange="SMART"`
- `currency="USD"`
- `tif="DAY"`
- `transmit=False`

Conditional:
- `limit_price` required for `LMT`
- `limit_price` must be omitted for `MKT`

Optional:
- `primary_exch`
- `client_tag`
- `order_ref`

Validation behavior:
- Unknown fields rejected.
- Enum-like strings normalized uppercase.
- If both `client_tag` and `order_ref` are set, they must match.

## 5) CLI API (Secondary)

CLI remains available for scripts and manual ops:

```bash
python -m src.app health
python -m src.app validate --json-file examples/orders/mkt_buy_aapl.json
python -m src.app place --json-file examples/orders/mkt_buy_aapl.json
python -m src.app place --json-file examples/orders/mkt_buy_aapl.json --dry-run
python -m src.app watch --order-id 123
```

## 6) Persistence

Order state is persisted to SQLite at `ORDER_DB_PATH` (default `data/orders.db`).

Persisted data includes status/fill/error fields and full `raw_state`, enabling watch/recovery across process restarts.

## 7) Error Contract

Common cases:
- Validation failure:
  - `TradeResult.ok=False`
  - `TradeResult.errors=[...]`
- TWS unavailable/maintenance:
  - `TradeResult.ok=False`
  - `TradeResult.error="could not connect to TWS"`
- Watch timeout:
  - `TradeResult.ok=False`
  - `TradeResult.error="max_wait_exceeded"`

## 8) Recommended Usage Rule

If backend and trade logic are deployed together, use only:

- `TradeRequest` (optional typed wrapper)
- `execute_trade`
- `TradeResult`

Treat all lower-level modules as implementation details unless you need custom orchestration.
