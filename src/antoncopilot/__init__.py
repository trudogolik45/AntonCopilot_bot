import asyncio

import httpx
from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from antoncopilot.app import build_dispatcher
from antoncopilot.config import Settings
from antoncopilot.db import Base
from antoncopilot.llm import OpenRouterWriter
from antoncopilot.logs import setup_logging


async def run() -> None:
    settings = Settings()  # type: ignore[call-arg]
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with httpx.AsyncClient(timeout=60) as http:
        writer = OpenRouterWriter(
            http,
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            style=settings.style_path.read_text(encoding="utf-8"),
        )
        dp = build_dispatcher(async_sessionmaker(engine, expire_on_commit=False), writer)
        bot = Bot(settings.bot_token)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    await engine.dispose()


def main() -> None:
    setup_logging()
    asyncio.run(run())
