"""
Centralized configuration loaded from environment variables.
All settings are read-only after initialization.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # Mode
    paper_trading: bool = field(
        default_factory=lambda: os.getenv("PAPER_TRADING", "true").lower() == "true"
    )

    # API base URLs
    clob_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "CLOB_API_BASE_URL", "https://clob.polymarket.com"
        )
    )
    gamma_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "GAMMA_API_BASE_URL", "https://gamma-api.polymarket.com"
        )
    )

    # Auth (optional — only for order placement, not needed for reads)
    private_key: str | None = field(
        default_factory=lambda: os.getenv("POLYMARKET_PRIVATE_KEY") or None
    )
    api_key: str | None = field(
        default_factory=lambda: os.getenv("POLYMARKET_API_KEY") or None
    )
    api_secret: str | None = field(
        default_factory=lambda: os.getenv("POLYMARKET_API_SECRET") or None
    )
    api_passphrase: str | None = field(
        default_factory=lambda: os.getenv("POLYMARKET_API_PASSPHRASE") or None
    )

    # HTTP settings
    request_timeout: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_TIMEOUT", "10"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("MAX_RETRIES", "3"))
    )

    # Logging
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper()
    )

    @property
    def has_auth(self) -> bool:
        """True if credentials are configured for authenticated requests."""
        return all([self.private_key, self.api_key, self.api_secret, self.api_passphrase])


# Singleton — import this everywhere
settings = Config()
