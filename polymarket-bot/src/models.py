"""
Domain models / dataclasses for Polymarket market data.
These mirror the shapes returned by the CLOB and Gamma APIs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class MarketStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    RESOLVED = "resolved"


class OutcomeType(str, Enum):
    YES = "YES"
    NO = "NO"


@dataclass
class Token:
    """Represents a binary outcome token (YES or NO) within a market."""
    token_id: str          # CLOB token ID (used in orderbook queries)
    outcome: str           # "YES" or "NO"
    price: Decimal         # Current mid-price [0.0 – 1.0]
    winner: bool = False


@dataclass
class Market:
    """
    A Polymarket prediction market with its current state.
    Sourced from the Gamma API (/markets endpoint).
    """
    condition_id: str          # Unique market identifier (hex)
    question: str              # Human-readable question
    description: str
    status: MarketStatus
    tokens: list[Token]        # Typically 2 tokens: YES and NO
    category: str = ""
    end_date: Optional[datetime] = None
    volume_24h: Decimal = Decimal("0")
    volume_total: Decimal = Decimal("0")
    liquidity: Decimal = Decimal("0")

    @property
    def yes_price(self) -> Optional[Decimal]:
        for t in self.tokens:
            if t.outcome.upper() == "YES":
                return t.price
        return None

    @property
    def no_price(self) -> Optional[Decimal]:
        for t in self.tokens:
            if t.outcome.upper() == "NO":
                return t.price
        return None


@dataclass
class OrderBookLevel:
    """A single price level in the orderbook."""
    price: Decimal
    size: Decimal


@dataclass
class OrderBook:
    """
    Snapshot of the order book for a specific token.
    Sourced from the CLOB API (/book endpoint).
    """
    token_id: str
    market: str                        # condition_id of parent market
    asset_id: str
    bids: list[OrderBookLevel] = field(default_factory=list)   # sorted desc by price
    asks: list[OrderBookLevel] = field(default_factory=list)   # sorted asc by price
    timestamp: Optional[datetime] = None

    @property
    def best_bid(self) -> Optional[Decimal]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> Optional[Decimal]:
        if self.best_bid is not None and self.best_ask is not None:
            return self.best_ask - self.best_bid
        return None

    @property
    def mid_price(self) -> Optional[Decimal]:
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2
        return None


@dataclass
class MarketPrice:
    """Current price snapshot for a token from the CLOB /price endpoint."""
    token_id: str
    price: Decimal
    side: str   # "BUY" or "SELL"
