from datetime import datetime, timedelta, timezone
from typing import Tuple

import httpx
import logging
from sqlalchemy import select

from bot.config import load_config
from bot.database.db import AsyncSessionLocal
from bot.database.models import Order, OrderStatus, Product, User

config = load_config()
logger = logging.getLogger(__name__)

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

        payload = {
            "amount": db_order.total_price,
            "order_id": str(db_order.id),
            "description": f"Оплата заказа {db_order.id}",
        }
        data = None
        auth_variants = [
            f"Bearer {config.PALLY_API_TOKEN}",
            config.PALLY_API_TOKEN,
        ]
        async with httpx.AsyncClient(timeout=20.0) as client:
            for auth in auth_variants:
                try:
                    response = await client.post(
                        CREATE_BILL_URL,
                        headers={
                            "Authorization": auth,
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    if response.status_code >= 400:
                        logger.warning(
                            "Paypalych create bill failed: status=%s body=%s",
                            response.status_code,
                            response.text[:400],
                        )
                        continue
                    data = response.json()
                    break
                except Exception as exc:
                    logger.warning("Paypalych create bill request error: %s", exc)
                    continue

        bill_id = (
            (data or {}).get("bill_id")
            or (data or {}).get("id")
            or (((data or {}).get("data") or {}).get("bill_id"))
            or (((data or {}).get("result") or {}).get("bill_id"))
        )
        pay_url = (
            (data or {}).get("pay_url")
            or (data or {}).get("url")
            or (((data or {}).get("data") or {}).get("pay_url"))
            or (((data or {}).get("result") or {}).get("pay_url"))
            or product.payment_url
        )
        # Fallback: если API недоступен, оставляем payment_url из товара,
        # чтобы пользователь всё равно мог оплатить по рабочей ссылке.
        if not bill_id:
            logger.warning("Paypalych не вернул bill_id, используем fallback-ссылку товара")
            bill_id = f"fallback-{db_order.id}"

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

    params = {
        "bill_id": payment_id,
    }
    auth_variants = [
        f"Bearer {config.PALLY_API_TOKEN}",
        config.PALLY_API_TOKEN,
    ]
    async with httpx.AsyncClient(timeout=20.0) as client:
        data = None
        for auth in auth_variants:
            try:
                response = await client.get(
                    CHECK_BILL_URL,
                    headers={"Authorization": auth},
                    params=params,
                )
                if response.status_code >= 400:
                    logger.warning(
                        "Paypalych check bill failed: status=%s body=%s",
                        response.status_code,
                        response.text[:400],
                    )
                    continue
                data = response.json()
                break
            except Exception as exc:
                logger.warning("Paypalych check bill request error: %s", exc)
                continue
    if data is None:
        return False

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

