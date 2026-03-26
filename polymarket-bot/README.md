# Polymarket Trading Bot

Automated prediction market trading bot for [Polymarket](https://polymarket.com).
Currently operates in **paper trading mode only** (no real funds).

---

## Architecture — API Stack

This bot uses **two complementary APIs**:

| API | Base URL | Auth Required | Purpose |
|-----|----------|---------------|---------|
| **Gamma API** | `https://gamma-api.polymarket.com` | No | Market discovery, metadata, volume |
| **CLOB API** | `https://clob.polymarket.com` | No (reads) / Yes (writes) | Real-time prices, orderbook depth |

### Why two APIs?

- **Gamma API** is the best source for *discovering* markets — it returns human-readable
  market metadata (question, description, category, volume, liquidity) plus current prices.
  It does not require authentication for public data.

- **CLOB API** (Central Limit Order Book) provides *real-time* orderbook data:
  full bid/ask ladders, best prices, and mid-points. It also exposes the token IDs
  needed to query the orderbook. Reads are public; placing orders requires L1/L2 auth.

- **py-clob-client** (`pip install py-clob-client`) is the official Python SDK that wraps
  the CLOB API. We use it for convenience but also expose raw `httpx` calls for endpoints
  not yet covered by the SDK.

---

## Project Structure

```
polymarket-bot/
├── .env.example        # Template for environment variables
├── .gitignore          # Excludes .env, __pycache__, .venv
├── requirements.txt    # Pinned dependencies
├── README.md           # This file
├── src/
│   ├── __init__.py
│   ├── config.py       # Centralised config (reads from .env)
│   ├── models.py       # Domain dataclasses: Market, OrderBook, Token…
│   └── market_client.py  # HTTP client for Gamma + CLOB APIs
└── tests/
    ├── __init__.py
    └── test_market_client.py  # Unit tests (fully mocked, no network)
```

---

## Quick Start

### 1. Clone and set up

```bash
git clone <repo-url>
cd polymarket-bot

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — for read-only / paper trading, no credentials needed
```

### 3. Run tests

```bash
pytest tests/ -v
```

### 4. Explore markets (example script)

```python
import asyncio
from src.market_client import PolymarketClient

async def main():
    async with PolymarketClient() as client:
        # List top 5 active markets
        markets = await client.get_markets(limit=5)
        for m in markets:
            print(f"{m.question}")
            print(f"  YES: {m.yes_price:.2f}  NO: {m.no_price:.2f}")
            print(f"  Liquidity: ${m.liquidity:,.0f}")
            print()

        # Get full orderbook for the first YES token
        token_id = markets[0].tokens[0].token_id
        book = await client.get_orderbook(token_id)
        print(f"Best bid: {book.best_bid}  Best ask: {book.best_ask}")
        print(f"Spread:   {book.spread}    Mid-price: {book.mid_price}")

asyncio.run(main())
```

---

## Key Endpoints

### Gamma API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/markets` | GET | List markets. Params: `limit`, `offset`, `active`, `tag_slug` |
| `/markets/{condition_id}` | GET | Single market by ID |

### CLOB API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/markets` | GET | CLOB market list with token IDs (paginated via cursor) |
| `/book` | GET | Full orderbook. Param: `token_id` |
| `/price` | GET | Best price. Params: `token_id`, `side` (`BUY`/`SELL`) |
| `/midpoint` | GET | Mid-price. Param: `token_id` |

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `py-clob-client` | 0.19.0 | Official Polymarket CLOB SDK |
| `httpx` | 0.27.2 | Async HTTP client |
| `pydantic` | 2.9.2 | Data validation |
| `python-dotenv` | 1.0.1 | `.env` file loading |
| `tenacity` | 9.0.0 | Retry logic with exponential backoff |
| `pytest` + `respx` | latest | Testing with HTTP mocking |

---

## Paper Trading Mode

`PAPER_TRADING=true` in `.env` (default) disables any order-placing code paths.
The `settings.paper_trading` flag is checked throughout the codebase to ensure
no real orders are submitted accidentally.

---

## Roadmap

- [x] Phase 1 — API connection, market data reading, orderbook parsing
- [ ] Phase 2 — Paper trading engine (simulated fills, P&L tracking)
- [ ] Phase 3 — Signal generation (price model, edge detection)
- [ ] Phase 4 — Live trading with position sizing and risk management
