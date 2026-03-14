from aiogram import F, Router
from aiogram.types import Message

from bot.config import load_config
from bot.keyboards.inline import guarantees_link_kb
from bot.keyboards.reply import main_menu_kb

router = Router()
config = load_config()


@router.message(F.text == "⭐ Отзывы")
async def reviews(message: Message) -> None:
    await message.answer(
        "Отзывы наших клиентов:\n"
        f"{config.REVIEWS_URL}",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "📜 Гарантии")
async def guarantees(message: Message) -> None:
    if not config.GUARANTEES_URL:
        await message.answer(
            "Раздел гарантий временно недоступен. Пожалуйста свяжитесь с поддержкой.",
            reply_markup=main_menu_kb(),
        )
        return

    await message.answer(
        "Перед покупкой пожалуйста ознакомьтесь с условиями работы магазина "
        "и гарантиями выполнения заказов.",
        reply_markup=guarantees_link_kb(config.GUARANTEES_URL),
    )


@router.message(F.text == "📞 Поддержка")
async def support(message: Message) -> None:
    await message.answer(
        "По всем вопросам обращайтесь в поддержку:\n"
        f"{config.SUPPORT_USERNAME}",
        reply_markup=main_menu_kb(),
    )

