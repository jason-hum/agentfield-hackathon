from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.ibkr.order_store import OrderStore, is_terminal_status


class OrderStoreTestCase(unittest.TestCase):
    def test_upsert_and_get(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OrderStore(str(Path(tmpdir) / "orders.db"))
            store.upsert(
                {
                    "order_id": 101,
                    "status": "SUBMITTED",
                    "symbol": "AAPL",
                    "action": "BUY",
                    "order_type": "MKT",
                    "quantity": 2,
                    "transmit": False,
                    "filled": 0,
                }
            )

            state = store.get(101)
            self.assertIsNotNone(state)
            assert state is not None
            self.assertEqual(state["order_id"], 101)
            self.assertEqual(state["status"], "SUBMITTED")
            self.assertEqual(state["symbol"], "AAPL")

    def test_upsert_preserves_existing_fields_on_partial_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OrderStore(str(Path(tmpdir) / "orders.db"))
            store.upsert(
                {
                    "order_id": 202,
                    "status": "SUBMITTED",
                    "symbol": "MSFT",
                    "action": "SELL",
                    "order_type": "LMT",
                    "quantity": 1,
                    "limit_price": 400.0,
                    "filled": 0,
                }
            )
            store.upsert(
                {
                    "order_id": 202,
                    "status": "FILLED",
                    "filled": 1,
                    "avg_fill_price": 401.5,
                }
            )

            state = store.get(202)
            self.assertIsNotNone(state)
            assert state is not None
            self.assertEqual(state["status"], "FILLED")
            self.assertEqual(state["filled"], 1.0)
            self.assertEqual(state["avg_fill_price"], 401.5)
            self.assertEqual(state["symbol"], "MSFT")
            self.assertEqual(state["limit_price"], 400.0)

    def test_terminal_status_detection(self) -> None:
        self.assertTrue(is_terminal_status("filled"))
        self.assertTrue(is_terminal_status("CANCELLED"))
        self.assertFalse(is_terminal_status("Submitted"))


if __name__ == "__main__":
    unittest.main()
