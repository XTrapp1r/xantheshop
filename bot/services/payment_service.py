from typing import Tuple

from sqlalchemy import select

from bot.database.db import AsyncSessionLocal
from bot.database.models import Order, OrderStatus, Product, User


async def create_payment_for_order(order: Order) -> Order:
    """
    Подготавливает платёж для заказа без вызова внешних API.

    Логика:
    - payment_status = "pending"
    - payment_url берётся из связанного товара (Product.payment_url)
    - payment_id — любой UUID (строка)
    """
    import uuid

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

        db_order.payment_provider = "pally"
        db_order.payment_status = "pending"
        db_order.payment_id = str(uuid.uuid4())
        db_order.payment_url = product.payment_url

        await session.commit()
        await session.refresh(db_order)
        return db_order


async def get_payment_status(order_id: int) -> str:
    """
    Возвращает статус оплаты заказа.
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Order).where(Order.id == order_id))
        db_order = res.scalar_one_or_none()
        if db_order is None:
            return "unknown"
        return db_order.payment_status or "pending"


async def confirm_manual_payment(order_id: int) -> Tuple[Order | None, User | None]:
    """
    Ручное подтверждение оплаты пользователем.

    Меняет:
    - payment_status -> "paid"
    - order.status -> OrderStatus.PAID
    """
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

        if order.payment_status == "paid":
            return order, user

        order.payment_status = "paid"
        order.status = OrderStatus.PAID

        await session.commit()
        await session.refresh(order)

        return order, user


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

