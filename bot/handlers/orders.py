from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.database.models import OrderStatus
from bot.keyboards.inline import (
    user_order_actions_kb,
)
from bot.keyboards.reply import main_menu_kb
from bot.services import order_service
from bot.services.payment_service import (
    apply_paid_order_payment_ui,
    sync_order_payment_from_paypalych_api,
)
from bot.utils.text import format_order_line, human_status

router = Router()


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
        line = (
            f"Заказ №{o.id}\n"
            f"{o.product_name_snapshot} | {o.quantity} шт. | {o.total_price} ₽\n"
            f"Статус: {human_status(o.status)}"
        )
        if (o.payment_status or "").lower() == "paid":
            await message.answer(line)
        else:
            await message.answer(line, reply_markup=user_order_actions_kb(o.id))


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
    
    async_orders = await order_service.get_user_orders_by_telegram_id(
        user.id,
        active_only=False,
    )
    order = next((o for o in async_orders if o.id == order_id), None)
    if order is None:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    payment_status = (order.payment_status or "pending").lower()
    if payment_status == "paid":
        db_order = await order_service.get_order_by_id(order_id)
        if db_order:
            await apply_paid_order_payment_ui(
                callback.bot,
                db_order,
                chat_id=user.telegram_id,
                send_payment_received_line=False,
            )
        await callback.answer("Статус оплаты: Оплачен.", show_alert=True)
        return
    if payment_status == "failed":
        await callback.answer("Статус оплаты: Неуспешно/отменён.", show_alert=True)
        return

    sync_result = await sync_order_payment_from_paypalych_api(order_id, callback.bot)
    if sync_result == "updated":
        await callback.answer("Оплата подтверждена, статус обновлён.", show_alert=True)
        return
    if sync_result == "already_paid":
        await callback.answer("Статус оплаты: Оплачен.", show_alert=True)
        return
    if sync_result == "error":
        await callback.answer(
            "Не удалось проверить оплату. Попробуйте позже или напишите в поддержку.",
            show_alert=True,
        )
        return
    await callback.answer(
        "Оплата в PayPalych ещё не отмечена. Подождите минуту и нажмите снова.",
        show_alert=True,
    )


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

    await callback.message.answer(
        "Оформление заказа отменено.",
        reply_markup=main_menu_kb(),
    )

    await callback.answer("Заказ отменён.")

