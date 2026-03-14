from bot.database.models import OrderStatus


STATUS_HUMAN = {
    OrderStatus.NEW: "Новый",
    OrderStatus.PAID: "Оплачен",
    OrderStatus.IN_PROGRESS: "В работе",
    OrderStatus.DONE: "Выполнен",
    OrderStatus.CANCELLED: "Отменён",
}


def human_status(status: str) -> str:
    return STATUS_HUMAN.get(status, status)


def format_order_line(order_id: int, product_name: str, quantity: int, total: int, status: str) -> str:
    return f"№{order_id} | {product_name} | {quantity} шт. | {total} ₽ | {human_status(status)}"

