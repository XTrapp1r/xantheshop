from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.config import load_config
from bot.database.models import OrderStatus
from bot.keyboards.inline import admin_menu_kb, admin_order_status_kb
from bot.services import order_service
from bot.utils.text import human_status

router = Router()
config = load_config()


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


@router.message(Command("admin"))
async def admin_menu(message: Message) -> None:
    user = message.from_user
    if user is None or not _is_admin(user.id):
        await message.answer("У вас нет доступа к админ-панели.")
        return

    await message.answer(
        "👑 Админ-панель\n\n"
        "Выберите действие:",
        reply_markup=admin_menu_kb(),
    )


@router.callback_query(lambda c: c.data in ("admin:orders", "admin:stats"))
async def admin_actions(callback: CallbackQuery) -> None:
    user = callback.from_user
    if user is None or not _is_admin(user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    if callback.data == "admin:orders":
        await _admin_last_orders(callback)
    elif callback.data == "admin:stats":
        await _admin_stats(callback)


async def _admin_last_orders(callback: CallbackQuery) -> None:
    # Показываем только активные заказы (ещё не выполненные и не отменённые)
    orders = await order_service.get_active_orders()
    if not orders:
        await callback.message.edit_text("Заказов пока нет.")
        await callback.answer()
        return

    lines = ["📄 <b>Активные заказы</b>:\n"]
    for o in orders:
        lines.append(
            f"#{o.id} | {o.product_name_snapshot} | {o.quantity} шт. | "
            f"{o.total_price} ₽ | {human_status(o.status)}"
        )

    await callback.message.edit_text("\n".join(lines))

    # Дополнительно отправляем отдельные сообщения с кнопками управления
    # Только для активных заказов (new / paid / in_progress)
    for o in orders:
        if o.status not in (
            OrderStatus.NEW,
            OrderStatus.PAID,
            OrderStatus.IN_PROGRESS,
        ):
            continue

        await callback.message.answer(
            f"Заказ #{o.id}\n"
            f"{o.product_name_snapshot} | {o.quantity} шт. | {o.total_price} ₽\n"
            f"Статус: {human_status(o.status)}",
            reply_markup=admin_order_status_kb(o.id, o.status),
        )

    await callback.answer()


async def _admin_stats(callback: CallbackQuery) -> None:
    total_orders, new_orders, total_amount = await order_service.get_stats()

    lines = [
        "📊 <b>Статистика заказов</b>\n",
        f"Всего заказов: <b>{total_orders}</b>",
        f"Новых заказов: <b>{new_orders}</b>",
        f"Общая сумма всех заказов: <b>{total_amount} ₽</b>",
        "",
        f"Статус по умолчанию: {human_status(OrderStatus.NEW)}",
    ]

    await callback.message.edit_text("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:set_status:"))
async def admin_set_status(callback: CallbackQuery) -> None:
    user = callback.from_user
    if user is None or not _is_admin(user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    try:
        _, _, order_id_str, status = callback.data.split(":", maxsplit=3)
        order_id = int(order_id_str)
    except Exception:
        await callback.answer("Некорректные данные заказа.", show_alert=True)
        return

    allowed_statuses = {
        "in_progress": OrderStatus.IN_PROGRESS,
        "done": OrderStatus.DONE,
        "cancelled": OrderStatus.CANCELLED,
    }
    if status not in allowed_statuses:
        await callback.answer("Недопустимый статус.", show_alert=True)
        return

    db_status = allowed_statuses[status]

    existing = await order_service.get_order_by_id(order_id)
    if existing is None:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    if existing.status == db_status:
        await callback.message.edit_text(
            f"Заказ #{existing.id}\n"
            f"{existing.product_name_snapshot} | {existing.quantity} шт. | {existing.total_price} ₽\n"
            f"Статус: {human_status(existing.status)}",
            reply_markup=admin_order_status_kb(existing.id, existing.status),
        )
        await callback.answer("Статус уже установлен.")
        return

    if existing.status in (OrderStatus.DONE, OrderStatus.CANCELLED):
        await callback.message.edit_text(
            f"Заказ #{existing.id}\n"
            f"{existing.product_name_snapshot} | {existing.quantity} шт. | {existing.total_price} ₽\n"
            f"Статус: {human_status(existing.status)}",
            reply_markup=None,
        )
        await callback.answer("Заказ уже завершён.", show_alert=True)
        return

    order, client = await order_service.update_order_status(order_id, db_status)
    if order is None or client is None:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    # Обновляем текст под кнопками
    await callback.message.edit_text(
        f"Заказ #{order.id}\n"
        f"{order.product_name_snapshot} | {order.quantity} шт. | {order.total_price} ₽\n"
        f"Статус: {human_status(order.status)}",
        reply_markup=admin_order_status_kb(order.id, order.status),
    )

    # Уведомляем клиента
    text_for_client: str
    if db_status == OrderStatus.IN_PROGRESS:
        text_for_client = (
            f"Ваш заказ №{order.id} взят в работу."
        )
    elif db_status == OrderStatus.DONE:
        text_for_client = (
            f"Ваш заказ №{order.id} выполнен. Спасибо за покупку!"
        )
    elif db_status == OrderStatus.CANCELLED:
        text_for_client = (
            f"Ваш заказ №{order.id} был отменён. Если у вас есть вопросы, "
            f"обратитесь в поддержку."
        )
    else:
        text_for_client = f"Статус вашего заказа №{order.id} обновлён: {human_status(order.status)}"

    try:
        await callback.message.bot.send_message(
            chat_id=client.telegram_id,
            text=text_for_client,
        )
    except Exception:
        # Если не удалось уведомить клиента (например, бот в бане) — просто игнорируем
        pass

    await callback.answer("Статус заказа обновлён.")

