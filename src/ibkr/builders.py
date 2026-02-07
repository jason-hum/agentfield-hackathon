from __future__ import annotations

from ibapi.contract import Contract
from ibapi.order import Order

from ..domain import OrderRequest


def build_contract(req: OrderRequest) -> Contract:
    contract = Contract()
    contract.symbol = req.symbol
    contract.secType = req.sec_type
    contract.exchange = req.exchange
    contract.currency = req.currency

    if req.primary_exch:
        contract.primaryExchange = req.primary_exch

    return contract


def build_order(req: OrderRequest) -> Order:
    order = Order()
    order.action = req.action
    order.totalQuantity = req.quantity
    order.orderType = req.order_type
    order.tif = req.tif
    order.transmit = req.transmit

    if req.order_type == "LMT" and req.limit_price is not None:
        order.lmtPrice = req.limit_price

    if req.effective_order_ref:
        order.orderRef = req.effective_order_ref

    return order
