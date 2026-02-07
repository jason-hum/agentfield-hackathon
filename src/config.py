from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    ib_host: str
    ib_port: int
    ib_client_id: int
    order_db_path: str


def _load_dotenv() -> None:
    """Best-effort .env loader without hard dependency."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    load_dotenv()


def load_config() -> Config:
    _load_dotenv()

    ib_host = os.getenv("IB_HOST", "127.0.0.1")
    ib_port = int(os.getenv("IB_PORT", "7497"))
    ib_client_id = int(os.getenv("IB_CLIENT_ID", "7"))
    order_db_path = os.getenv("ORDER_DB_PATH", "data/orders.db")

    return Config(
        ib_host=ib_host,
        ib_port=ib_port,
        ib_client_id=ib_client_id,
        order_db_path=order_db_path,
    )
