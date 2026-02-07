from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, Tuple

from pydantic import ValidationError

from .config import load_config
from .domain import OrderRequest
from .ibkr import IBApiClient, OrderStore, build_contract, build_order, is_terminal_status
from .logging import configure_logging


def _print_json(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, default=str) + "\n")


def _read_payload(args: argparse.Namespace) -> str:
    if args.json:
        return args.json
    if args.json_file:
        with open(args.json_file, "r", encoding="utf-8") as fh:
            return fh.read()
    raise ValueError("Either --json or --json-file is required")


def _parse_order_request(args: argparse.Namespace) -> OrderRequest:
    payload = _read_payload(args)
    req = OrderRequest.from_json(payload)
    if getattr(args, "transmit", False):
        req = req.model_copy(update={"transmit": True})
    return req


def _contract_to_dict(contract: Any) -> Dict[str, Any]:
    return {
        "symbol": contract.symbol,
        "sec_type": contract.secType,
        "exchange": contract.exchange,
        "currency": contract.currency,
        "primary_exch": contract.primaryExchange or None,
    }


def _order_to_dict(order: Any) -> Dict[str, Any]:
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


def cmd_health(args: argparse.Namespace) -> int:
    logger = configure_logging()
    config = load_config()

    client = IBApiClient(logger=logger)
    ok = client.connect_and_wait(
        config.ib_host,
        config.ib_port,
        config.ib_client_id,
        timeout=args.timeout,
    )

    if not ok:
        _print_json({"connected": False, "next_valid_id": None})
        return 1

    _print_json({"connected": True, "next_valid_id": client.next_valid_id})
    client.disconnect_and_wait()
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        req = _parse_order_request(args)
    except ValidationError as exc:
        _print_json({"valid": False, "errors": exc.errors(include_url=False, include_context=False)})
        return 1
    except json.JSONDecodeError as exc:
        _print_json({"valid": False, "errors": [{"type": "json_decode", "msg": str(exc)}]})
        return 1
    except Exception as exc:
        _print_json({"valid": False, "errors": [{"type": "runtime", "msg": str(exc)}]})
        return 1

    _print_json(
        {
            "valid": True,
            "order_request": req.model_dump(),
            "effective_order_ref": req.effective_order_ref,
        }
    )
    return 0


def cmd_place(args: argparse.Namespace) -> int:
    logger = configure_logging()
    config = load_config()

    try:
        req = _parse_order_request(args)
    except ValidationError as exc:
        _print_json({"submitted": False, "errors": exc.errors(include_url=False, include_context=False)})
        return 1
    except Exception as exc:
        _print_json({"submitted": False, "errors": [{"type": "runtime", "msg": str(exc)}]})
        return 1

    contract = build_contract(req)
    order = build_order(req)

    if args.dry_run:
        _print_json(
            {
                "submitted": False,
                "dry_run": True,
                "order_request": req.model_dump(),
                "contract": _contract_to_dict(contract),
                "order": _order_to_dict(order),
            }
        )
        return 0

    store = OrderStore(config.order_db_path)
    client = IBApiClient(logger=logger, order_store=store)
    ok = client.connect_and_wait(
        config.ib_host,
        config.ib_port,
        config.ib_client_id,
        timeout=args.timeout,
    )
    if not ok:
        _print_json({"submitted": False, "error": "could not connect to TWS"})
        return 1

    try:
        order_id = client.submit_order(req)
        state = client.get_order_state(order_id) or store.get(order_id)
        _print_json({"submitted": True, "order_id": order_id, "state": state})
        return 0
    finally:
        client.disconnect_and_wait()


def cmd_watch(args: argparse.Namespace) -> int:
    logger = configure_logging()
    config = load_config()
    store = OrderStore(config.order_db_path)

    order_id = args.order_id
    last_signature: Tuple[Any, Any, Any, Any] | None = None
    start_time = time.monotonic()

    persisted = store.get(order_id)
    if persisted:
        last_signature = _state_signature(persisted)
        _print_json({"event": "order_update", "order_id": order_id, "state": persisted})
        if is_terminal_status(persisted.get("status")):
            return 0

    client = IBApiClient(logger=logger, order_store=store)
    ok = client.connect_and_wait(
        config.ib_host,
        config.ib_port,
        config.ib_client_id,
        timeout=args.timeout,
    )
    if not ok:
        _print_json({"watching": False, "error": "could not connect to TWS"})
        return 1

    client.request_open_orders()
    last_seq = 0

    try:
        while True:
            live_state = client.wait_for_order_update(order_id, last_seq=last_seq, timeout=args.poll_interval)
            if live_state:
                last_seq = int(live_state.get("_seq", last_seq))

            state = store.get(order_id) or live_state
            if state:
                signature = _state_signature(state)
                if signature != last_signature:
                    last_signature = signature
                    _print_json({"event": "order_update", "order_id": order_id, "state": state})

                if is_terminal_status(state.get("status")):
                    return 0

            if args.max_wait is not None and (time.monotonic() - start_time) >= args.max_wait:
                _print_json({"watching": False, "order_id": order_id, "error": "max_wait_exceeded"})
                return 1
    except KeyboardInterrupt:
        _print_json({"watching": False, "order_id": order_id, "error": "interrupted"})
        return 130
    finally:
        client.disconnect_and_wait()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ibkr-cli")
    sub = parser.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health", help="Check IB connection and nextValidId")
    health.add_argument("--timeout", type=float, default=5.0, help="Seconds to wait for nextValidId")
    health.set_defaults(func=cmd_health)

    validate = sub.add_parser("validate", help="Validate structured order JSON input")
    validate_input = validate.add_mutually_exclusive_group(required=True)
    validate_input.add_argument("--json", type=str, help="Inline JSON payload")
    validate_input.add_argument("--json-file", type=str, help="Path to JSON payload file")
    validate.add_argument("--transmit", action="store_true", help="Override payload and set transmit=true")
    validate.set_defaults(func=cmd_validate)

    place = sub.add_parser("place", help="Submit a basic order")
    place_input = place.add_mutually_exclusive_group(required=True)
    place_input.add_argument("--json", type=str, help="Inline JSON payload")
    place_input.add_argument("--json-file", type=str, help="Path to JSON payload file")
    place.add_argument("--transmit", action="store_true", help="Override payload and set transmit=true")
    place.add_argument("--dry-run", action="store_true", help="Build contract/order but do not place")
    place.add_argument("--timeout", type=float, default=5.0, help="Seconds to wait for nextValidId")
    place.set_defaults(func=cmd_place)

    watch = sub.add_parser("watch", help="Watch an order until Filled/Cancelled")
    watch.add_argument("--order-id", type=int, required=True, help="IB order id to watch")
    watch.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between update checks")
    watch.add_argument("--timeout", type=float, default=5.0, help="Seconds to wait for connection readiness")
    watch.add_argument("--max-wait", type=float, default=None, help="Optional max seconds before giving up")
    watch.set_defaults(func=cmd_watch)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
