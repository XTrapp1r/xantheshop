from typing import Tuple

from sqlalchemy import select

from bot.config import load_config
from bot.database.db import AsyncSessionLocal
from bot.database.models import Order, OrderStatus, User

config = load_config()


async def create_payment_for_order(order: Order) -> Order:
    """
    Создаёт (или подготавливает) платёж для заказа.

    В fake-режиме просто сохраняем тестовые данные в полях оплаты.
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Order).where(Order.id == order.id))
        db_order = res.scalar_one_or_none()
        if db_order is None:
            return order

        if config.PAYMENT_MODE == "fake":
            db_order.payment_provider = "fake"
            db_order.payment_status = "pending"
            db_order.payment_id = str(db_order.id)
            db_order.payment_url = None

        await session.commit()
        await session.refresh(db_order)
        return db_order


async def get_payment_status(order: Order) -> str:
    """
    Возвращает статус оплаты заказа (для fake-режима — значение из поля payment_status).
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Order).where(Order.id == order.id))
        db_order = res.scalar_one_or_none()
        if db_order is None:
            return "unknown"
        return db_order.payment_status or "pending"


async def confirm_fake_payment(order_id: int) -> Tuple[Order | None, User | None]:
    """
    Тестовое подтверждение оплаты.

    Меняет статус заказа на PAID и payment_status на paid.
    """
    if config.PAYMENT_MODE != "fake":
        return None, None

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Order, User)
            .join(User, Order.user_id == User.id)
            .where(Order.id == order_id)
        )
        row = res.one_or_none()
        if row is None:
            return None, None

        order, user = row
        order.payment_provider = "fake"
        order.payment_status = "paid"
        order.status = OrderStatus.PAID

        await session.commit()
        await session.refresh(order)

        return order, user


async def cancel_order(order_id: int) -> Order | None:
    """
    Отмена заказа вместе с оплатой (в fake-режиме просто помечаем как cancelled).
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Order).where(Order.id == order_id))
        order = res.scalar_one_or_none()
        if order is None:
            return None

        order.status = OrderStatus.CANCELLED
        order.payment_status = "cancelled"

        await session.commit()
        await session.refresh(order)

        return order

