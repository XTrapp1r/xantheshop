from datetime import datetime, timedelta, timezone
from typing import Tuple

import httpx
from sqlalchemy import select

from bot.config import load_config
from bot.database.db import AsyncSessionLocal
from bot.database.models import Order, OrderStatus, Product, User

config = load_config()

CREATE_BILL_URL = "https://paypalych.com/api/v1/bill/create"
CHECK_BILL_URL = "https://paypalych.com/api/v1/bill/status"


async def create_payment_for_order(order: Order) -> Order:
    """
    Совместимость со старым интерфейсом.
    """
    return await create_payment(order)


async def create_payment(order: Order) -> Order:
    """
    Создаёт счёт в Paypalych и сохраняет bill_id/pay_url в заказ.
    """
    if not config.PALLY_API_TOKEN:
        raise RuntimeError("PALLY_API_TOKEN не указан в переменных окружения")

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

        headers = {
            "Authorization": f"Bearer {config.PALLY_API_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "amount": db_order.total_price,
            "order_id": str(db_order.id),
            "description": f"Оплата заказа {db_order.id}",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(CREATE_BILL_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        bill_id = (
            data.get("bill_id")
            or data.get("id")
            or (data.get("data") or {}).get("bill_id")
            or (data.get("result") or {}).get("bill_id")
        )
        pay_url = (
            data.get("pay_url")
            or data.get("url")
            or (data.get("data") or {}).get("pay_url")
            or (data.get("result") or {}).get("pay_url")
            or product.payment_url
        )
        if not bill_id:
            raise RuntimeError("Paypalych не вернул bill_id")

        db_order.payment_provider = "paypalych"
        db_order.payment_status = "pending"
        db_order.payment_id = str(bill_id)
        db_order.payment_url = str(pay_url)

        await session.commit()
        await session.refresh(db_order)
        return db_order


async def check_payment(payment_id: str) -> bool:
    """
    Проверяет статус счёта в Paypalych.
    """
    if not config.PALLY_API_TOKEN or not payment_id:
        return False

    headers = {
        "Authorization": f"Bearer {config.PALLY_API_TOKEN}",
    }
    params = {
        "bill_id": payment_id,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(CHECK_BILL_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

    status = (
        data.get("status")
        or (data.get("data") or {}).get("status")
        or (data.get("result") or {}).get("status")
        or ""
    )
    return str(status).lower() == "paid"


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


async def mark_order_paid(order_id: int) -> Tuple[Order | None, User | None]:
    """
    Помечает заказ как оплаченный.
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
            if created_utc < threshold and (order.payment_status or "pending") != "paid":
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

