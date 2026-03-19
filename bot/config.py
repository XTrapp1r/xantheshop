import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    BOT_TOKEN: str
    ADMIN_IDS: List[int]
    SUPPORT_USERNAME: str
    REVIEWS_URL: str
    GUARANTEES_URL: str | None
    PAYMENT_MODE: str
    PALLY_API_TOKEN: str | None
    DATABASE_URL: str


def _parse_admin_ids(raw: str) -> List[int]:
    ids: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if part.lstrip("-").isdigit():
            ids.append(int(part))
    return ids


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN не указан в переменных окружения")

    admin_ids_raw = os.getenv("ADMIN_IDS", "")
    admin_ids = _parse_admin_ids(admin_ids_raw)

    support_username = os.getenv("SUPPORT_USERNAME", "@x4nth3")
    reviews_url = os.getenv("REVIEWS_URL", "https://t.me/xantheshop/7")
    guarantees_url = os.getenv("GUARANTEES_URL") or None
    payment_mode = os.getenv("PAYMENT_MODE", "fake").strip().lower() or "fake"
    pally_api_token = os.getenv("PALLY_API_TOKEN", "").strip() or None
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./shop.db")

    return Config(
        BOT_TOKEN=bot_token,
        ADMIN_IDS=admin_ids,
        SUPPORT_USERNAME=support_username,
        REVIEWS_URL=reviews_url,
        GUARANTEES_URL=guarantees_url,
        PAYMENT_MODE=payment_mode,
        PALLY_API_TOKEN=pally_api_token,
        DATABASE_URL=database_url,
    )
