import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import load_config
from bot.database.db import init_db
from bot.database.seed import seed_initial_data
from bot.handlers import admin, catalog, info, orders, start

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main() -> None:
    config = load_config()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(orders.router)
    dp.include_router(info.router)
    dp.include_router(admin.router)

    await init_db()
    await seed_initial_data()

    logging.info("Бот запущен. Ожидание обновлений...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

