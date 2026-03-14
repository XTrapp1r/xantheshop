from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    choosing_product = State()
    choosing_quantity = State()
    entering_supercell_id = State()
    confirming = State()

