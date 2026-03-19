from datetime import datetime, timedelta, timezone
import logging

import httpx
from aiogram import Bot
from sqlalchemy import select

from bot.config import load_config
from bot.database.db import AsyncSessionLocal
from bot.database.models import Order, OrderStatus, Product, User

config = load_config()
logger = logging.getLogger(__name__)

CREATE_BILL_URL = "https://pal24.pro/api/v1/bill/create"


async def create_payment_for_order(order: Order) -> Order:
    """
    Совместимость со старым интерфейсом.
    """
    return await create_payment(order)


async def create_payment(order: Order) -> Order:
    """
    Создаёт уникальный bill в PayPalych для заказа.
    """
    if not config.PALLY_API_TOKEN:
        raise RuntimeError("PALLY_API_TOKEN не указан в переменных окружения")
    if not config.PALLY_SHOP_ID:
        raise RuntimeError("PALLY_SHOP_ID не указан в переменных окружения")

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Order).where(Order.id == order.id))
        db_order = res.scalar_one_or_none()
        if db_order is None:
            return order

        if db_order.product_id is None:
            return db_order

        prod_res = await session.execute(
            select(Product).where(Product.id == db_order.product_id)
        )
        product = prod_res.scalar_one_or_none()
        if product is None:
            return db_order

        payload = {
            "amount": db_order.total_price,
            "order_id": str(db_order.id),
            "description": f"Оплата заказа #{db_order.id}",
            "type": "normal",
            "shop_id": config.PALLY_SHOP_ID,
            "currency_in": "RUB",
            "custom": f"order:{db_order.id}",
            "payer_pays_commission": 1,
            "name": db_order.product_name_snapshot,
        }

        data = None
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                CREATE_BILL_URL,
                headers={"Authorization": f"Bearer {config.PALLY_API_TOKEN}"},
                data=payload,  # form-data/x-www-form-urlencoded
            )
            if response.status_code >= 400:
                logger.error(
                    "PayPalych create bill failed: status=%s body=%s",
                    response.status_code,
                    response.text[:500],
                )
                raise RuntimeError("PayPalych вернул ошибку при создании счёта")
            data = response.json()

        success = bool(
            data.get("success")
            or (data.get("data") or {}).get("success")
            or (data.get("result") or {}).get("success")
        )
        if not success:
            logger.error("PayPalych create bill unsuccessful response: %s", data)
            raise RuntimeError("Не удалось создать счёт в PayPalych")

        bill_id = (
            data.get("bill_id")
            or data.get("id")
            or (data.get("data") or {}).get("bill_id")
            or (data.get("result") or {}).get("bill_id")
        )
        pay_url = (
            data.get("link_page_url")
            or data.get("pay_url")
            or data.get("url")
            or (data.get("data") or {}).get("link_page_url")
            or (data.get("result") or {}).get("link_page_url")
        )
        if not bill_id or not pay_url:
            logger.error("PayPalych response missing bill_id or link_page_url: %s", data)
            raise RuntimeError("PayPalych не вернул bill_id/link_page_url")

        db_order.payment_provider = "paypalych"
        db_order.payment_status = "pending"
        db_order.payment_id = str(bill_id)
        db_order.payment_url = str(pay_url)

        await session.commit()
        await session.refresh(db_order)
        return db_order


async def get_payment_status(order_id: int) -> str:
    """
    Возвращает текущий status оплаты из БД.
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Order).where(Order.id == order_id))
        db_order = res.scalar_one_or_none()
        if db_order is None:
            return "unknown"
        return db_order.payment_status or "pending"


def get_result_url() -> str | None:
    if not config.PUBLIC_BASE_URL:
        return None
    return f"{config.PUBLIC_BASE_URL}/webhooks/paypalych/result"


async def process_paypalych_postback(payload: dict, bot: Bot) -> str:
    """
    Обрабатывает postback от PayPalych. Идемпотентно.
    """
    status = str(payload.get("Status", "")).upper()
    inv_id_raw = str(payload.get("InvId", "")).strip()
    trs_id = str(payload.get("TrsId", "")).strip() or None
    custom = str(payload.get("custom", "")).strip()

    order_id: int | None = None
    if inv_id_raw.isdigit():
        order_id = int(inv_id_raw)
    elif custom.startswith("order:") and custom.split(":", 1)[1].isdigit():
        order_id = int(custom.split(":", 1)[1])

    if order_id is None:
        logger.warning("PayPalych postback: invalid order id payload=%s", payload)
        return "ok"

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Order, User)
            .join(User, Order.user_id == User.id)
            .where(Order.id == order_id)
        )
        row = res.one_or_none()
        if row is None:
            logger.warning("PayPalych postback: order not found order_id=%s", order_id)
            return "ok"

        order, user = row
        if order.payment_status == "paid":
            # Повторный postback: не дублируем бизнес-логику/уведомления.
            return "ok"

        if status == "SUCCESS":
            order.payment_status = "paid"
            order.status = OrderStatus.PAID
            if trs_id:
                order.payment_id = trs_id
            await session.commit()
            await session.refresh(order)

            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text="✅ Оплата получена. Ваш заказ передан в обработку.",
                )
            except Exception:
                logger.exception("Не удалось отправить уведомление пользователю order_id=%s", order.id)

            from bot.keyboards.inline import admin_order_status_kb

            admin_text = (
                "🔥 Новый оплаченный заказ\n\n"
                f"ID: {order.id}\n"
                f"Товар: {order.product_name_snapshot}\n"
                f"Количество: {order.quantity}\n"
                f"Сумма: {order.total_price} ₽\n"
                f"Supercell ID: {order.supercell_id}\n"
                f"Юзер: @{user.username or 'без_username'} / Telegram ID: {user.telegram_id}\n\n"
                "Статус: Ожидает выполнения"
            )
            for admin_id in config.ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=admin_text,
                        reply_markup=admin_order_status_kb(order.id),
                    )
                except Exception:
                    logger.exception("Не удалось отправить уведомление админу admin_id=%s", admin_id)
            return "ok"

        if status == "FAIL":
            order.payment_status = "failed"
            order.status = OrderStatus.CANCELLED
            await session.commit()
            await session.refresh(order)
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text="❌ Оплата не прошла. Попробуйте снова или оформите новый заказ.",
                )
            except Exception:
                logger.exception("Не удалось отправить FAIL уведомление пользователю order_id=%s", order.id)
            return "ok"

        logger.info("PayPalych postback ignored: status=%s payload=%s", status, payload)
        return "ok"


async def auto_cancel_expired_unpaid_orders() -> int:
    """
    Отменяет заказы старше 30 минут без подтверждённой оплаты.
    """
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(minutes=30)

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Order).where(
                Order.status == OrderStatus.NEW,
            )
        )
        orders = list(res.scalars().all())
        updated = 0
        for order in orders:
            created = order.created_at
            if created is None:
                continue
            created_utc = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
            if created_utc < threshold and (order.payment_status or "pending") == "pending":
                order.status = OrderStatus.CANCELLED
                order.payment_status = "failed"
                updated += 1

        if updated:
            await session.commit()
        return updated


async def cancel_order(order_id: int) -> Order | None:
    """
    Отмена заказа вместе с оплатой.
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Order).where(Order.id == order_id))
        order = res.scalar_one_or_none()
        if order is None:
            return None

        order.status = OrderStatus.CANCELLED
        order.payment_status = "failed"

        await session.commit()
        await session.refresh(order)

        return order

