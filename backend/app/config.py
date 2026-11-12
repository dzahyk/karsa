from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    ai_provider: str  # "demo" | "anthropic"
    anthropic_api_key: str | None
    anthropic_model: str
    cors_origins: tuple[str, ...]
    timezone: str
    demo_mode: bool
    cookie_secure: bool
    worker_enabled: bool
    static_dir: str | None


def get_settings() -> Settings:
    provider = (os.getenv("AI_PROVIDER") or "demo").strip().lower()
    key = os.getenv("ANTHROPIC_API_KEY") or None
    if provider == "anthropic" and not key:
        provider = "demo"  # fail safe: never pretend a provider is active without a key
    origins = os.getenv("CORS_ORIGINS") or "http://localhost:5173"
    return Settings(
        database_url=os.getenv("DATABASE_URL") or f"sqlite:///{ROOT / 'decisionflow.db'}",
        ai_provider=provider,
        anthropic_api_key=key,
        anthropic_model=os.getenv("ANTHROPIC_MODEL") or "claude-opus-5-5",
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        timezone=os.getenv("APP_TIMEZONE") or "Asia/Jakarta",
        demo_mode=_flag("DEMO_MODE", True),
        cookie_secure=_flag("COOKIE_SECURE", False),
        worker_enabled=_flag("WORKER_ENABLED", True),
        static_dir=os.getenv("STATIC_DIR") or None,
    )


def _flag(name: str, default: bool) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return default if not v else v in ("1", "true", "yes", "on")
