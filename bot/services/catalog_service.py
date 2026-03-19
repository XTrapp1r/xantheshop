from typing import List, Optional

from sqlalchemy import select

from bot.database.db import AsyncSessionLocal
from bot.database.models import Category, Product


async def get_categories() -> List[Category]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Category)
            .where(Category.name.in_(["Brawl Stars", "Clash Royale"]))
            .order_by(Category.id)
        )
        return list(result.scalars().all())


async def get_active_products_by_category(category_id: int) -> List[Product]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Product)
            .where(
                Product.category_id == category_id,
                Product.is_active.is_(True),
            )
            .order_by(Product.id)
        )
        return list(result.scalars().all())


async def get_active_product(product_id: int) -> Optional[Product]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Product).where(
                Product.id == product_id,
                Product.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

