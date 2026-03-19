from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.models import Product
from bot.keyboards.inline import (
    categories_kb,
    confirm_order_kb,
    order_payment_kb,
    product_card_kb,
    products_kb,
)
from bot.keyboards.reply import cancel_kb, main_menu_kb
from bot.services import catalog_service, order_service, payment_service
from bot.states.order_states import OrderStates

router = Router()


@router.message(F.text == "🛍 Магазин")
async def open_catalog(message: Message) -> None:
    categories = await catalog_service.get_categories()
    if not categories:
        await message.answer(
            "Магазин сейчас пуст. Мы уже работаем над наполнением 😊",
            reply_markup=main_menu_kb(),
        )
        return

    await message.answer(
        "Выберите игру:",
        reply_markup=categories_kb(categories),
    )


@router.callback_query(F.data == "back:categories")
async def back_to_categories(callback: CallbackQuery) -> None:
    categories = await catalog_service.get_categories()
    if not categories:
        await callback.message.edit_text("Магазин сейчас пуст.")
        await callback.answer()
        return

    await callback.message.edit_text(
        "Выберите игру:",
        reply_markup=categories_kb(categories),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat:"))
async def open_category(callback: CallbackQuery) -> None:
    try:
        _, cat_id_str = callback.data.split(":", maxsplit=1)
        category_id = int(cat_id_str)
    except Exception:
        await callback.answer("Неверные данные категории.", show_alert=True)
        return

    products = await catalog_service.get_active_products_by_category(category_id)
    if not products:
        await callback.answer("В этой категории пока нет доступных товаров.", show_alert=True)
        return

    await callback.message.edit_text(
        "Выберите товар:",
        reply_markup=products_kb(category_id, products),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("back:products:"))
async def back_to_products(callback: CallbackQuery) -> None:
    try:
        _, _, cat_id_str = callback.data.split(":", maxsplit=2)
        category_id = int(cat_id_str)
    except Exception:
        await callback.answer("Неверные данные категории.", show_alert=True)
        return

    products = await catalog_service.get_active_products_by_category(category_id)
    if not products:
        await callback.answer("В этой категории пока нет доступных товаров.", show_alert=True)
        return

    await callback.message.edit_text(
        "Выберите товар:",
        reply_markup=products_kb(category_id, products),
    )
    await callback.answer()


async def _send_product_card(
    message: Message,
    product: Product,
    category_id: int,
) -> None:
    text = (
        f"<b>{product.name}</b>\n"
        f"Цена: <b>{product.price} ₽</b>\n\n"
        f"{product.description or 'Описание скоро появится.'}"
    )

    if product.image_url:
        await message.answer_photo(
            photo=product.image_url,
            caption=text,
            reply_markup=product_card_kb(category_id, product.id),
        )
    else:
        await message.answer(
            text,
            reply_markup=product_card_kb(category_id, product.id),
        )


@router.callback_query(F.data.startswith("prod:"))
async def open_product(callback: CallbackQuery) -> None:
    try:
        _, cat_id_str, prod_id_str = callback.data.split(":", maxsplit=2)
        category_id = int(cat_id_str)
        product_id = int(prod_id_str)
    except Exception:
        await callback.answer("Неверные данные товара.", show_alert=True)
        return

    product = await catalog_service.get_active_product(product_id)
    if not product:
        await callback.answer("Товар недоступен или отключён.", show_alert=True)
        return

    await _send_product_card(callback.message, product, category_id)
    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def start_order(callback: CallbackQuery, state: FSMContext) -> None:
    user = callback.from_user
    if user is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    try:
        _, prod_id_str, cat_id_str = callback.data.split(":", maxsplit=2)
        product_id = int(prod_id_str)
        category_id = int(cat_id_str)
    except Exception:
        await callback.answer("Неверные данные товара.", show_alert=True)
        return

    product = await catalog_service.get_active_product(product_id)
    if not product:
        await callback.answer("Товар недоступен или отключён.", show_alert=True)
        return

    await state.update_data(
        product_id=product.id,
        category_id=category_id,
        quantity=1,
    )
    await _go_to_supercell_input(callback, state)


async def _go_to_supercell_input(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderStates.entering_supercell_id)
    await callback.message.answer(
        "Отлично! Теперь укажите ваш <b>Supercell ID</b>.\n\n"
        "📌 <b>Как его найти?</b>\n"
        "Откройте игру → Настройки → Раздел Supercell ID →\n"
        "Скопируйте ваш ID, привязанный к аккаунту.\n\n"
        "Отправьте его мне одним сообщением.\n"
        "Если передумали, нажмите «Отмена».",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(OrderStates.entering_supercell_id, F.text.casefold() == "отмена")
async def cancel_supercell_input(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Оформление заказа отменено.",
        reply_markup=main_menu_kb(),
    )


@router.message(OrderStates.entering_supercell_id)
async def process_supercell_id(message: Message, state: FSMContext) -> None:
    supercell_id = (message.text or "").strip()
    if not supercell_id or len(supercell_id) < 3:
        await message.answer(
            "Похоже, что это не похоже на реальный Supercell ID.\n"
            "Пожалуйста, отправьте корректный ID или нажмите «Отмена».",
            reply_markup=cancel_kb(),
        )
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    quantity = int(data.get("quantity", 1))

    if not product_id:
        await state.clear()
        await message.answer(
            "Что-то пошло не так при оформлении заказа. Попробуйте начать заново.",
            reply_markup=main_menu_kb(),
        )
        return

    product = await catalog_service.get_active_product(product_id)
    if not product:
        await state.clear()
        await message.answer(
            "Товар недоступен или отключён. Попробуйте выбрать другой.",
            reply_markup=main_menu_kb(),
        )
        return

    total = product.price * quantity

    await state.update_data(supercell_id=supercell_id)
    await state.set_state(OrderStates.confirming)

    text = (
        "✅ Проверьте данные заказа:\n\n"
        f"Товар: <b>{product.name}</b>\n"
        f"Цена: <b>{product.price} ₽</b>\n"
        f"Количество: <b>{quantity}</b>\n"
        f"Итого: <b>{total} ₽</b>\n"
        f"Supercell ID: <b>{supercell_id}</b>\n\n"
        "Если всё верно — подтвердите заказ.\n"
        "Если что-то не так — можно отменить и оформить заново."
    )

    await message.answer(
        text,
        reply_markup=confirm_order_kb(),
    )


@router.callback_query(OrderStates.confirming, F.data == "order:cancel")
async def cancel_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer(
        "Оформление заказа отменено.",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(OrderStates.confirming, F.data == "order:confirm")
async def confirm_order(callback: CallbackQuery, state: FSMContext) -> None:
    user = callback.from_user
    if user is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    quantity = int(data.get("quantity", 1))
    supercell_id = data.get("supercell_id")

    if not all([product_id, quantity, supercell_id]):
        await state.clear()
        await callback.message.answer(
            "Данные заказа повреждены. Попробуйте оформить заново.",
            reply_markup=main_menu_kb(),
        )
        await callback.answer()
        return

    try:
        order = await order_service.create_order(
            telegram_id=user.id,
            product_id=int(product_id),
            quantity=quantity,
            supercell_id=str(supercell_id),
        )
    except ValueError as e:
        await state.clear()
        await callback.message.answer(
            f"Не удалось создать заказ: {e}",
            reply_markup=main_menu_kb(),
        )
        await callback.answer()
        return

    # создаём платёж (без API, только ссылка и служебные поля)
    order = await payment_service.create_payment_for_order(order)

    await state.clear()

    payment_link = order.payment_url or ""

    text = (
        "✅ Ваш заказ создан\n\n"
        "💸 Оплатите по ссылке ниже (кнопка «Оплатить»).\n"
        "После оплаты нажмите:\n"
        "🔄 Проверить оплату"
    )

    await callback.message.answer(
        text,
        reply_markup=order_payment_kb(order.id, payment_link),
    )

    await callback.answer("Заказ успешно создан, ожидает оплаты.")

