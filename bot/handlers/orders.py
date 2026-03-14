from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
import contextlib

from bot.config import load_config
from bot.database.models import OrderStatus
from bot.keyboards.inline import fake_payment_kb, order_payment_kb, user_order_actions_kb
from bot.keyboards.reply import main_menu_kb
from bot.services import order_service, payment_service
from bot.utils.text import format_order_line, human_status

router = Router()
config = load_config()


@router.message(F.text == "📋 Мои заказы")
async def my_orders(message: Message) -> None:
    user = message.from_user
    if user is None:
        await message.answer(
            "Не удалось определить пользователя. Попробуйте ещё раз.",
            reply_markup=main_menu_kb(),
        )
        return

    orders = await order_service.get_user_orders_by_telegram_id(
        user.id,
        active_only=True,
    )
    if not orders:
        await message.answer(
            "У вас пока нет активных заказов.",
            reply_markup=main_menu_kb(),
        )
        return

    lines = [
        "📋 <b>Ваши заказы</b>:\n",
    ]
    for o in orders:
        lines.append(
            format_order_line(
                order_id=o.id,
                product_name=o.product_name_snapshot,
                quantity=o.quantity,
                total=o.total_price,
                status=o.status,
            )
        )

    # Сводная табличка
    await message.answer(
        "\n".join(lines),
        reply_markup=main_menu_kb(),
    )

    # Отдельные карточки заказов с кнопкой отмены (только для статусов, где отмена ещё имеет смысл)
    for o in orders:
        if o.status not in (OrderStatus.NEW, OrderStatus.IN_PROGRESS):
            continue
        await message.answer(
            f"Заказ №{o.id}\n"
            f"{o.product_name_snapshot} | {o.quantity} шт. | {o.total_price} ₽\n"
            f"Статус: {human_status(o.status)}",
            reply_markup=user_order_actions_kb(o.id),
        )


@router.callback_query(F.data.startswith("pay:start:"))
async def start_payment(callback: CallbackQuery) -> None:
    user = callback.from_user
    if user is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    try:
        _, _, order_id_str = callback.data.split(":", maxsplit=2)
        order_id = int(order_id_str)
    except Exception:
        await callback.answer("Некорректные данные заказа.", show_alert=True)
        return

    if config.PAYMENT_MODE == "fake":
        await callback.message.answer(
            "Сейчас включён тестовый режим оплаты.\n"
            "Реальная платёжная система будет подключена позже.",
            reply_markup=fake_payment_kb(order_id),
        )
        await callback.answer()
        return

    await callback.answer("Режим оплаты пока не настроен.", show_alert=True)


@router.callback_query(F.data.startswith("pay:check:"))
async def check_payment(callback: CallbackQuery) -> None:
    user = callback.from_user
    if user is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    try:
        _, _, order_id_str = callback.data.split(":", maxsplit=2)
        order_id = int(order_id_str)
    except Exception:
        await callback.answer("Некорректные данные заказа.", show_alert=True)
        return

    # В fake-режиме статусы берём из полей заказа
    async_orders = await order_service.get_user_orders_by_telegram_id(user.id, active_only=False)
    order = next((o for o in async_orders if o.id == order_id), None)
    if order is None:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    status = await payment_service.get_payment_status(order)
    if status == "paid":
        await callback.answer("Оплата уже подтверждена, заказ передан в обработку.", show_alert=True)
    elif status == "pending":
        await callback.answer(
            "Оплата пока не подтверждена.\n"
            "В тестовом режиме используйте кнопку «Тестово подтвердить оплату».",
            show_alert=True,
        )
    elif status == "cancelled":
        await callback.answer("Оплата по этому заказу была отменена.", show_alert=True)
    else:
        await callback.answer(f"Статус оплаты: {status}", show_alert=True)


@router.callback_query(F.data.startswith("pay:fake_confirm:"))
async def fake_confirm_payment(callback: CallbackQuery) -> None:
    user = callback.from_user
    if user is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    try:
        _, _, order_id_str = callback.data.split(":", maxsplit=2)
        order_id = int(order_id_str)
    except Exception:
        await callback.answer("Некорректные данные заказа.", show_alert=True)
        return

    order, client = await payment_service.confirm_fake_payment(order_id)
    if order is None or client is None:
        await callback.answer("Не удалось подтвердить оплату.", show_alert=True)
        return

    # Убираем старые кнопки fake-оплаты
    with contextlib.suppress(Exception):
        await callback.message.edit_reply_markup(reply_markup=None)

    # Сообщение пользователю (и возврат в главное меню)
    await callback.message.answer(
        "Оплата успешно подтверждена. Ваш заказ передан в обработку.",
        reply_markup=main_menu_kb(),
    )

    # Уведомление админам
    text = (
        f"💳 Оплачен новый заказ №{order.id}\n\n"
        f"Товар: {order.product_name_snapshot}\n"
        f"Количество: {order.quantity}\n"
        f"Сумма: {order.total_price} ₽\n"
        f"Supercell ID: {order.supercell_id}\n\n"
        f"Клиент: @{client.username or 'без username'} (ID: {client.telegram_id})\n"
        f"Статус: Ожидает выполнения"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await callback.message.bot.send_message(
                chat_id=admin_id,
                text=text,
            )
        except Exception:
            continue

    await callback.answer("Оплата подтверждена.")


@router.callback_query(F.data.startswith("user:cancel_order:"))
async def user_cancel_order(callback: CallbackQuery) -> None:
    user = callback.from_user
    if user is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    try:
        _, _, order_id_str = callback.data.split(":", maxsplit=2)
        order_id = int(order_id_str)
    except Exception:
        await callback.answer("Некорректные данные заказа.", show_alert=True)
        return

    order = await order_service.cancel_order_by_user(order_id, user.id)
    if order is None:
        await callback.answer(
            "Этот заказ нельзя отменить (возможно, он уже обработан или не принадлежит вам).",
            show_alert=True,
        )
        return

    # Обновляем карточку заказа
    await callback.message.edit_text(
        f"Заказ №{order.id}\n"
        f"{order.product_name_snapshot} | {order.quantity} шт. | {order.total_price} ₽\n"
        f"Статус: {human_status(order.status)}",
    )

    await callback.answer("Заказ отменён.")

