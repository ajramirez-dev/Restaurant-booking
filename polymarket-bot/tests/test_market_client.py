"""
Tests for PolymarketClient.

Uses respx to mock HTTP responses — no real network calls are made.
All tests run in paper trading mode by default.
"""
from __future__ import annotations

import pytest
import respx
import httpx
from decimal import Decimal
from unittest.mock import patch

from src.market_client import PolymarketClient
from src.models import Market, MarketStatus, OrderBook, MarketPrice


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_GAMMA_MARKET = {
    "condition_id": "0xabc123",
    "question": "Will Bitcoin reach $100k by end of 2025?",
    "description": "This market resolves YES if BTC/USD closes above 100000.",
    "active": True,
    "category": "crypto",
    "end_date_iso": "2025-12-31T23:59:59Z",
    "volume24hr": "150000.50",
    "volume": "2500000.00",
    "liquidity": "85000.00",
    "tokens": [
        {"token_id": "token_yes_001", "outcome": "YES", "price": "0.67", "winner": False},
        {"token_id": "token_no_001",  "outcome": "NO",  "price": "0.33", "winner": False},
    ],
}

SAMPLE_ORDERBOOK = {
    "market": "0xabc123",
    "asset_id": "token_yes_001",
    "bids": [
        {"price": "0.66", "size": "500.00"},
        {"price": "0.65", "size": "1200.00"},
        {"price": "0.64", "size": "3000.00"},
    ],
    "asks": [
        {"price": "0.68", "size": "400.00"},
        {"price": "0.69", "size": "900.00"},
        {"price": "0.70", "size": "2500.00"},
    ],
}

SAMPLE_PRICE = {"price": "0.67"}
SAMPLE_MIDPOINT = {"mid": "0.67"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> PolymarketClient:
    return PolymarketClient()


# ---------------------------------------------------------------------------
# get_markets
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_get_markets_returns_parsed_list(client: PolymarketClient) -> None:
    respx.get("https://gamma-api.polymarket.com/markets").mock(
        return_value=httpx.Response(200, json=[SAMPLE_GAMMA_MARKET])
    )

    markets = await client.get_markets(limit=1)

    assert len(markets) == 1
    m = markets[0]
    assert isinstance(m, Market)
    assert m.condition_id == "0xabc123"
    assert m.question == "Will Bitcoin reach $100k by end of 2025?"
    assert m.status == MarketStatus.ACTIVE
    assert m.yes_price == Decimal("0.67")
    assert m.no_price == Decimal("0.33")
    assert m.liquidity == Decimal("85000.00")


@pytest.mark.asyncio
@respx.mock
async def test_get_markets_passes_active_filter(client: PolymarketClient) -> None:
    route = respx.get("https://gamma-api.polymarket.com/markets").mock(
        return_value=httpx.Response(200, json=[SAMPLE_GAMMA_MARKET])
    )

    await client.get_markets(active=True)

    assert route.called
    request = route.calls[0].request
    assert b"active=true" in request.url.query


@pytest.mark.asyncio
@respx.mock
async def test_get_markets_handles_empty_response(client: PolymarketClient) -> None:
    respx.get("https://gamma-api.polymarket.com/markets").mock(
        return_value=httpx.Response(200, json=[])
    )

    markets = await client.get_markets()
    assert markets == []


@pytest.mark.asyncio
@respx.mock
async def test_get_markets_raises_on_http_error(client: PolymarketClient) -> None:
    respx.get("https://gamma-api.polymarket.com/markets").mock(
        return_value=httpx.Response(500, json={"error": "Internal server error"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_markets()


# ---------------------------------------------------------------------------
# get_market_by_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_get_market_by_id_returns_single_market(client: PolymarketClient) -> None:
    respx.get("https://gamma-api.polymarket.com/markets/0xabc123").mock(
        return_value=httpx.Response(200, json=SAMPLE_GAMMA_MARKET)
    )

    market = await client.get_market_by_id("0xabc123")

    assert market.condition_id == "0xabc123"
    assert len(market.tokens) == 2


# ---------------------------------------------------------------------------
# get_orderbook
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_get_orderbook_parses_bids_and_asks(client: PolymarketClient) -> None:
    respx.get("https://clob.polymarket.com/book").mock(
        return_value=httpx.Response(200, json=SAMPLE_ORDERBOOK)
    )

    book = await client.get_orderbook("token_yes_001")

    assert isinstance(book, OrderBook)
    assert book.token_id == "token_yes_001"
    assert len(book.bids) == 3
    assert len(book.asks) == 3


@pytest.mark.asyncio
@respx.mock
async def test_get_orderbook_best_bid_ask(client: PolymarketClient) -> None:
    respx.get("https://clob.polymarket.com/book").mock(
        return_value=httpx.Response(200, json=SAMPLE_ORDERBOOK)
    )

    book = await client.get_orderbook("token_yes_001")

    assert book.best_bid == Decimal("0.66")
    assert book.best_ask == Decimal("0.68")


@pytest.mark.asyncio
@respx.mock
async def test_get_orderbook_spread_and_midprice(client: PolymarketClient) -> None:
    respx.get("https://clob.polymarket.com/book").mock(
        return_value=httpx.Response(200, json=SAMPLE_ORDERBOOK)
    )

    book = await client.get_orderbook("token_yes_001")

    assert book.spread == Decimal("0.02")
    assert book.mid_price == Decimal("0.67")


@pytest.mark.asyncio
@respx.mock
async def test_get_orderbook_empty_book(client: PolymarketClient) -> None:
    respx.get("https://clob.polymarket.com/book").mock(
        return_value=httpx.Response(200, json={"market": "0xabc123", "asset_id": "t1", "bids": [], "asks": []})
    )

    book = await client.get_orderbook("t1")

    assert book.best_bid is None
    assert book.best_ask is None
    assert book.spread is None
    assert book.mid_price is None


# ---------------------------------------------------------------------------
# get_price
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_get_price_returns_market_price(client: PolymarketClient) -> None:
    respx.get("https://clob.polymarket.com/price").mock(
        return_value=httpx.Response(200, json=SAMPLE_PRICE)
    )

    price = await client.get_price("token_yes_001", side="BUY")

    assert isinstance(price, MarketPrice)
    assert price.token_id == "token_yes_001"
    assert price.price == Decimal("0.67")
    assert price.side == "BUY"


# ---------------------------------------------------------------------------
# get_midpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_get_midpoint_returns_decimal(client: PolymarketClient) -> None:
    respx.get("https://clob.polymarket.com/midpoint").mock(
        return_value=httpx.Response(200, json=SAMPLE_MIDPOINT)
    )

    mid = await client.get_midpoint("token_yes_001")

    assert mid == Decimal("0.67")


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------

def test_market_yes_no_price_accessors() -> None:
    from src.models import Token, Market
    market = PolymarketClient._parse_gamma_market(SAMPLE_GAMMA_MARKET)
    assert market.yes_price == Decimal("0.67")
    assert market.no_price == Decimal("0.33")


def test_market_closed_status() -> None:
    data = {**SAMPLE_GAMMA_MARKET, "active": False}
    market = PolymarketClient._parse_gamma_market(data)
    assert market.status == MarketStatus.CLOSED


def test_orderbook_model_empty_defaults() -> None:
    book = OrderBook(token_id="t1", market="m1", asset_id="t1")
    assert book.best_bid is None
    assert book.spread is None
    assert book.mid_price is None
