from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Any, Dict

from .logging import configure_logging
from .service_api import HealthIn, PlaceIn, ValidateIn, WatchIn, run_health, run_place, run_validate, run_watch


def _print_json(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, default=str) + "\n")


def _read_payload(args: argparse.Namespace) -> str:
    if args.json:
        return args.json
    if args.json_file:
        with open(args.json_file, "r", encoding="utf-8") as fh:
            return fh.read()
    raise ValueError("Either --json or --json-file is required")


def cmd_health(args: argparse.Namespace) -> int:
    logger = configure_logging()
    out = run_health(HealthIn(timeout=args.timeout), logger=logger)
    _print_json(asdict(out))
    return 0 if out.connected else 1


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        order_payload = _read_payload(args)
    except Exception as exc:
        _print_json({"valid": False, "errors": [{"type": "runtime", "msg": str(exc)}]})
        return 1

    out = run_validate(ValidateIn(order=order_payload, transmit=args.transmit))
    _print_json(asdict(out))
    return 0 if out.valid else 1


def cmd_place(args: argparse.Namespace) -> int:
    logger = configure_logging()

    try:
        order_payload = _read_payload(args)
    except Exception as exc:
        _print_json({"submitted": False, "errors": [{"type": "runtime", "msg": str(exc)}]})
        return 1

    out = run_place(
        PlaceIn(
            order=order_payload,
            transmit=args.transmit,
            dry_run=args.dry_run,
            timeout=args.timeout,
        ),
        logger=logger,
    )

    _print_json(asdict(out))
    return 0 if out.submitted or out.dry_run else 1


def cmd_watch(args: argparse.Namespace) -> int:
    logger = configure_logging()

    def on_update(event: Dict[str, Any]) -> None:
        _print_json(event)

    out = run_watch(
        WatchIn(
            order_id=args.order_id,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
            max_wait=args.max_wait,
        ),
        logger=logger,
        on_update=on_update,
    )

    if out.error:
        _print_json({"watching": False, "order_id": out.order_id, "error": out.error})
        return 130 if out.error == "interrupted" else 1

    return 0


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
