"""
Polymarket market data client.

Architecture decision: uses two APIs in tandem —

  1. Gamma API  (https://gamma-api.polymarket.com)
     • Public REST API — no authentication required
     • /markets   → list/search markets, metadata, prices, volume
     • Best for: discovering markets, filtering by category/status

  2. CLOB API   (https://clob.polymarket.com)
     • Central Limit Order Book — no auth required for *read* endpoints
     • /markets   → CLOB market list with token IDs
     • /book      → full orderbook (bids + asks) for a token
     • /price     → best current price for a token/side
     • /midpoint  → mid-price for a token
     • Best for: real-time prices, orderbook depth, spread analysis

  py-clob-client wraps the CLOB API with a Python SDK.
  We use httpx directly for the Gamma API (no official Python SDK).
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from .config import settings
from .models import Market, MarketStatus, OrderBook, OrderBookLevel, Token, MarketPrice

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry decorator shared by all HTTP calls
# ---------------------------------------------------------------------------
_RETRY = retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    stop=stop_after_attempt(settings.max_retries),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)


class PolymarketClient:
    """
    Read-only client for Polymarket market data.
    Compatible with paper-trading mode — no credentials required.
    """

    def __init__(self) -> None:
        self._gamma = httpx.AsyncClient(
            base_url=settings.gamma_api_base_url,
            timeout=settings.request_timeout,
            headers={"Accept": "application/json"},
        )
        self._clob = httpx.AsyncClient(
            base_url=settings.clob_api_base_url,
            timeout=settings.request_timeout,
            headers={"Accept": "application/json"},
        )
        logger.info(
            "PolymarketClient initialized | paper_trading=%s | clob=%s | gamma=%s",
            settings.paper_trading,
            settings.clob_api_base_url,
            settings.gamma_api_base_url,
        )

    async def close(self) -> None:
        await self._gamma.aclose()
        await self._clob.aclose()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------
    async def __aenter__(self) -> "PolymarketClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Gamma API — market discovery
    # ------------------------------------------------------------------

    @_RETRY
    async def get_markets(
        self,
        limit: int = 20,
        offset: int = 0,
        active: bool = True,
        category: Optional[str] = None,
    ) -> list[Market]:
        """
        Fetch a paginated list of markets from the Gamma API.

        Args:
            limit:    Number of markets to return (max 100).
            offset:   Pagination offset.
            active:   If True, filter to active markets only.
            category: Optional category filter (e.g. "politics", "sports").

        Returns:
            List of Market objects with current prices and metadata.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if active:
            params["active"] = "true"
        if category:
            params["tag_slug"] = category

        resp = await self._gamma.get("/markets", params=params)
        resp.raise_for_status()
        raw: list[dict] = resp.json()
        markets = [self._parse_gamma_market(m) for m in raw]
        logger.debug("Fetched %d markets from Gamma API", len(markets))
        return markets

    @_RETRY
    async def get_market_by_id(self, condition_id: str) -> Market:
        """Fetch a single market by its condition ID from the Gamma API."""
        resp = await self._gamma.get(f"/markets/{condition_id}")
        resp.raise_for_status()
        return self._parse_gamma_market(resp.json())

    # ------------------------------------------------------------------
    # CLOB API — orderbook and price data
    # ------------------------------------------------------------------

    @_RETRY
    async def get_orderbook(self, token_id: str) -> OrderBook:
        """
        Fetch the full orderbook for a token from the CLOB API.

        Args:
            token_id: The CLOB token ID (found in market.tokens[n].token_id).

        Returns:
            OrderBook with sorted bids and asks, spread, and mid-price.
        """
        resp = await self._clob.get("/book", params={"token_id": token_id})
        resp.raise_for_status()
        data = resp.json()
        return self._parse_orderbook(token_id, data)

    @_RETRY
    async def get_price(self, token_id: str, side: str = "BUY") -> MarketPrice:
        """
        Fetch the best current price for a token.

        Args:
            token_id: The CLOB token ID.
            side:     "BUY" or "SELL".

        Returns:
            MarketPrice with the best available price.
        """
        resp = await self._clob.get(
            "/price", params={"token_id": token_id, "side": side}
        )
        resp.raise_for_status()
        data = resp.json()
        return MarketPrice(
            token_id=token_id,
            price=Decimal(str(data.get("price", "0"))),
            side=side,
        )

    @_RETRY
    async def get_midpoint(self, token_id: str) -> Decimal:
        """
        Fetch the mid-price (average of best bid and ask) for a token.

        Args:
            token_id: The CLOB token ID.

        Returns:
            Mid-price as Decimal in range [0.0, 1.0].
        """
        resp = await self._clob.get("/midpoint", params={"token_id": token_id})
        resp.raise_for_status()
        data = resp.json()
        return Decimal(str(data.get("mid", "0")))

    @_RETRY
    async def get_clob_markets(self, next_cursor: str = "") -> dict:
        """
        Fetch the raw CLOB market list (paginated via cursor).
        Useful for mapping condition_id → token_id mappings.

        Args:
            next_cursor: Pagination cursor from a previous response.

        Returns:
            Raw dict with 'data' (list of markets) and 'next_cursor'.
        """
        params: dict[str, Any] = {}
        if next_cursor:
            params["next_cursor"] = next_cursor
        resp = await self._clob.get("/markets", params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Parsers — raw API dicts → domain models
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_gamma_market(data: dict) -> Market:
        tokens: list[Token] = []
        for t in data.get("tokens", []):
            tokens.append(
                Token(
                    token_id=t.get("token_id", ""),
                    outcome=t.get("outcome", ""),
                    price=Decimal(str(t.get("price", "0"))),
                    winner=t.get("winner", False),
                )
            )

        end_date: Optional[datetime] = None
        if raw_end := data.get("end_date_iso"):
            try:
                end_date = datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
            except ValueError:
                pass

        raw_status = data.get("active", True)
        status = MarketStatus.ACTIVE if raw_status else MarketStatus.CLOSED

        return Market(
            condition_id=data.get("condition_id", ""),
            question=data.get("question", ""),
            description=data.get("description", ""),
            status=status,
            tokens=tokens,
            category=data.get("category", ""),
            end_date=end_date,
            volume_24h=Decimal(str(data.get("volume24hr", "0") or "0")),
            volume_total=Decimal(str(data.get("volume", "0") or "0")),
            liquidity=Decimal(str(data.get("liquidity", "0") or "0")),
        )

    @staticmethod
    def _parse_orderbook(token_id: str, data: dict) -> OrderBook:
        def parse_levels(raw: list[dict]) -> list[OrderBookLevel]:
            return [
                OrderBookLevel(
                    price=Decimal(str(entry.get("price", "0"))),
                    size=Decimal(str(entry.get("size", "0"))),
                )
                for entry in raw
            ]

        return OrderBook(
            token_id=token_id,
            market=data.get("market", ""),
            asset_id=data.get("asset_id", token_id),
            bids=parse_levels(data.get("bids", [])),
            asks=parse_levels(data.get("asks", [])),
            timestamp=datetime.utcnow(),
        )
