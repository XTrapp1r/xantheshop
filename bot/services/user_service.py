from typing import Optional

from sqlalchemy import select

from bot.database.db import AsyncSessionLocal
from bot.database.models import User


async def get_or_create_user(
    telegram_id: int,
    username: Optional[str],
    first_name: Optional[str],
) -> User:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            return user

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

