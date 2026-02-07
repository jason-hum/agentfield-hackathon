from __future__ import annotations

import unittest

from src.domain import OrderRequest
from src.ibkr.builders import build_contract, build_order


class BuildersTestCase(unittest.TestCase):
    def test_build_contract_with_defaults(self) -> None:
        req = OrderRequest.model_validate(
            {
                "action": "BUY",
                "symbol": "AAPL",
                "order_type": "MKT",
                "quantity": 1,
            }
        )

        contract = build_contract(req)

        self.assertEqual(contract.symbol, "AAPL")
        self.assertEqual(contract.secType, "STK")
        self.assertEqual(contract.exchange, "SMART")
        self.assertEqual(contract.currency, "USD")
        self.assertEqual(contract.primaryExchange, "")

    def test_build_contract_with_primary_exchange(self) -> None:
        req = OrderRequest.model_validate(
            {
                "action": "BUY",
                "symbol": "AAPL",
                "order_type": "MKT",
                "quantity": 1,
                "primary_exch": "NASDAQ",
            }
        )

        contract = build_contract(req)

        self.assertEqual(contract.primaryExchange, "NASDAQ")

    def test_build_market_order(self) -> None:
        req = OrderRequest.model_validate(
            {
                "action": "BUY",
                "symbol": "AAPL",
                "order_type": "MKT",
                "quantity": 3,
                "transmit": False,
                "client_tag": "ref-001",
            }
        )

        order = build_order(req)

        self.assertEqual(order.action, "BUY")
        self.assertEqual(order.totalQuantity, 3)
        self.assertEqual(order.orderType, "MKT")
        self.assertEqual(order.tif, "DAY")
        self.assertFalse(order.transmit)
        self.assertEqual(order.orderRef, "ref-001")

    def test_build_limit_order(self) -> None:
        req = OrderRequest.model_validate(
            {
                "action": "SELL",
                "symbol": "MSFT",
                "order_type": "LMT",
                "quantity": 2,
                "limit_price": 450.25,
                "tif": "GTC",
                "transmit": True,
                "order_ref": "ref-002",
            }
        )

        order = build_order(req)

        self.assertEqual(order.action, "SELL")
        self.assertEqual(order.totalQuantity, 2)
        self.assertEqual(order.orderType, "LMT")
        self.assertEqual(order.lmtPrice, 450.25)
        self.assertEqual(order.tif, "GTC")
        self.assertTrue(order.transmit)
        self.assertEqual(order.orderRef, "ref-002")


if __name__ == "__main__":
    unittest.main()
