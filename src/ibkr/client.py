from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.wrapper import EWrapper

from ..domain import OrderRequest
from .builders import build_contract, build_order
from .order_store import OrderStore, normalize_status, utc_now_iso


class IBApiClient(EWrapper, EClient):
    def __init__(self, logger: Optional[logging.Logger] = None, order_store: OrderStore | None = None) -> None:
        EWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)
        self._logger = logger or logging.getLogger(__name__)
        self._thread: Optional[threading.Thread] = None
        self._next_valid_id_event = threading.Event()
        self._connected_event = threading.Event()
        self._orders_cv = threading.Condition()
        self._sequence = 0

        self.next_valid_id: Optional[int] = None
        self.orders: Dict[int, Dict[str, Any]] = {}
        self.order_store = order_store

    def connect_and_wait(self, host: str, port: int, client_id: int, timeout: float = 5.0) -> bool:
        self._logger.info("connecting", extra={"host": host, "port": port, "client_id": client_id})
        self._next_valid_id_event.clear()
        ok = self.connect(host, port, client_id)
        if not ok:
            self._logger.error("connect_failed")
            return False

        self._thread = threading.Thread(target=self.run, name="ibkr-reader", daemon=True)
        self._thread.start()

        if not self._next_valid_id_event.wait(timeout=timeout):
            self._logger.error("next_valid_id_timeout", extra={"timeout": timeout})
            self.disconnect_and_wait()
            return False

        return True

    def disconnect_and_wait(self, timeout: float = 2.0) -> None:
        try:
            self.disconnect()
        finally:
            if self._thread:
                self._thread.join(timeout=timeout)

    def submit_order(self, req: OrderRequest) -> int:
        if self.next_valid_id is None:
            raise RuntimeError("next_valid_id is not available")

        order_id = self.next_valid_id
        self.next_valid_id += 1

        contract = build_contract(req)
        order = build_order(req)

        self._record_order_update(
            order_id,
            {
                "status": "SUBMITTING",
                "symbol": req.symbol,
                "action": req.action,
                "order_type": req.order_type,
                "quantity": req.quantity,
                "limit_price": req.limit_price,
                "tif": req.tif,
                "transmit": req.transmit,
                "order_ref": req.effective_order_ref,
                "filled": 0.0,
                "avg_fill_price": None,
            },
        )

        try:
            self.placeOrder(order_id, contract, order)
            self._record_order_update(order_id, {"status": "SUBMITTED"})
        except Exception as exc:
            self._record_order_update(order_id, {"status": "ERROR", "last_error": str(exc)})
            raise

        self._logger.info(
            "order_submitted",
            extra={"order_id": order_id, "symbol": req.symbol, "action": req.action, "transmit": req.transmit},
        )
        return order_id

    def get_order_state(self, order_id: int) -> Dict[str, Any] | None:
        with self._orders_cv:
            state = self.orders.get(order_id)
            if state:
                return dict(state)

        if not self.order_store:
            return None

        persisted = self.order_store.get(order_id)
        if not persisted:
            return None
        persisted.setdefault("_seq", 0)
        return persisted

    def wait_for_order_update(self, order_id: int, last_seq: int, timeout: float = 1.0) -> Dict[str, Any] | None:
        with self._orders_cv:
            state = self.orders.get(order_id)
            if state and int(state.get("_seq", 0)) > last_seq:
                return dict(state)

            self._orders_cv.wait(timeout=timeout)
            state = self.orders.get(order_id)
            if state and int(state.get("_seq", 0)) > last_seq:
                return dict(state)

        return None

    def request_open_orders(self) -> None:
        self.reqOpenOrders()
        self.reqAllOpenOrders()

    def _record_order_update(self, order_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._orders_cv:
            base = self.orders.get(order_id)
            if base is None and self.order_store:
                base = self.order_store.get(order_id)

            state: Dict[str, Any] = dict(base or {"order_id": order_id, "status": "UNKNOWN"})
            for key, value in updates.items():
                if value is None:
                    continue
                state[key] = value

            state["status"] = normalize_status(state.get("status"))
            state["last_update"] = utc_now_iso()
            self._sequence += 1
            state["_seq"] = self._sequence

            self.orders[order_id] = state

            if self.order_store:
                self.order_store.upsert({k: v for k, v in state.items() if k != "_seq"})

            self._orders_cv.notify_all()
            return dict(state)

    # --- IB callbacks ---
    def nextValidId(self, orderId: int) -> None:  # noqa: N802
        self.next_valid_id = orderId
        self._logger.info("next_valid_id", extra={"order_id": orderId})
        self._next_valid_id_event.set()

    def connectAck(self) -> None:  # noqa: N802
        self._connected_event.set()
        self._logger.info("connect_ack")

    def openOrder(self, orderId: int, contract: Contract, order: Order, orderState: Any) -> None:  # noqa: N802
        limit_price = None
        if getattr(order, "orderType", "") == "LMT":
            limit_price = getattr(order, "lmtPrice", None)

        state = self._record_order_update(
            orderId,
            {
                "status": getattr(orderState, "status", None) or "OPEN",
                "symbol": getattr(contract, "symbol", None),
                "action": getattr(order, "action", None),
                "order_type": getattr(order, "orderType", None),
                "quantity": getattr(order, "totalQuantity", None),
                "limit_price": limit_price,
                "tif": getattr(order, "tif", None),
                "transmit": getattr(order, "transmit", None),
                "order_ref": getattr(order, "orderRef", None),
                "perm_id": getattr(order, "permId", None),
            },
        )
        self._logger.info(
            "open_order",
            extra={"order_id": orderId, "status": state.get("status"), "symbol": state.get("symbol")},
        )

    def orderStatus(  # noqa: N802
        self,
        orderId: int,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ) -> None:
        state = self._record_order_update(
            orderId,
            {
                "status": status,
                "filled": filled,
                "remaining": remaining,
                "avg_fill_price": avgFillPrice,
                "perm_id": permId,
                "last_fill_price": lastFillPrice,
            },
        )
        self._logger.info(
            "order_status",
            extra={
                "order_id": orderId,
                "status": state.get("status"),
                "filled": state.get("filled"),
                "avg_fill_price": state.get("avg_fill_price"),
            },
        )

    def error(self, reqId: int, *args: Any) -> None:  # noqa: N802
        error_time: int | None = None
        error_code: int = -1
        error_string: str = ""
        advanced_reject: str = ""

        # Handle both IB API callback shapes:
        # 1) (reqId, errorCode, errorString, advancedOrderRejectJson?)
        # 2) (reqId, errorTime, errorCode, errorString, advancedOrderRejectJson?)
        if len(args) == 2:
            error_code = int(args[0])
            error_string = str(args[1])
        elif len(args) == 3:
            if isinstance(args[1], int):
                error_time = int(args[0])
                error_code = int(args[1])
                error_string = str(args[2])
            else:
                error_code = int(args[0])
                error_string = str(args[1])
                advanced_reject = str(args[2] or "")
        elif len(args) >= 4:
            error_time = int(args[0])
            error_code = int(args[1])
            error_string = str(args[2])
            advanced_reject = str(args[3] or "")

        payload = {
            "req_id": reqId,
            "error_code": error_code,
            "error": error_string,
        }
        if error_time is not None:
            payload["error_time"] = error_time
        if advanced_reject:
            payload["advanced_reject"] = advanced_reject

        self._logger.error("ib_error", extra=payload)

        if reqId > 0:
            self._record_order_update(
                reqId,
                {
                    "last_error_code": error_code,
                    "last_error": error_string,
                },
            )
