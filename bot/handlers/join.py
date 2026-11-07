import html

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.callbacks import JoinActionCB, JoinStatusCB
from bot.db import Database
from bot.filters import IsAdmin, IsPrivate
from bot.keyboards import (
    back_cancel,
    join_status_keyboard,
    phone_keyboard,
    skip_back_cancel,
)
from bot.services.crypto import CryptoService
from bot.services.notify import safe_send_message
from bot.states import JoinStates
from bot.validators import (
    normalize_full_name,
    normalize_instagram,
    normalize_phone,
    normalize_telegram,
    validate_birth_date,
)

router = Router(name="join")

FIELDS = ("full_name", "birth_date", "phone", "group_name", "instagram", "telegram")


@router.message(F.text == "✍️ Приєднатися до відділу", IsPrivate())
async def start_join(message: Message, state: FSMContext, db: Database, crypto: CryptoService):
    await state.clear(); enc_id = crypto.encrypt(str(message.from_user.id))
    active, recent = await db.count_join_limits(enc_id)
    if active:
        await message.answer("⚠️ У тебе вже є активна анкета. Дочекайся рішення, або скористайся /cancel."); return
    if recent:
        await message.answer("⚠️ Нову анкету можна подати не раніше ніж через 7 днів після попередньої."); return
    await state.update_data(editing=False, editing_field=None, values={})
    await state.set_state(JoinStates.full_name)
    await message.answer("⚠️ Ця анкета не анонімна: нам потрібні твої контакти", reply_markup=back_cancel())
    await message.answer("Крок 1 з 6\nВкажи свій ПІБ повністю, наприклад: Олена Петренко-Павленко.")


@router.message(JoinStates.full_name, F.text, F.chat.type == "private")
async def full_name(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад": return
    from bot.validators import validate_full_name
    if not validate_full_name(message.text):
        await message.answer("⚠️ Вкажи ПІБ із щонайменше двох слів, без цифр."); return
    result = normalize_full_name(message.text)
    if not result:
        await message.answer("⚠️ Вкажи ПІБ із щонайменше двох слів, без цифр."); return
    data = await state.get_data(); values = data.get("values", {}); values["full_name"] = result
    await state.update_data(values=values)
    if data.get("editing_field") == "full_name":
        await state.update_data(editing_field=None); await state.set_state(JoinStates.confirm); await show_confirm(message, values); return
    await state.set_state(JoinStates.birth_date)
    await message.answer("Крок 2 з 6\nДата народження у форматі ДД.ММ.РРРР, наприклад 03.10.2008", reply_markup=back_cancel())


@router.message(JoinStates.birth_date, F.text, F.chat.type == "private")
async def birth_date(message: Message, state: FSMContext):
    if not validate_birth_date(message.text):
        await message.answer("⚠️ Схоже, дата введена неправильно. Спробуй ще раз у форматі ДД.ММ.РРРР, наприклад 25.03.2006"); return
    data = await state.get_data(); values = data.get("values", {}); values["birth_date"] = message.text.strip()
    await state.update_data(values=values)
    if data.get("editing_field") == "birth_date":
        await state.update_data(editing_field=None); await state.set_state(JoinStates.confirm); await show_confirm(message, values); return
    await state.set_state(JoinStates.phone)
    await message.answer("Крок 3 з 6\nНомер телефону. Приклад: +380501234567", reply_markup=phone_keyboard())


@router.message(JoinStates.phone, F.contact)
async def contact(message: Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id:
        await message.answer("⚠️ Поділися, будь ласка, саме своїм номером телефону."); return
    await accept_phone(message, state, message.contact.phone_number, True)


@router.message(JoinStates.phone, F.text)
async def phone_text(message: Message, state: FSMContext):
    await accept_phone(message, state, message.text, False)


async def accept_phone(message, state, raw, from_contact):
    result = normalize_phone(raw)
    if not result:
        await message.answer("⚠️ Не вдалося розпізнати номер. Приклад: +380501234567"); return
    data = await state.get_data(); values = data.get("values", {}); values["phone"] = result
    await state.update_data(values=values)
    if data.get("editing_field") == "phone":
        await state.update_data(editing_field=None); await state.set_state(JoinStates.confirm); await show_confirm(message, values); return
    await state.set_state(JoinStates.group)
    await message.answer("Крок 4 з 6\nВкажи свою групу, наприклад БЖД-21, до 20 символів.", reply_markup=back_cancel())


@router.message(JoinStates.group, F.text)
async def group(message: Message, state: FSMContext):
    if len(message.text) > 20:
        await message.answer("⚠️ Скороти назву групи до 20 символів."); return
    data = await state.get_data(); values = data.get("values", {}); values["group_name"] = message.text.strip()
    await state.update_data(values=values)
    if data.get("editing_field") == "group_name":
        await state.update_data(editing_field=None); await state.set_state(JoinStates.confirm); await show_confirm(message, values); return
    await state.set_state(JoinStates.instagram)
    await message.answer("Крок 5 з 6\nНік в Instagram. Можна написати @nick, nick або посилання.", reply_markup=skip_back_cancel("Пропустити"))


@router.message(JoinStates.instagram, F.text)
async def instagram(message: Message, state: FSMContext):
    if message.text == "Пропустити": value = None
    else:
        value = normalize_instagram(message.text)
        if not value:
            await message.answer("⚠️ Невірний Instagram-нік. Використай латиницю, цифри, крапку або нижнє підкреслення."); return
    data = await state.get_data(); values = data.get("values", {}); values["instagram"] = value
    await state.update_data(values=values)
    if data.get("editing_field") == "instagram":
        await state.update_data(editing_field=None); await state.set_state(JoinStates.confirm); await show_confirm(message, values); return
    await state.set_state(JoinStates.telegram)
    from aiogram.utils.keyboard import ReplyKeyboardBuilder
    b = ReplyKeyboardBuilder(); b.button(text="Використати мій @username") if message.from_user.username else None; b.button(text="⬅️ Назад"); b.button(text="❌ Скасувати")
    await message.answer("Крок 6 з 6\nНік у Telegram.", reply_markup=b.as_markup(resize_keyboard=True))


@router.message(JoinStates.telegram, F.text)
async def telegram_nick(message: Message, state: FSMContext):
    raw = message.text
    if raw == "Використати мій @username":
        raw = message.from_user.username or ""
    value = normalize_telegram(raw)
    if not value:
        await message.answer("⚠️ Введи Telegram-нік із 5–32 символів, наприклад @pravna"); return
    data = await state.get_data(); values = data.get("values", {})
    values["telegram"] = value
    values["motivation"] = "Не вказано"
    values["experience"] = None
    values["hours"] = 0
    values["consent"] = 1
    await state.update_data(values=values)
    if data.get("editing_field") == "telegram":
        await state.update_data(editing_field=None)
    await state.set_state(JoinStates.confirm)
    await show_confirm(message, values)



async def show_confirm(message, values):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    text = "<b>Перевірка анкети</b>\n━━━━━━━━━━\n"
    labels = {"full_name":"Свій ПІБ", "birth_date":"Дата народження", "phone":"Номер телефону", "group_name":"Група", "instagram":"Нік Instagram", "telegram":"Нік Telegram"}
    for key, label in labels.items(): text += f"{label}: {html.escape(str(values.get(key) or 'Не вказано'))}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Надіслати", callback_data="join_submit")],[InlineKeyboardButton(text="✏️ Змінити", callback_data="join_edit")],[InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_action")]])
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "join_edit", JoinStates.confirm)
async def edit_start(call: CallbackQuery, state: FSMContext):
    await call.answer(); await state.set_state(JoinStates.edit_field)
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [[InlineKeyboardButton(text="Свій ПІБ", callback_data="je:full_name")],[InlineKeyboardButton(text="Дата народження", callback_data="je:birth_date")],[InlineKeyboardButton(text="Номер телефону", callback_data="je:phone")],[InlineKeyboardButton(text="Група", callback_data="je:group_name")],[InlineKeyboardButton(text="Нік Instagram", callback_data="je:instagram")],[InlineKeyboardButton(text="Нік Telegram", callback_data="je:telegram")]]
    await call.message.edit_text("Оберіть поле для зміни:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("je:"), JoinStates.edit_field)
async def edit_field(call: CallbackQuery, state: FSMContext):
    await call.answer(); field = call.data.split(":",1)[1]; await state.update_data(editing_field=field)
    state_map={"full_name":JoinStates.full_name,"birth_date":JoinStates.birth_date,"phone":JoinStates.phone,"group_name":JoinStates.group,"instagram":JoinStates.instagram,"telegram":JoinStates.telegram}
    await state.set_state(state_map[field]); await call.message.edit_text("Введи нове значення. Після перевірки повернемось до підсумку анкети.")


@router.callback_query(F.data == "join_submit", JoinStates.confirm)
async def submit_join(call: CallbackQuery, state: FSMContext, db: Database, crypto: CryptoService, settings, bot):
    await call.answer(); data = await state.get_data(); values=data["values"]
    app = await db.create_join_application({
        "user_id_enc":crypto.encrypt(str(call.from_user.id)),"username":call.from_user.username,"full_name_enc":crypto.encrypt(values["full_name"]),"birth_date_enc":crypto.encrypt(values["birth_date"]),"phone_enc":crypto.encrypt(values["phone"]),"group_name":values["group_name"],"instagram":values.get("instagram"),"telegram":values["telegram"],"motivation":values["motivation"],"experience":values.get("experience"),"hours":values["hours"]})
    row=await db.get_join_application(app)
    delivered=False
    for admin_id in settings.admin_ids:
        msg=await safe_send_message(bot, admin_id, join_card(row, crypto), reply_markup=join_status_keyboard(app,"new"))
        if msg: delivered=True; await db.add_admin_card("application",app,admin_id,msg.message_id); await db.add_admin_msg_map(admin_id,msg.message_id,"application",app)
    await db.set_join_delivery(app, delivered); await state.clear()
    await call.message.edit_text(f"✅ Анкету A{app} надіслано. Ми розглянемо її та напишемо сюди.")


def join_card(row, crypto):
    labels={"new":"🆕 нова","review":"👀 розглядається","accepted":"✅ прийнято","rejected":"❌ відхилено"}
    user_id = html.escape(crypto.decrypt(row['user_id_enc']))
    try:
        username = row['username']
    except (KeyError, IndexError):
        username = None
    direct_username = str(username).lstrip('@') if username else None
    direct_link = f'<a href="https://t.me/{html.escape(direct_username)}">@{html.escape(direct_username)}</a>' if direct_username else f'<a href="tg://user?id={user_id}">Написати в Telegram</a>'
    responsible = html.escape(row['responsible']) if row['responsible'] else 'ще не призначено'
    return (f"<b>Анкета A{row['id']}</b>\n━━━━━━━━━━\nСвій ПІБ: {html.escape(crypto.decrypt(row['full_name_enc']))}\n"
            f"Дата народження: {html.escape(crypto.decrypt(row['birth_date_enc']))}\nНомер телефону: {html.escape(crypto.decrypt(row['phone_enc']))}\nГрупа: {html.escape(row['group_name'])}\nНік Instagram: {html.escape(row['instagram'] or 'не вказано')}\nНік Telegram: {html.escape(row['telegram'])}\n{direct_link}\nСтатус: {labels[row['status']]}\nВідповідальний: {responsible}")


@router.callback_query(JoinActionCB.filter(F.action == "take"), IsAdmin())
async def take_join_application(call: CallbackQuery, callback_data: JoinActionCB, db: Database, crypto: CryptoService, bot):
    await call.answer()
    before = await db.get_join_application(callback_data.application_id)
    changed = await db.set_join_status(callback_data.application_id, "review", call.from_user.full_name)
    if not changed:
        await call.answer("⚠️ Відповідального вже призначено або заявку недоступно")
        return
    row = await db.get_join_application(callback_data.application_id)
    for card in await db.get_admin_cards("application", callback_data.application_id):
        try:
            await call.bot.edit_message_text(
                join_card(row, crypto),
                chat_id=card["admin_id"],
                message_id=card["message_id"],
                reply_markup=join_status_keyboard(callback_data.application_id, row["status"]),
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    if before and before["status"] != "review":
        try:
            user_id = int(crypto.decrypt(row["user_id_enc"]))
            await bot.send_message(user_id, "Твою анкету взяли в роботу. Ми почали розглядати твою заявку.")
        except (TelegramForbiddenError, TelegramBadRequest, ValueError):
            await call.message.answer("⚠️ Кандидат заблокував бота або адреса недоступна")
    await call.answer("✅ Ти взяв(-ла) заявку в роботу")


@router.callback_query(JoinStatusCB.filter(), IsAdmin())
async def join_status(call: CallbackQuery, callback_data: JoinStatusCB, db: Database, crypto: CryptoService, settings, bot):
    await call.answer()
    changed=await db.set_join_status(callback_data.application_id, callback_data.status)
    if not changed: return
    row=await db.get_join_application(callback_data.application_id)
    card=join_card(row,crypto)+f"\n━━━━━━━━━━\nСтатус: {callback_data.status} · Змінив: {html.escape(call.from_user.full_name)}"
    for old in await db.get_admin_cards("application",callback_data.application_id):
        try: await bot.edit_message_text(card,chat_id=old["admin_id"],message_id=old["message_id"],reply_markup=join_status_keyboard(callback_data.application_id,callback_data.status))
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    try:
        user_id=int(crypto.decrypt(row["user_id_enc"]))
        messages={"new":"Анкету повернули до нового статусу.","review":"Твою анкету почали розглядати.","accepted":"Раді повідомити — твою анкету прийнято!","rejected":"На жаль, цього разу анкету не прийнято. Дякуємо за цікавість."}
        await bot.send_message(user_id,messages[callback_data.status])
    except TelegramForbiddenError: await call.message.answer("⚠️ Кандидат заблокував бота.")
