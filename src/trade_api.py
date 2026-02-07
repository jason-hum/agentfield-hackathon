from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict

from .config import Config
from .service_api import (
    OrderInput,
    PlaceIn,
    ValidateIn,
    WatchIn,
    WatchUpdateHandler,
    run_place,
    run_validate,
    run_watch,
)


@dataclass(frozen=True)
class TradeRequest:
    order: OrderInput
    transmit: bool = False
    dry_run: bool = False
    wait_for_terminal: bool = False
    timeout: float = 5.0
    poll_interval: float = 1.0
    max_wait: float | None = None


@dataclass(frozen=True)
class TradeResult:
    ok: bool
    submitted: bool = False
    dry_run: bool = False
    order_id: int | None = None
    status: str | None = None
    terminal: bool | None = None
    state: Dict[str, Any] | None = None
    updates: list[Dict[str, Any]] | None = None
    contract: Dict[str, Any] | None = None
    order_payload: Dict[str, Any] | None = None
    order_request: Dict[str, Any] | None = None
    effective_order_ref: str | None = None
    errors: list[Dict[str, Any]] | None = None
    error: str | None = None


TradeInput = TradeRequest | Dict[str, Any]


def _coerce_trade_request(payload: TradeInput) -> TradeRequest:
    if isinstance(payload, TradeRequest):
        return payload
    if isinstance(payload, dict):
        return TradeRequest(**payload)
    raise TypeError("payload must be TradeRequest or dict")


def execute_trade(
    payload: TradeInput,
    *,
    config: Config | None = None,
    logger: logging.Logger | None = None,
    on_update: WatchUpdateHandler | None = None,
) -> TradeResult:
    """Single-entry trade API: validate -> place -> optional watch."""
    try:
        request = _coerce_trade_request(payload)

        validation = run_validate(ValidateIn(order=request.order, transmit=request.transmit))
        if not validation.valid:
            return TradeResult(ok=False, errors=validation.errors)

        placement = run_place(
            PlaceIn(
                order=request.order,
                transmit=request.transmit,
                dry_run=request.dry_run,
                timeout=request.timeout,
            ),
            config=config,
            logger=logger,
        )

        if placement.dry_run:
            return TradeResult(
                ok=True,
                submitted=False,
                dry_run=True,
                contract=placement.contract,
                order_payload=placement.order_payload,
                order_request=placement.order_request,
                effective_order_ref=placement.effective_order_ref,
            )

        if not placement.submitted:
            return TradeResult(
                ok=False,
                submitted=False,
                error=placement.error,
                errors=placement.errors,
                contract=placement.contract,
                order_payload=placement.order_payload,
            )

        if not request.wait_for_terminal:
            status = (placement.state or {}).get("status") if placement.state else None
            return TradeResult(
                ok=True,
                submitted=True,
                order_id=placement.order_id,
                status=status,
                terminal=False,
                state=placement.state,
                contract=placement.contract,
                order_payload=placement.order_payload,
            )

        if placement.order_id is None:
            return TradeResult(ok=False, submitted=False, error="order_id missing after submission")

        watch = run_watch(
            WatchIn(
                order_id=placement.order_id,
                poll_interval=request.poll_interval,
                timeout=request.timeout,
                max_wait=request.max_wait,
            ),
            config=config,
            logger=logger,
            on_update=on_update,
        )

        if watch.error:
            return TradeResult(
                ok=False,
                submitted=True,
                order_id=placement.order_id,
                status=watch.status,
                terminal=watch.terminal,
                state=placement.state,
                updates=watch.updates,
                error=watch.error,
                contract=placement.contract,
                order_payload=placement.order_payload,
            )

        final_state = (watch.updates or [{}])[-1].get("state") if (watch.updates or None) else placement.state

        return TradeResult(
            ok=True,
            submitted=True,
            order_id=placement.order_id,
            status=watch.status,
            terminal=watch.terminal,
            state=final_state,
            updates=watch.updates,
            contract=placement.contract,
            order_payload=placement.order_payload,
        )
    except Exception as exc:
        return TradeResult(ok=False, errors=[{"type": "runtime", "msg": str(exc)}], error=str(exc))
