from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_kb() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="🛍 Магазин")],
        [KeyboardButton(text="📋 Мои заказы")],
        [KeyboardButton(text="⭐ Отзывы"), KeyboardButton(text="📜 Гарантии")],
        [KeyboardButton(text="📞 Поддержка")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел меню",
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    buttons = [[KeyboardButton(text="Отмена")]]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Вы можете ввести Supercell ID или нажать Отмена",
    )


def back_to_menu_kb() -> ReplyKeyboardMarkup:
    buttons = [[KeyboardButton(text="В меню")]]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Вернуться в главное меню",
    )

