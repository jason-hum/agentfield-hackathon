"""Top-level package for the IBKR paper trading scaffold."""

from .domain import OrderRequest
from .service_api import (
    HealthIn,
    HealthOut,
    PlaceIn,
    PlaceOut,
    ValidateIn,
    ValidateOut,
    WatchIn,
    WatchOut,
    run_health,
    run_place,
    run_validate,
    run_watch,
)

__all__ = [
    "HealthIn",
    "HealthOut",
    "OrderRequest",
    "PlaceIn",
    "PlaceOut",
    "ValidateIn",
    "ValidateOut",
    "WatchIn",
    "WatchOut",
    "run_health",
    "run_place",
    "run_validate",
    "run_watch",
]
