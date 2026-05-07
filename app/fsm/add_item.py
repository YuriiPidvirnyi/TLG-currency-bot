from aiogram.fsm.state import State, StatesGroup


class AddItem(StatesGroup):
    cabinet = State()
    item = State()        # waiting for catalog choice or "+free-form"
    free_form_name = State()
    qty = State()
    unit = State()
    doctor = State()
    comment = State()
    confirm = State()
