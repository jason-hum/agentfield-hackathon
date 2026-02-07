"""Top-level package for the IBKR paper trading scaffold."""

from .trade_api import TradeRequest, TradeResult, execute_trade

__all__ = [
    "TradeRequest",
    "TradeResult",
    "execute_trade",
]
