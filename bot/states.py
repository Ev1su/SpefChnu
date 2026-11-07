from aiogram.fsm.state import State, StatesGroup


class AppealStates(StatesGroup):
    category = State()
    description = State()
    urgency = State()
    confirm = State()


class JoinStates(StatesGroup):
    full_name = State()
    birth_date = State()
    phone = State()
    group = State()
    instagram = State()
    telegram = State()
    confirm = State()
    edit_field = State()


class AdminReplyStates(StatesGroup):
    waiting = State()
