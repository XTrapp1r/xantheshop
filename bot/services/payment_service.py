from datetime import datetime, timedelta, timezone
import html
import logging

import httpx
from aiogram import Bot
from sqlalchemy import select

from bot.config import load_config
from bot.database.db import AsyncSessionLocal
from bot.database.models import Order, OrderStatus, Product, User

config = load_config()
logger = logging.getLogger(__name__)

CREATE_BILL_URL = "https://pal24.pro/api/v1/bill/create"
CHECK_BILL_URL = "https://pal24.pro/api/v1/bill/status"


async def create_payment_for_order(order: Order) -> Order:
    """
    Совместимость со старым интерфейсом.
    """
    return await create_payment(order)


async def create_payment(order: Order) -> Order:
    """
    Создаёт уникальный bill в PayPalych для заказа.
    """
    if not config.PALLY_API_TOKEN:
        raise RuntimeError("PALLY_API_TOKEN не указан в переменных окружения")
    if not config.PALLY_SHOP_ID:
        raise RuntimeError("PALLY_SHOP_ID не указан в переменных окружения")

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Order).where(Order.id == order.id))
        db_order = res.scalar_one_or_none()
        if db_order is None:
            return order

        if db_order.product_id is None:
            return db_order

        prod_res = await session.execute(
            select(Product).where(Product.id == db_order.product_id)
        )
        product = prod_res.scalar_one_or_none()
        if product is None:
            return db_order

        payload = {
            "amount": db_order.total_price,
            "order_id": str(db_order.id),
            "description": f"Оплата заказа #{db_order.id}",
            "type": "normal",
            "shop_id": config.PALLY_SHOP_ID,
            "currency_in": "RUB",
            "custom": f"order:{db_order.id}",
            "payer_pays_commission": 1,
            "name": db_order.product_name_snapshot,
        }

        data = None
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                CREATE_BILL_URL,
                headers={"Authorization": f"Bearer {config.PALLY_API_TOKEN}"},
                data=payload,  # form-data/x-www-form-urlencoded
            )
            if response.status_code >= 400:
                logger.error(
                    "PayPalych create bill failed: status=%s body=%s",
                    response.status_code,
                    response.text[:500],
                )
                raise RuntimeError("PayPalych вернул ошибку при создании счёта")
            data = response.json()

        success = bool(
            data.get("success")
            or (data.get("data") or {}).get("success")
            or (data.get("result") or {}).get("success")
        )
        if not success:
            logger.error("PayPalych create bill unsuccessful response: %s", data)
            raise RuntimeError("Не удалось создать счёт в PayPalych")

        bill_id = (
            data.get("bill_id")
            or data.get("id")
            or (data.get("data") or {}).get("bill_id")
            or (data.get("result") or {}).get("bill_id")
        )
        pay_url = (
            data.get("link_page_url")
            or data.get("pay_url")
            or data.get("url")
            or (data.get("data") or {}).get("link_page_url")
            or (data.get("result") or {}).get("link_page_url")
        )
        if not bill_id or not pay_url:
            logger.error("PayPalych response missing bill_id or link_page_url: %s", data)
            raise RuntimeError("PayPalych не вернул bill_id/link_page_url")

        db_order.payment_provider = "paypalych"
        db_order.payment_status = "pending"
        db_order.payment_id = str(bill_id)
        # Только ссылка со счёта PayPalych: оплата должна идти по этому bill,
        # иначе webhook по InvId не привяжется к оплате (статические pally.info в каталоге — другой поток).
        db_order.payment_url = str(pay_url)

        await session.commit()
        await session.refresh(db_order)
        return db_order


async def get_payment_status(order_id: int) -> str:
    """
    Возвращает текущий status оплаты из БД.
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Order).where(Order.id == order_id))
        db_order = res.scalar_one_or_none()
        if db_order is None:
            return "unknown"
        return db_order.payment_status or "pending"


def get_result_url() -> str | None:
    if not config.PUBLIC_BASE_URL:
        return None
    return f"{config.PUBLIC_BASE_URL}/webhooks/paypalych/result"


def format_order_payment_screen_paid_html(order: Order) -> str:
    """Текст сообщения со счётом после оплаты (без кнопок оплаты/отмены)."""
    return (
        "✅ Ваш заказ создан\n\n"
        f"Номер заказа: <b>#{order.id}</b>\n"
        f"Товар: <b>{html.escape(order.product_name_snapshot)}</b>\n"
        f"Количество: <b>{order.quantity}</b>\n"
        f"Сумма: <b>{order.total_price} ₽</b>\n\n"
        "<b>✅ Оплачено</b>"
    )


async def apply_paid_order_payment_ui(
    bot: Bot,
    order: Order,
    *,
    chat_id: int,
    send_payment_received_line: bool = True,
) -> None:
    """
    Убирает inline-кнопки с карточки оплаты и показывает главное меню внизу.
    """
    from bot.keyboards.reply import main_menu_kb

    if order.payment_telegram_message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=order.payment_telegram_message_id,
                text=format_order_payment_screen_paid_html(order),
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            logger.exception(
                "Не удалось обновить сообщение оплаты order_id=%s", order.id
            )

    try:
        if send_payment_received_line:
            await bot.send_message(
                chat_id=chat_id,
                text="✅ Оплата получена. Ваш заказ передан в обработку.",
                reply_markup=main_menu_kb(),
            )
        elif not order.payment_telegram_message_id:
            await bot.send_message(
                chat_id=chat_id,
                text="✅ Оплата уже подтверждена.",
                reply_markup=main_menu_kb(),
            )
    except Exception:
        logger.exception("Не удалось отправить главное меню order_id=%s", order.id)


async def notify_order_paid_and_admins(order: Order, user: User, bot: Bot) -> None:
    """Уведомления после подтверждённой оплаты (webhook или sync API)."""
    await apply_paid_order_payment_ui(
        bot,
        order,
        chat_id=user.telegram_id,
        send_payment_received_line=True,
    )

    from bot.keyboards.inline import admin_order_status_kb

    admin_text = (
        "🔥 Новый оплаченный заказ\n\n"
        f"ID: {order.id}\n"
        f"Товар: {order.product_name_snapshot}\n"
        f"Количество: {order.quantity}\n"
        f"Сумма: {order.total_price} ₽\n"
        f"Supercell ID: {order.supercell_id}\n"
        f"Юзер: @{user.username or 'без_username'} / Telegram ID: {user.telegram_id}\n\n"
        "Статус: Ожидает выполнения"
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                reply_markup=admin_order_status_kb(order.id, order.status),
            )
        except Exception:
            logger.exception("Не удалось отправить уведомление админу admin_id=%s", admin_id)


async def finalize_order_as_paid(
    order_id: int,
    bot: Bot,
    *,
    trs_id: str | None = None,
) -> bool:
    """
    Переводит заказ в paid/PAID и шлёт уведомления. Идемпотентно.
    Возвращает True, если статус был обновлён сейчас.
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Order, User)
            .join(User, Order.user_id == User.id)
            .where(Order.id == order_id)
        )
        row = res.one_or_none()
        if row is None:
            return False
        order, user = row
        if order.payment_status == "paid":
            return False
        order.payment_status = "paid"
        order.status = OrderStatus.PAID
        if trs_id:
            order.payment_id = trs_id
        await session.commit()
        await session.refresh(order)
    await notify_order_paid_and_admins(order, user, bot)
    return True


def _bill_payload_is_paid(data: dict) -> bool:
    raw = (
        data.get("status")
        or (data.get("data") or {}).get("status")
        or (data.get("result") or {}).get("status")
        or data.get("bill_status")
        or ""
    )
    s = str(raw).lower()
    if s in ("paid", "success", "completed", "ok"):
        return True
    return "paid" in s or "success" in s


async def sync_order_payment_from_paypalych_api(order_id: int, bot: Bot) -> str:
    """
    Подтягивает статус счёта из PayPalych API (если webhook не дошёл).
    Возвращает: already_paid | updated | pending | error | not_found
    """
    if not config.PALLY_API_TOKEN:
        return "error"

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Order, User)
            .join(User, Order.user_id == User.id)
            .where(Order.id == order_id)
        )
        row = res.one_or_none()
        if row is None:
            return "not_found"
        order, _user = row
        if order.payment_status == "paid":
            return "already_paid"
        if (order.payment_status or "") == "failed":
            return "pending"
        if order.payment_provider != "paypalych" or not order.payment_id:
            return "pending"

        bill_id = str(order.payment_id).strip()

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                CHECK_BILL_URL,
                headers={"Authorization": f"Bearer {config.PALLY_API_TOKEN}"},
                params={"bill_id": bill_id},
            )
            if response.status_code >= 400:
                logger.warning(
                    "PayPalych bill/status HTTP %s: %s",
                    response.status_code,
                    response.text[:400],
                )
                return "error"
            data = response.json()
    except Exception:
        logger.exception("PayPalych bill/status request failed order_id=%s", order_id)
        return "error"

    if not _bill_payload_is_paid(data):
        return "pending"

    trs_id = None
    for key in ("TrsId", "trs_id", "transaction_id"):
        v = data.get(key) or (data.get("data") or {}).get(key)
        if v:
            trs_id = str(v).strip()
            break

    updated = await finalize_order_as_paid(order_id, bot, trs_id=trs_id)
    return "updated" if updated else "already_paid"


async def process_paypalych_postback(payload: dict, bot: Bot) -> str:
    """
    Обрабатывает postback от PayPalych. Идемпотентно.
    """
    status = str(payload.get("Status", "")).upper()
    inv_id_raw = str(payload.get("InvId", "")).strip()
    trs_id = str(payload.get("TrsId", "")).strip() or None
    custom = str(payload.get("custom", "")).strip()

    order_id: int | None = None
    if inv_id_raw.isdigit():
        order_id = int(inv_id_raw)
    elif custom.startswith("order:") and custom.split(":", 1)[1].isdigit():
        order_id = int(custom.split(":", 1)[1])

    if order_id is None:
        logger.warning("PayPalych postback: invalid order id payload=%s", payload)
        return "ok"

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Order, User)
            .join(User, Order.user_id == User.id)
            .where(Order.id == order_id)
        )
        row = res.one_or_none()
        if row is None:
            logger.warning("PayPalych postback: order not found order_id=%s", order_id)
            return "ok"

        order, user = row
        if order.payment_status == "paid":
            # Повторный postback SUCCESS/FAIL: не меняем статус и не шлём уведомления снова.
            return "ok"

        if status == "SUCCESS":
            await finalize_order_as_paid(order.id, bot, trs_id=trs_id)
            return "ok"

        if status == "FAIL":
            # Повторный FAIL: не дублируем уведомления.
            if order.payment_status == "failed" and order.status == OrderStatus.CANCELLED:
                return "ok"
            order.payment_status = "failed"
            order.status = OrderStatus.CANCELLED
            await session.commit()
            await session.refresh(order)
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text="❌ Оплата не прошла. Попробуйте снова или оформите новый заказ.",
                )
            except Exception:
                logger.exception("Не удалось отправить FAIL уведомление пользователю order_id=%s", order.id)
            return "ok"

        logger.info("PayPalych postback ignored: status=%s payload=%s", status, payload)
        return "ok"


async def auto_cancel_expired_unpaid_orders() -> int:
    """
    Отменяет заказы старше 30 минут без подтверждённой оплаты.
    """
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(minutes=30)

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Order).where(
                Order.status == OrderStatus.NEW,
            )
        )
        orders = list(res.scalars().all())
        updated = 0
        for order in orders:
            created = order.created_at
            if created is None:
                continue
            created_utc = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
            if created_utc < threshold and (order.payment_status or "pending") == "pending":
                order.status = OrderStatus.CANCELLED
                order.payment_status = "failed"
                updated += 1

        if updated:
            await session.commit()
        return updated


async def cancel_order(order_id: int) -> Order | None:
    """
    Отмена заказа вместе с оплатой.
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Order).where(Order.id == order_id))
        order = res.scalar_one_or_none()
        if order is None:
            return None

        order.status = OrderStatus.CANCELLED
        order.payment_status = "failed"

        await session.commit()
        await session.refresh(order)

        return order

