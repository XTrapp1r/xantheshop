from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardRemove

from bot.keyboards.reply import main_menu_kb
from bot.services.user_service import get_or_create_user

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    if user is None:
        await message.answer(
            "Привет! Я магазин внутриигровых услуг.\n"
            "Пожалуйста, напишите мне ещё раз, чтобы я смог сохранить ваш профиль."
        )
        return

    await get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    # Сброс старой reply-клавиатуры (иначе Telegram может оставить лишние ряды,
    # например удалённую кнопку «Оферта», пока не придёт Remove).
    m = await message.answer(".", reply_markup=ReplyKeyboardRemove())
    try:
        await message.bot.delete_message(message.chat.id, m.message_id)
    except Exception:
        pass

    await message.answer(
        "<b>Привет! 👋</b>\n\n"
        "Я бот-магазин внутриигровых услуг — здесь можно спокойно оформить заказ.\n\n"
        "👉 <b>Разделы магазина</b> — на клавиатуре <u>внизу экрана</u> (Магазин, Заказы, Отзывы…).\n\n"
        "───────────────\n"
        "✅ <b>Верификация Pally</b>\n"
        "<i>Магазин в доверенном списке Pally — платежи и сделки проходят через проверенную экосистему.</i>\n"
        "───────────────",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )

