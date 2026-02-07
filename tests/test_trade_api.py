from __future__ import annotations

import unittest
from unittest.mock import patch

import src
from src.service_api import PlaceOut, ValidateOut, WatchOut
from src.trade_api import execute_trade


class TradeApiTestCase(unittest.TestCase):
    def test_top_level_exports_are_locked_down(self) -> None:
        self.assertEqual(sorted(src.__all__), ["TradeRequest", "TradeResult", "execute_trade"])

    @patch("src.trade_api.run_place")
    @patch("src.trade_api.run_validate")
    def test_execute_trade_validation_failure(self, mock_validate, mock_place) -> None:
        mock_validate.return_value = ValidateOut(valid=False, errors=[{"type": "value_error", "msg": "bad"}])

        out = execute_trade({"order": {"action": "BUY"}})

        self.assertFalse(out.ok)
        self.assertEqual(out.errors, [{"type": "value_error", "msg": "bad"}])
        mock_place.assert_not_called()

    @patch("src.trade_api.run_place")
    @patch("src.trade_api.run_validate")
    def test_execute_trade_dry_run(self, mock_validate, mock_place) -> None:
        mock_validate.return_value = ValidateOut(valid=True, order_request={"symbol": "AAPL"})
        mock_place.return_value = PlaceOut(
            submitted=False,
            dry_run=True,
            contract={"symbol": "AAPL"},
            order_payload={"order_type": "MKT"},
            order_request={"symbol": "AAPL"},
            effective_order_ref="ref-1",
        )

        out = execute_trade({"order": {"action": "BUY"}, "dry_run": True})

        self.assertTrue(out.ok)
        self.assertTrue(out.dry_run)
        self.assertEqual(out.contract, {"symbol": "AAPL"})
        self.assertEqual(out.order_payload, {"order_type": "MKT"})

    @patch("src.trade_api.run_watch")
    @patch("src.trade_api.run_place")
    @patch("src.trade_api.run_validate")
    def test_execute_trade_submit_without_wait(self, mock_validate, mock_place, mock_watch) -> None:
        mock_validate.return_value = ValidateOut(valid=True, order_request={"symbol": "AAPL"})
        mock_place.return_value = PlaceOut(
            submitted=True,
            order_id=42,
            state={"status": "SUBMITTED"},
            contract={"symbol": "AAPL"},
            order_payload={"order_type": "MKT"},
        )

        out = execute_trade({"order": {"action": "BUY"}, "wait_for_terminal": False})

        self.assertTrue(out.ok)
        self.assertTrue(out.submitted)
        self.assertEqual(out.order_id, 42)
        self.assertEqual(out.status, "SUBMITTED")
        mock_watch.assert_not_called()

    @patch("src.trade_api.run_watch")
    @patch("src.trade_api.run_place")
    @patch("src.trade_api.run_validate")
    def test_execute_trade_wait_for_terminal_success(self, mock_validate, mock_place, mock_watch) -> None:
        mock_validate.return_value = ValidateOut(valid=True, order_request={"symbol": "AAPL"})
        mock_place.return_value = PlaceOut(
            submitted=True,
            order_id=99,
            state={"status": "SUBMITTED"},
            contract={"symbol": "AAPL"},
            order_payload={"order_type": "MKT"},
        )
        mock_watch.return_value = WatchOut(
            order_id=99,
            terminal=True,
            status="FILLED",
            updates=[{"event": "order_update", "order_id": 99, "state": {"status": "FILLED"}}],
        )

        out = execute_trade({"order": {"action": "BUY"}, "wait_for_terminal": True})

        self.assertTrue(out.ok)
        self.assertEqual(out.status, "FILLED")
        self.assertTrue(out.terminal)
        self.assertEqual(out.state, {"status": "FILLED"})

    @patch("src.trade_api.run_watch")
    @patch("src.trade_api.run_place")
    @patch("src.trade_api.run_validate")
    def test_execute_trade_watch_error(self, mock_validate, mock_place, mock_watch) -> None:
        mock_validate.return_value = ValidateOut(valid=True, order_request={"symbol": "AAPL"})
        mock_place.return_value = PlaceOut(
            submitted=True,
            order_id=11,
            state={"status": "SUBMITTED"},
            contract={"symbol": "AAPL"},
            order_payload={"order_type": "MKT"},
        )
        mock_watch.return_value = WatchOut(order_id=11, terminal=False, status="SUBMITTED", error="max_wait_exceeded")

        out = execute_trade({"order": {"action": "BUY"}, "wait_for_terminal": True})

        self.assertFalse(out.ok)
        self.assertEqual(out.order_id, 11)
        self.assertEqual(out.error, "max_wait_exceeded")


if __name__ == "__main__":
    unittest.main()
