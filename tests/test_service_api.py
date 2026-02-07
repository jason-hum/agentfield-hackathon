from __future__ import annotations

import unittest

from src.service_api import PlaceIn, ValidateIn, run_place, run_validate


class ServiceApiTestCase(unittest.TestCase):
    def test_run_validate_success(self) -> None:
        out = run_validate(
            ValidateIn(
                order={
                    "action": "BUY",
                    "symbol": "AAPL",
                    "order_type": "MKT",
                    "quantity": 1,
                }
            )
        )

        self.assertTrue(out.valid)
        self.assertIsNotNone(out.order_request)
        assert out.order_request is not None
        self.assertEqual(out.order_request["symbol"], "AAPL")

    def test_run_validate_failure(self) -> None:
        out = run_validate(
            ValidateIn(
                order={
                    "action": "BUY",
                    "symbol": "AAPL",
                    "order_type": "LMT",
                    "quantity": 1,
                }
            )
        )

        self.assertFalse(out.valid)
        self.assertIsNotNone(out.errors)

    def test_run_place_dry_run(self) -> None:
        out = run_place(
            PlaceIn(
                order={
                    "action": "SELL",
                    "symbol": "MSFT",
                    "order_type": "LMT",
                    "quantity": 2,
                    "limit_price": 450,
                },
                dry_run=True,
            )
        )

        self.assertFalse(out.submitted)
        self.assertTrue(out.dry_run)
        self.assertIsNone(out.order_id)
        self.assertEqual(out.contract["symbol"], "MSFT")
        self.assertEqual(out.order_payload["order_type"], "LMT")
        self.assertEqual(out.order_payload["limit_price"], 450)


if __name__ == "__main__":
    unittest.main()
