from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Tuple

from pydantic import ValidationError

from .config import Config, load_config
from .domain import OrderRequest
from .ibkr import IBApiClient, OrderStore, build_contract, build_order, is_terminal_status

OrderInput = OrderRequest | Mapping[str, Any] | str
WatchUpdateHandler = Callable[[Dict[str, Any]], None]


@dataclass(frozen=True)
class HealthIn:
    timeout: float = 5.0


@dataclass(frozen=True)
class HealthOut:
    connected: bool
    next_valid_id: int | None
    error: str | None = None


@dataclass(frozen=True)
class ValidateIn:
    order: OrderInput
    transmit: bool = False


@dataclass(frozen=True)
class ValidateOut:
    valid: bool
    order_request: Dict[str, Any] | None = None
    effective_order_ref: str | None = None
    errors: list[Dict[str, Any]] | None = None


@dataclass(frozen=True)
class PlaceIn:
    order: OrderInput
    transmit: bool = False
    dry_run: bool = False
    timeout: float = 5.0


@dataclass(frozen=True)
class PlaceOut:
    submitted: bool
    dry_run: bool = False
    order_id: int | None = None
    state: Dict[str, Any] | None = None
    contract: Dict[str, Any] | None = None
    order_payload: Dict[str, Any] | None = None
    order_request: Dict[str, Any] | None = None
    effective_order_ref: str | None = None
    errors: list[Dict[str, Any]] | None = None
    error: str | None = None


@dataclass(frozen=True)
class WatchIn:
    order_id: int
    poll_interval: float = 1.0
    timeout: float = 5.0
    max_wait: float | None = None


@dataclass(frozen=True)
class WatchOut:
    order_id: int
    terminal: bool
    status: str | None = None
    updates: list[Dict[str, Any]] | None = None
    error: str | None = None


def _resolve_config(config: Config | None) -> Config:
    return config or load_config()


def _resolve_logger(logger: logging.Logger | None) -> logging.Logger:
    return logger or logging.getLogger(__name__)


def _coerce_order_request(order_input: OrderInput, transmit: bool = False) -> OrderRequest:
    if isinstance(order_input, OrderRequest):
        req = order_input
    elif isinstance(order_input, str):
        req = OrderRequest.from_json(order_input)
    elif isinstance(order_input, Mapping):
        req = OrderRequest.model_validate(dict(order_input))
    else:
        raise TypeError("order input must be OrderRequest, mapping, or JSON string")

    if transmit:
        req = req.model_copy(update={"transmit": True})

    return req


def _to_contract_dict(contract: Any) -> Dict[str, Any]:
    return {
        "symbol": contract.symbol,
        "sec_type": contract.secType,
        "exchange": contract.exchange,
        "currency": contract.currency,
        "primary_exch": contract.primaryExchange or None,
    }


def _to_order_dict(order: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "action": order.action,
        "quantity": order.totalQuantity,
        "order_type": order.orderType,
        "tif": order.tif,
        "transmit": order.transmit,
        "order_ref": order.orderRef or None,
    }
    if order.orderType == "LMT":
        payload["limit_price"] = order.lmtPrice
    return payload


def _state_signature(state: Dict[str, Any]) -> Tuple[Any, Any, Any, Any]:
    return (
        state.get("last_update"),
        state.get("status"),
        state.get("filled"),
        state.get("avg_fill_price"),
    )


def _validation_errors(exc: ValidationError) -> list[Dict[str, Any]]:
    return list(exc.errors(include_url=False, include_context=False))


def run_health(payload: HealthIn, *, config: Config | None = None, logger: logging.Logger | None = None) -> HealthOut:
    cfg = _resolve_config(config)
    log = _resolve_logger(logger)

    client = IBApiClient(logger=log)
    ok = client.connect_and_wait(
        cfg.ib_host,
        cfg.ib_port,
        cfg.ib_client_id,
        timeout=payload.timeout,
    )
    if not ok:
        return HealthOut(connected=False, next_valid_id=None, error="could not connect to TWS")

    try:
        return HealthOut(connected=True, next_valid_id=client.next_valid_id)
    finally:
        client.disconnect_and_wait()


def run_validate(payload: ValidateIn) -> ValidateOut:
    try:
        req = _coerce_order_request(payload.order, transmit=payload.transmit)
    except ValidationError as exc:
        return ValidateOut(valid=False, errors=_validation_errors(exc))
    except Exception as exc:
        return ValidateOut(valid=False, errors=[{"type": "runtime", "msg": str(exc)}])

    return ValidateOut(
        valid=True,
        order_request=req.model_dump(),
        effective_order_ref=req.effective_order_ref,
    )


def run_place(payload: PlaceIn, *, config: Config | None = None, logger: logging.Logger | None = None) -> PlaceOut:
    cfg = _resolve_config(config)
    log = _resolve_logger(logger)

    try:
        req = _coerce_order_request(payload.order, transmit=payload.transmit)
    except ValidationError as exc:
        return PlaceOut(submitted=False, errors=_validation_errors(exc))
    except Exception as exc:
        return PlaceOut(submitted=False, errors=[{"type": "runtime", "msg": str(exc)}])

    contract = build_contract(req)
    order = build_order(req)
    contract_payload = _to_contract_dict(contract)
    order_payload = _to_order_dict(order)

    if payload.dry_run:
        return PlaceOut(
            submitted=False,
            dry_run=True,
            contract=contract_payload,
            order_payload=order_payload,
            order_request=req.model_dump(),
            effective_order_ref=req.effective_order_ref,
        )

    store = OrderStore(cfg.order_db_path)
    client = IBApiClient(logger=log, order_store=store)

    ok = client.connect_and_wait(
        cfg.ib_host,
        cfg.ib_port,
        cfg.ib_client_id,
        timeout=payload.timeout,
    )
    if not ok:
        return PlaceOut(submitted=False, error="could not connect to TWS")

    try:
        order_id = client.submit_order(req)
        state = client.get_order_state(order_id) or store.get(order_id)
        return PlaceOut(
            submitted=True,
            order_id=order_id,
            state=state,
            contract=contract_payload,
            order_payload=order_payload,
        )
    except Exception as exc:
        return PlaceOut(submitted=False, error=str(exc), contract=contract_payload, order_payload=order_payload)
    finally:
        client.disconnect_and_wait()


def run_watch(
    payload: WatchIn,
    *,
    config: Config | None = None,
    logger: logging.Logger | None = None,
    on_update: WatchUpdateHandler | None = None,
) -> WatchOut:
    cfg = _resolve_config(config)
    log = _resolve_logger(logger)
    store = OrderStore(cfg.order_db_path)

    updates: list[Dict[str, Any]] = []
    last_signature: Tuple[Any, Any, Any, Any] | None = None
    start_time = time.monotonic()
    state: Dict[str, Any] | None = None

    def emit(state: Dict[str, Any]) -> None:
        event = {"event": "order_update", "order_id": payload.order_id, "state": state}
        updates.append(event)
        if on_update:
            on_update(event)

    persisted = store.get(payload.order_id)
    if persisted:
        last_signature = _state_signature(persisted)
        emit(persisted)
        if is_terminal_status(persisted.get("status")):
            return WatchOut(
                order_id=payload.order_id,
                terminal=True,
                status=persisted.get("status"),
                updates=updates,
            )

    client = IBApiClient(logger=log, order_store=store)
    ok = client.connect_and_wait(
        cfg.ib_host,
        cfg.ib_port,
        cfg.ib_client_id,
        timeout=payload.timeout,
    )
    if not ok:
        return WatchOut(
            order_id=payload.order_id,
            terminal=False,
            status=(persisted or {}).get("status") if persisted else None,
            updates=updates,
            error="could not connect to TWS",
        )

    client.request_open_orders()
    last_seq = 0

    try:
        while True:
            live_state = client.wait_for_order_update(payload.order_id, last_seq=last_seq, timeout=payload.poll_interval)
            if live_state:
                last_seq = int(live_state.get("_seq", last_seq))

            state = store.get(payload.order_id) or live_state
            if state:
                signature = _state_signature(state)
                if signature != last_signature:
                    last_signature = signature
                    emit(state)

                if is_terminal_status(state.get("status")):
                    return WatchOut(
                        order_id=payload.order_id,
                        terminal=True,
                        status=state.get("status"),
                        updates=updates,
                    )

            if payload.max_wait is not None and (time.monotonic() - start_time) >= payload.max_wait:
                return WatchOut(
                    order_id=payload.order_id,
                    terminal=False,
                    status=(state or {}).get("status") if state else None,
                    updates=updates,
                    error="max_wait_exceeded",
                )
    except KeyboardInterrupt:
        return WatchOut(
            order_id=payload.order_id,
            terminal=False,
            status=None,
            updates=updates,
            error="interrupted",
        )
    finally:
        client.disconnect_and_wait()
