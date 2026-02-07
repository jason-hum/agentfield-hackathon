# IBKR Paper Trading API

This project exposes two APIs:

1. In-process Python API (recommended for backend integration in the same deployable artifact)
2. CLI API (JSON over stdout)

The CLI is now a thin wrapper around the in-process API, so behavior is consistent.

## 1) Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Create env file:

```bash
cp .env.example .env
```

Set values in `.env`:

- `IB_HOST` default `127.0.0.1`
- `IB_PORT` default `7497` (TWS paper)
- `IB_CLIENT_ID` default `7`
- `ORDER_DB_PATH` default `data/orders.db`

Smoke test:

```bash
python -m src.app health
```

## 2) In-Process API (Primary)

Module: `src/service_api.py`

Exports (also re-exported by `src/__init__.py`):

- Inputs: `HealthIn`, `ValidateIn`, `PlaceIn`, `WatchIn`
- Outputs: `HealthOut`, `ValidateOut`, `PlaceOut`, `WatchOut`
- Functions: `run_health`, `run_validate`, `run_place`, `run_watch`

### 2.1 Type Signatures

```python
run_health(payload: HealthIn, *, config: Config | None = None, logger: logging.Logger | None = None) -> HealthOut
run_validate(payload: ValidateIn) -> ValidateOut
run_place(payload: PlaceIn, *, config: Config | None = None, logger: logging.Logger | None = None) -> PlaceOut
run_watch(payload: WatchIn, *, config: Config | None = None, logger: logging.Logger | None = None, on_update: Callable[[dict], None] | None = None) -> WatchOut
```

### 2.2 Input Models

`HealthIn`
- `timeout: float = 5.0`

`ValidateIn`
- `order: OrderInput`
- `transmit: bool = False`

`PlaceIn`
- `order: OrderInput`
- `transmit: bool = False`
- `dry_run: bool = False`
- `timeout: float = 5.0`

`WatchIn`
- `order_id: int`
- `poll_interval: float = 1.0`
- `timeout: float = 5.0`
- `max_wait: float | None = None`

`OrderInput` accepted forms:
- `OrderRequest` object
- Python `dict`
- JSON `str`

### 2.3 Output Models

`HealthOut`
- `connected: bool`
- `next_valid_id: int | None`
- `error: str | None`

`ValidateOut`
- `valid: bool`
- `order_request: dict | None`
- `effective_order_ref: str | None`
- `errors: list[dict] | None`

`PlaceOut`
- `submitted: bool`
- `dry_run: bool`
- `order_id: int | None`
- `state: dict | None` (latest order state when submitted)
- `contract: dict | None` (constructed IB contract)
- `order_payload: dict | None` (constructed IB order)
- `order_request: dict | None` (only used in dry-run)
- `effective_order_ref: str | None` (only used in dry-run)
- `errors: list[dict] | None`
- `error: str | None`

`WatchOut`
- `order_id: int`
- `terminal: bool`
- `status: str | None`
- `updates: list[dict] | None`
- `error: str | None`

### 2.4 Order Request Schema

`OrderRequest` fields (from `src/domain/order_request.py`):

Required:
- `action`: `"BUY" | "SELL"`
- `symbol`: non-empty string (normalized uppercase)
- `order_type`: `"MKT" | "LMT"`
- `quantity`: positive number

Defaults:
- `sec_type`: `"STK"`
- `exchange`: `"SMART"`
- `currency`: `"USD"`
- `tif`: `"DAY"`
- `transmit`: `False`

Conditional:
- `limit_price` required for `LMT`
- `limit_price` must be omitted for `MKT`

Optional:
- `primary_exch`
- `client_tag`
- `order_ref`

Validation notes:
- Extra fields are rejected.
- String enums are uppercased.
- `client_tag` and `order_ref` must match when both provided.

### 2.5 In-Process Usage Examples

Validate:

```python
from src.service_api import ValidateIn, run_validate

out = run_validate(
    ValidateIn(order={
        "action": "BUY",
        "symbol": "AAPL",
        "order_type": "MKT",
        "quantity": 1
    })
)

if not out.valid:
    print(out.errors)
```

Place (dry run):

```python
from src.service_api import PlaceIn, run_place

out = run_place(
    PlaceIn(
        order={
            "action": "SELL",
            "symbol": "MSFT",
            "order_type": "LMT",
            "quantity": 2,
            "limit_price": 450.0
        },
        dry_run=True
    )
)

print(out.contract)
print(out.order_payload)
```

Place + watch:

```python
from src.service_api import PlaceIn, WatchIn, run_place, run_watch

place_out = run_place(
    PlaceIn(
        order={
            "action": "BUY",
            "symbol": "AAPL",
            "order_type": "MKT",
            "quantity": 1
        },
        transmit=False
    )
)

if place_out.submitted and place_out.order_id is not None:
    def on_update(event: dict) -> None:
        print(event)

    watch_out = run_watch(
        WatchIn(order_id=place_out.order_id, poll_interval=1.0, max_wait=120),
        on_update=on_update,
    )

    print(watch_out.terminal, watch_out.status, watch_out.error)
```

## 3) CLI API

Entry point: `python -m src.app`

All commands return JSON to stdout and non-zero exit code on failure.

### 3.1 Commands

Health:

```bash
python -m src.app health --timeout 5
```

Validate:

```bash
python -m src.app validate --json '{"action":"BUY","symbol":"AAPL","order_type":"MKT","quantity":1}'
python -m src.app validate --json-file examples/orders/mkt_buy_aapl.json
```

Place:

```bash
python -m src.app place --json-file examples/orders/mkt_buy_aapl.json
python -m src.app place --json-file examples/orders/mkt_buy_aapl.json --transmit
python -m src.app place --json-file examples/orders/mkt_buy_aapl.json --dry-run
```

Watch:

```bash
python -m src.app watch --order-id 123
python -m src.app watch --order-id 123 --poll-interval 0.5 --max-wait 120
```

Behavior:
- `watch` exits `0` when a terminal state is reached.
- Terminal states include: `FILLED`, `CANCELLED`, `ApiCancelled` variants, `INACTIVE`.

## 4) Persistence Model

Order state is persisted to SQLite at `ORDER_DB_PATH` (default `data/orders.db`).

Stored fields include:
- `order_id`
- `status`
- `filled`
- `avg_fill_price`
- `symbol`
- `action`
- `order_type`
- `quantity`
- `limit_price`
- `tif`
- `transmit`
- `order_ref`
- `last_error_code`
- `last_error`
- `perm_id`
- `last_update`
- `raw_state`

This allows `watch` and readbacks to work across process restarts.

## 5) Error Handling Contract

Validation errors:
- Returned as `errors: list[dict]` in `ValidateOut`/`PlaceOut`
- CLI returns JSON with `valid=false` or `submitted=false`

Connection errors (TWS unavailable/maintenance):
- `run_health`: `connected=false`, `error="could not connect to TWS"`
- `run_place`: `submitted=false`, `error="could not connect to TWS"`
- `run_watch`: `terminal=false`, `error="could not connect to TWS"`

Runtime exceptions:
- Returned as `errors=[{"type":"runtime","msg":"..."}]` where applicable.

## 6) Integration Pattern (Backend -> Library)

Recommended architecture when in same deployable:
- Backend imports `run_validate`, `run_place`, `run_watch` directly.
- Backend passes dict payloads from its own request layer.
- Backend handles retries/timeouts at orchestration layer.
- Backend uses `on_update` callback in `run_watch` to push events (logs, SSE, websockets, queue).

Minimal facade example:

```python
from src.service_api import PlaceIn, ValidateIn, WatchIn, run_place, run_validate, run_watch

def submit_order(order_payload: dict, transmit: bool = False):
    v = run_validate(ValidateIn(order=order_payload, transmit=transmit))
    if not v.valid:
        return {"ok": False, "errors": v.errors}

    p = run_place(PlaceIn(order=order_payload, transmit=transmit))
    if not p.submitted:
        return {"ok": False, "error": p.error, "errors": p.errors}

    return {"ok": True, "order_id": p.order_id, "state": p.state}
```

## 7) Operational Notes

- This project is for IBKR paper trading basic orders (`STK`, `MKT/LMT`) at current scope.
- `transmit=false` default is intentional safety.
- If TWS is under maintenance or not listening on the configured port, expect connection error `502`.
- For TWS paper account, default port is usually `7497`.

## 8) Stability and Compatibility

Public API surface for backend use:
- `src/service_api.py` function signatures and dataclasses
- `src/domain/order_request.py` schema

Internal implementation details (IB callbacks, store internals) may evolve.
