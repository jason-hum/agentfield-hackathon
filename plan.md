# IBKR Paper Trading (Python) — Phased Plan

Goal: place a basic order from structured input as early as possible, while keeping a clean path to expand.

Assumptions (adjust if needed)
- Instruments: US stocks only (`sec_type=STK`)
- Defaults: `exchange=SMART`, `currency=USD`, `tif=DAY`
- Safer default: `transmit=false` unless explicitly enabled

---

## Phase 0 — Project Shape (Scaffold)
Goal: runnable Python service/CLI with config + logging.

Deliverables
- Repo layout
  - `src/ibkr/` (IBKR adapter)
  - `src/domain/` (input schema + validation)
  - `src/app.py` (CLI entrypoint)
- `.env` / config for:
  - `IB_HOST` (usually `127.0.0.1`)
  - `IB_PORT` (paper trading port depends on TWS/Gateway config)
  - `IB_CLIENT_ID` (pick e.g. `7`)
- Structured logs to stdout (JSON or key/value)

---

## Phase 1 — Connect to TWS/IB Gateway and Get “Ready”
Goal: establish socket connection, start API message loop, obtain `nextValidId`.

Deliverables
- `IBApiClient` class that:
  - Connects to TWS/Gateway
  - Runs the reader loop (thread)
  - Waits until `nextValidId` arrives
- “Health check” command:
  - `python -m src.app health` prints: `connected=true`, `next_valid_id=<id>`

Why this matters
- IB order IDs come from `nextValidId` and must be incremented per order.

---

## Phase 2 — Minimal Order Input Schema (Pydantic)
Goal: one canonical request object → build `Contract` + `Order`.

Recommended input schema (basic only)

Required
- `action`: `"BUY" | "SELL"` (maps to `Order.Action`)
- `symbol`: `"AAPL"`
- `sec_type`: `"STK"` (support STK only first)
- `exchange`: `"SMART"` (default)
- `currency`: `"USD"` (default)
- `quantity`: number (maps to `Order.TotalQuantity`)
- `order_type`: `"MKT" | "LMT"`
- `tif`: `"DAY" | "GTC"` (default `"DAY"`)

Conditional
- `limit_price`: required if `order_type == "LMT"` (maps to `Order.LmtPrice`)

Optional but useful
- `primary_exch`: for ambiguity resolution
- `transmit`: default `False` (stage in TWS), or `True` to actually send
- `client_tag` / `order_ref`: for traceability (`Order.OrderRef`)

Deliverables
- `OrderRequest` Pydantic model with validations
- JSON examples you can paste into CLI

---

## Phase 3 — Contract Builder + Order Builder
Goal: deterministic mapping from `OrderRequest` → IB `Contract` + `Order`.

Deliverables
- `build_contract(req)` that fills:
  - `Contract.Symbol`, `SecType`, `Exchange`, `Currency`, optional `PrimaryExch`
- `build_order(req)` that fills:
  - `Order.Action`, `TotalQuantity`, `OrderType`, optional `LmtPrice`, `Tif`, `Transmit`
- Unit tests for pure mapping logic (no TWS needed)

---

## Phase 4 — “Submit Order” Workflow + Status Tracking
Goal: place an order and observe lifecycle callbacks.

Deliverables
- `submit_order(req) -> order_id`
  - Ensure connected + have next order id
  - `placeOrder(order_id, contract, order)`
  - Increment internal order id counter
- Callback handlers to track:
  - `openOrder`
  - `orderStatus`
  - `error`
- Simple in-memory store:
  - `orders[order_id] = {status, filled, avg_fill_price, last_update}`

CLI commands
- `place --json '{...}'`
- `watch --order-id 123` (prints updates)

---

## Phase 5 — Safety Rails (Paper Trading Still Benefits)
Goal: prevent dumb mistakes and make behavior explicit.

Deliverables
- Hard validation rules
  - `quantity > 0`
  - If `LMT`, `limit_price > 0`
  - Optional: enforce allowed symbols/whitelist
- Two-step sending
  - Default `transmit=false` (creates order in TWS but doesn’t transmit)
  - `--transmit` flag to send
- “Dry run” mode prints constructed `Contract`/`Order` without placing

---

## Immediate Next Steps
1. Set up TWS/IB Gateway paper trading, confirm API enabled, port/clientId chosen.
2. Build Phase 1 (connect + `nextValidId` + `health` command).
3. Implement `OrderRequest` + builders.
