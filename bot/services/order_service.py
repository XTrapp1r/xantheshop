from typing import List, Tuple

from sqlalchemy import Select, func, select

from bot.database.db import AsyncSessionLocal
from bot.database.models import Order, OrderStatus, Product, User


async def create_order(
    telegram_id: int,
    product_id: int,
    quantity: int,
    supercell_id: str,
) -> Order:
    """
    Создаёт заказ со snapshot названия и цены товара.
    """
    async with AsyncSessionLocal() as session:
        user_stmt: Select[tuple[User]] = select(User).where(
            User.telegram_id == telegram_id
        )
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            user = User(telegram_id=telegram_id, username=None, first_name=None)
            session.add(user)
            await session.flush()

        product_stmt: Select[tuple[Product]] = select(Product).where(
            Product.id == product_id
        )
        product_res = await session.execute(product_stmt)
        product = product_res.scalar_one_or_none()
        if not product or not product.is_active:
            raise ValueError("Товар недоступен")

        total_price = product.price * quantity

        order = Order(
            user_id=user.id,
            product_id=product.id,
            product_name_snapshot=product.name,
            price_snapshot=product.price,
            quantity=quantity,
            total_price=total_price,
            supercell_id=supercell_id,
            status=OrderStatus.NEW,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def get_user_orders_by_telegram_id(
    telegram_id: int,
    active_only: bool = False,
) -> List[Order]:
    async with AsyncSessionLocal() as session:
        user_res = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = user_res.scalar_one_or_none()
        if not user:
            return []

        stmt = select(Order).where(Order.user_id == user.id)
        if active_only:
            stmt = stmt.where(
                Order.status.in_(
                    [
                        OrderStatus.NEW,
                        OrderStatus.PAID,
                        OrderStatus.IN_PROGRESS,
                    ]
                )
            )

        stmt = stmt.order_by(Order.created_at.desc())
        orders_res = await session.execute(stmt)
        return list(orders_res.scalars().all())


async def get_last_orders(limit: int = 20) -> List[Order]:
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Order).order_by(Order.created_at.desc()).limit(limit)
        )
        return list(res.scalars().all())


async def get_active_orders() -> List[Order]:
    """
    Все заказы, которые ещё не обработаны до конца:
    NEW, PAID, IN_PROGRESS.
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Order)
            .where(
                Order.status.in_(
                    [
                        OrderStatus.NEW,
                        OrderStatus.PAID,
                        OrderStatus.IN_PROGRESS,
                    ]
                )
            )
            .order_by(Order.created_at.desc())
        )
        return list(res.scalars().all())


async def get_stats() -> Tuple[int, int, int]:
    """
    Возвращает: (всего заказов, заказов new, общая сумма всех заказов).
    """
    async with AsyncSessionLocal() as session:
        total_res = await session.execute(select(func.count(Order.id)))
        total_orders = total_res.scalar_one() or 0

        new_res = await session.execute(
            select(func.count(Order.id)).where(Order.status == OrderStatus.NEW)
        )
        new_orders = new_res.scalar_one() or 0

        sum_res = await session.execute(
            select(func.coalesce(func.sum(Order.total_price), 0))
        )
        total_amount = sum_res.scalar_one() or 0

        return total_orders, new_orders, total_amount


async def update_order_status(
    order_id: int,
    new_status: str,
) -> Tuple[Order | None, User | None]:
    """
    Обновляет статус заказа и возвращает (order, user), чтобы можно было уведомить клиента.
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
        order.status = new_status

        await session.commit()
        await session.refresh(order)

        return order, user


async def cancel_order_by_user(
    order_id: int,
    telegram_id: int,
) -> Order | None:
    """
    Отмена заказа самим пользователем.
    Разрешаем отмену только для статусов NEW и IN_PROGRESS.
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Order, User)
            .join(User, Order.user_id == User.id)
            .where(
                Order.id == order_id,
                User.telegram_id == telegram_id,
            )
        )
        row = res.one_or_none()
        if row is None:
            return None

        order, _user = row
        if order.status not in (OrderStatus.NEW, OrderStatus.IN_PROGRESS):
            return None

        order.status = OrderStatus.CANCELLED

        await session.commit()
        await session.refresh(order)

        return order

