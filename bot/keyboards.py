from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.callbacks import (
    AboutCB,
    AdminCardCB,
    AdminListCB,
    AppealActionCB,
    AppealIdentityCB,
    AppealStatusCB,
    JoinActionCB,
    JoinStatusCB,
)


def main_menu(admin: bool = False) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    for text in ("📝 Подати анонімне звернення", "📂 Мої звернення", "👥 Про нас", "✍️ Приєднатися до відділу", "📞 Контакти"):
        b.button(text=text)
    if admin:
        b.button(text="📋 Звернення")
        b.button(text="📋 Анкети")
        b.button(text="📊 Статистика")
    b.adjust(2, 2, 2, 2 if admin else 1)
    return b.as_markup(resize_keyboard=True)


def appeal_categories() -> InlineKeyboardMarkup:
    categories = ("Академічні питання", "Стипендії та фінанси", "Гуртожиток", "Булінг, дискримінація, цькування", "Порушення прав студента", "Інше")
    b = InlineKeyboardBuilder()
    for value in categories:
        b.button(text=value, callback_data=f"cat:{value}")
    b.adjust(1)
    return b.as_markup()


def appeal_done_cancel() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Готово", callback_data="appeal_done")
    b.button(text="❌ Скасувати", callback_data="cancel_action")
    b.adjust(2)
    return b.as_markup()


def appeal_confirm_keyboard(share_username: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=("☑️ Передати @username" if share_username else "☐ Передати @username"),
        callback_data=AppealIdentityCB(share_username=not share_username),
    )
    b.button(text="✅ Надіслати", callback_data="appeal_submit")
    b.button(text="❌ Скасувати", callback_data="cancel_action")
    b.adjust(1)
    return b.as_markup()


def appeal_admin_keyboard(item_id: int, status: str, notes: str = "") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    labels = {"new":"🆕 нова", "working":"🔄 в роботі", "resolved":"✅ вирішено", "closed":"❌ закрито"}
    for value, label in labels.items():
        b.button(text=("✓ " + label) if value == status else label, callback_data=AppealStatusCB(appeal_id=item_id, status=value))
    b.button(text="💬 Відповісти", callback_data=AppealActionCB(appeal_id=item_id, action="reply"))
    b.button(text="🙋 Беру в роботу", callback_data=AppealActionCB(appeal_id=item_id, action="take"))
    b.adjust(2, 2, 2)
    return b.as_markup()


def join_status_keyboard(item_id: int, status: str = "new") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    labels = {"new":"🆕 нова", "review":"👀 розглядається", "accepted":"✅ прийнято", "rejected":"❌ відхилено"}
    for value, label in labels.items():
        b.button(text=("✓ " + label) if value == status else label, callback_data=JoinStatusCB(application_id=item_id, status=value))
    b.button(text="🙋 Беру в роботу", callback_data=JoinActionCB(application_id=item_id, action="take"))
    b.adjust(2, 2, 1)
    return b.as_markup()


def back_cancel() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text="⬅️ Назад")
    b.button(text="❌ Скасувати")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)


def phone_keyboard() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text="📱 Поділитися номером", request_contact=True)
    b.button(text="⬅️ Назад")
    b.row(KeyboardButton(text="❌ Скасувати"))
    return b.as_markup(resize_keyboard=True)


def skip_back_cancel(skip_text: str | None = None) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    if skip_text:
        b.button(text=skip_text)
    b.button(text="⬅️ Назад")
    b.button(text="❌ Скасувати")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)


def hours_keyboard() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    for value in (2, 4, 6, 8, 10):
        b.button(text=str(value))
    b.button(text="⬅️ Назад")
    b.button(text="❌ Скасувати")
    b.adjust(5, 2)
    return b.as_markup(resize_keyboard=True)


def about_keyboard(index: int, total: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if index > 0:
        b.button(text="⬅️ Назад", callback_data=AboutCB(page=index-1))
    if index < total-1:
        b.button(text="➡️ Далі", callback_data=AboutCB(page=index+1))
    b.adjust(2)
    return b.as_markup()


def admin_list_keyboard(kind: str, status: str, offset: int, rows, has_next: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    statuses = ("all", "new", "working", "resolved", "closed") if kind == "appeal" else ("all", "new", "review", "accepted", "rejected")
    labels = {"all":"Усі", "new":"🆕 нова", "working":"🔄 в роботі", "resolved":"✅ вирішено", "closed":"❌ закрито", "review":"👀 розглядається", "accepted":"✅ прийнято", "rejected":"❌ відхилено"}
    for value in statuses:
        b.button(text=("✓ " + labels[value]) if value == status else labels[value], callback_data=AdminListCB(kind=kind, status=value, offset=0))
    for row in rows:
        if kind == "appeal":
            b.button(text=f"#{row['id']:04d}", callback_data=AdminCardCB(kind=kind, item_id=row["id"]))
        else:
            b.button(text=f"A{row['id']}", callback_data=AdminCardCB(kind=kind, item_id=row["id"]))
    if offset > 0:
        b.button(text="⬅️ Назад сторінка", callback_data=AdminListCB(kind=kind, status=status, offset=max(0,offset-8)))
    if has_next:
        b.button(text="Наступна сторінка ➡️", callback_data=AdminListCB(kind=kind, status=status, offset=offset+8))
    b.adjust(2)
    return b.as_markup()
