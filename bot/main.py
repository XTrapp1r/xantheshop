import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import load_config
from bot.database.db import init_db
from bot.database.seed import seed_initial_data
from bot.handlers import admin, catalog, info, orders, start
from bot.services import payment_service
from bot.webhooks import build_webhook_app

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

    async def _auto_cancel_loop() -> None:
        while True:
            try:
                await payment_service.auto_cancel_expired_unpaid_orders()
            except Exception:
                logging.exception("Ошибка авто-отмены неоплаченных заказов")
            await asyncio.sleep(300)

    asyncio.create_task(_auto_cancel_loop())

    webhook_app = build_webhook_app(bot)
    webhook_config = uvicorn.Config(
        app=webhook_app,
        host="0.0.0.0",
        port=8080,
        log_level="warning",
        loop="asyncio",
    )
    webhook_server = uvicorn.Server(webhook_config)
    asyncio.create_task(webhook_server.serve())

    result_url = payment_service.get_result_url()
    if result_url:
        logging.info("PayPalych Result URL: %s", result_url)
    else:
        logging.warning("PUBLIC_BASE_URL не задан: укажите его для Result URL PayPalych")

    logging.info("Бот запущен. Ожидание обновлений...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

