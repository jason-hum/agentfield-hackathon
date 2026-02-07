from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

TERMINAL_STATUSES = {"FILLED", "CANCELLED", "API CANCELLED", "APICANCELLED", "INACTIVE"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_status(status: str | None) -> str:
    if not status:
        return "UNKNOWN"
    return status.strip().upper()


def is_terminal_status(status: str | None) -> bool:
    return normalize_status(status) in TERMINAL_STATUSES


@dataclass(frozen=True)
class OrderStore:
    db_path: Path

    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        object.__setattr__(self, "db_path", path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL,
                    filled REAL NOT NULL DEFAULT 0,
                    avg_fill_price REAL,
                    last_update TEXT NOT NULL,
                    symbol TEXT,
                    action TEXT,
                    order_type TEXT,
                    quantity REAL,
                    limit_price REAL,
                    tif TEXT,
                    transmit INTEGER,
                    order_ref TEXT,
                    last_error_code INTEGER,
                    last_error TEXT,
                    perm_id INTEGER,
                    raw_state TEXT NOT NULL
                )
                """
            )

    def upsert(self, state: Dict[str, Any]) -> None:
        payload = dict(state)
        has_explicit_last_update = payload.get("last_update") is not None
        existing = self.get(int(payload["order_id"])) or {}
        merged = dict(existing)
        for key, value in payload.items():
            if value is None:
                continue
            merged[key] = value

        payload = merged
        payload.setdefault("status", "UNKNOWN")
        payload["status"] = normalize_status(payload.get("status"))
        payload.setdefault("filled", 0.0)
        payload.setdefault("avg_fill_price", None)
        if not has_explicit_last_update:
            payload["last_update"] = utc_now_iso()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    order_id, status, filled, avg_fill_price, last_update,
                    symbol, action, order_type, quantity, limit_price, tif,
                    transmit, order_ref, last_error_code, last_error, perm_id,
                    raw_state
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    status=excluded.status,
                    filled=excluded.filled,
                    avg_fill_price=excluded.avg_fill_price,
                    last_update=excluded.last_update,
                    symbol=excluded.symbol,
                    action=excluded.action,
                    order_type=excluded.order_type,
                    quantity=excluded.quantity,
                    limit_price=excluded.limit_price,
                    tif=excluded.tif,
                    transmit=excluded.transmit,
                    order_ref=excluded.order_ref,
                    last_error_code=excluded.last_error_code,
                    last_error=excluded.last_error,
                    perm_id=excluded.perm_id,
                    raw_state=excluded.raw_state
                """,
                (
                    int(payload["order_id"]),
                    payload["status"],
                    float(payload["filled"]),
                    payload.get("avg_fill_price"),
                    payload["last_update"],
                    payload.get("symbol"),
                    payload.get("action"),
                    payload.get("order_type"),
                    payload.get("quantity"),
                    payload.get("limit_price"),
                    payload.get("tif"),
                    int(payload["transmit"]) if payload.get("transmit") is not None else None,
                    payload.get("order_ref"),
                    payload.get("last_error_code"),
                    payload.get("last_error"),
                    payload.get("perm_id"),
                    json.dumps(payload, default=str),
                ),
            )

    def get(self, order_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT raw_state FROM orders WHERE order_id = ?", (order_id,)).fetchone()

        if not row:
            return None
        return json.loads(row[0])
