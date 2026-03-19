from typing import Iterable, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Category, Product


def categories_kb(categories: Iterable[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(
            text=cat.name,
            callback_data=f"cat:{cat.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def products_kb(category_id: int, products: Iterable[Product]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for prod in products:
        builder.button(
            text=f"{prod.name} — {prod.price} ₽",
            callback_data=f"prod:{category_id}:{prod.id}",
        )
    builder.button(
        text="⬅ Назад к категориям",
        callback_data="back:categories",
    )
    builder.adjust(1)
    return builder.as_markup()


def product_card_kb(category_id: int, product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🛒 Купить",
        callback_data=f"buy:{product_id}:{category_id}",
    )
    builder.button(
        text="⬅ Назад к товарам",
        callback_data=f"back:products:{category_id}",
    )
    builder.adjust(1)
    return builder.as_markup()


def cart_kb(product_id: int, quantity: int) -> InlineKeyboardMarkup:
    if quantity < 1:
        quantity = 1
    if quantity > 99:
        quantity = 99

    builder = InlineKeyboardBuilder()
    builder.button(
        text="➖",
        callback_data=f"cart:dec:{product_id}",
    )
    builder.button(
        text=f"{quantity} шт.",
        callback_data="cart:none",
    )
    builder.button(
        text="➕",
        callback_data=f"cart:inc:{product_id}",
    )
    builder.button(
        text="✅ Перейти к оформлению",
        callback_data="cart:checkout",
    )
    builder.button(
        text="✖ Отмена",
        callback_data="cart:cancel",
    )
    builder.adjust(3, 2)
    return builder.as_markup()


def confirm_order_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить заказ",
        callback_data="order:confirm",
    )
    builder.button(
        text="✖ Отмена",
        callback_data="order:cancel",
    )
    builder.adjust(1, 1)
    return builder.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📄 Список заказов",
        callback_data="admin:orders",
    )
    builder.button(
        text="📊 Статистика",
        callback_data="admin:stats",
    )
    builder.adjust(1)
    return builder.as_markup()


def guarantees_link_kb(url: str) -> InlineKeyboardMarkup:
    """
    Клавиатура с одной кнопкой-ссылкой на страницу гарантий.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Открыть гарантии",
        url=url,
    )
    builder.adjust(1)
    return builder.as_markup()


def admin_order_status_kb(order_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура управления статусом заказа для админов.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Взять в работу",
        callback_data=f"admin:set_status:{order_id}:in_progress",
    )
    builder.button(
        text="✔ Выполнено",
        callback_data=f"admin:set_status:{order_id}:done",
    )
    builder.button(
        text="❌ Отменить",
        callback_data=f"admin:set_status:{order_id}:cancelled",
    )
    builder.adjust(1)
    return builder.as_markup()


def user_order_actions_kb(order_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для управления заказом пользователем.
    Сейчас даём только кнопку отмены.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="❌ Отменить заказ",
        callback_data=f"user:cancel_order:{order_id}",
    )
    builder.adjust(1)
    return builder.as_markup()


def order_payment_kb(order_id: int, payment_url: Optional[str] = None) -> InlineKeyboardMarkup:
    """
    Клавиатура экрана оплаты заказа:
    - внешняя ссылка на оплату
    - обновление статуса оплаты из БД
    - отмена заказа
    """
    builder = InlineKeyboardBuilder()
    if payment_url:
        builder.button(
            text="💳 Оплатить",
            url=payment_url,
        )
    builder.button(
        text="🔄 Обновить статус",
        callback_data=f"pay:check:{order_id}",
    )
    builder.button(
        text="❌ Отменить заказ",
        callback_data=f"user:cancel_order:{order_id}",
    )
    builder.adjust(1)
    return builder.as_markup()
