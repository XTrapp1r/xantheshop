from sqlalchemy import select

from .db import AsyncSessionLocal
from .models import Category, Product


async def _get_or_create_category(session, name: str) -> Category:
    res = await session.execute(select(Category).where(Category.name == name))
    cat = res.scalar_one_or_none()
    if cat:
        return cat
    cat = Category(name=name)
    session.add(cat)
    await session.flush()
    return cat


async def _get_product_by_name(session, category_id: int, name: str) -> Product | None:
    res = await session.execute(
        select(Product).where(
            Product.category_id == category_id,
            Product.name == name,
        )
    )
    return res.scalar_one_or_none()


async def seed_initial_data() -> None:
    """
    Заполнение БД тестовыми данными и мягкое обновление ключевых товаров.
    """
    async with AsyncSessionLocal() as session:
        # Категории
        brawl = await _get_or_create_category(session, "Brawl Stars")
        royale = await _get_or_create_category(session, "Clash Royale")
        coc = await _get_or_create_category(session, "Clash of Clans")

        # Brawl Stars: обновляем или создаём нужные товары
        brawl_products_spec = [
            (
                "Brawl Pass",
                790,
                "Стандартный боевой пропуск для Brawl Stars.",
                "https://pally.info/transfer/w7eoaXNQmp",
            ),
            (
                "Brawl Pass Plus",
                990,
                "Расширенный боевой пропуск с дополнительными наградами.",
                "https://pally.info/transfer/rmdWAxBJvV",
            ),
        ]
        for name, price, desc, payment_url in brawl_products_spec:
            existing = await _get_product_by_name(session, brawl.id, name)
            if existing:
                existing.price = price
                existing.description = desc
                existing.is_active = True
                existing.payment_url = payment_url
            else:
                session.add(
                    Product(
                        category_id=brawl.id,
                        name=name,
                        description=desc,
                        price=price,
                        image_url=None,
                        is_active=True,
                        payment_url=payment_url,
                    )
                )

        # Clash Royale: скрываем все товары из витрины
        royale_products_spec = []
        for name, price, desc, payment_url in royale_products_spec:
            existing = await _get_product_by_name(session, royale.id, name)
            if existing:
                existing.price = price
                existing.description = desc
                existing.is_active = True
                existing.payment_url = payment_url
            else:
                session.add(
                    Product(
                        category_id=royale.id,
                        name=name,
                        description=desc,
                        price=price,
                        image_url=None,
                        is_active=True,
                        payment_url=payment_url,
                    )
                )

        # Clash of Clans: создаём базовые товары, если их ещё нет
        # Clash of Clans: пока не используем в витрине — оставляем категорию пустой

        # Скрываем устаревшие товары (старые названия/цены/ссылки), не входящие в актуальный список
        brawl_allowed = {name for name, *_ in brawl_products_spec}
        royale_allowed = {name for name, *_ in royale_products_spec}
        for cat_id, allowed in (
            (brawl.id, brawl_allowed),
            (royale.id, royale_allowed),
        ):
            res = await session.execute(
                select(Product).where(Product.category_id == cat_id)
            )
            for prod in res.scalars().all():
                if prod.name not in allowed:
                    prod.is_active = False

        await session.commit()
