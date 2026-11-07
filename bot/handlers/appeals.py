import html
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.callbacks import AppealActionCB, AppealIdentityCB, AppealStatusCB, MyAppealCB
from bot.db import Database
from bot.filters import IsAdmin, IsPrivate
from bot.keyboards import (
    appeal_admin_keyboard,
    appeal_categories,
    appeal_confirm_keyboard,
    appeal_done_cancel,
)
from bot.services.crypto import CryptoService
from bot.services.notify import safe_copy_message, safe_send_message
from bot.states import AdminReplyStates, AppealStates
from bot.texts import APPEAL_WARNING

router = Router(name="appeals")


def format_kyiv_time(raw: str) -> str:
    try:
        normalized = raw[:-1] + "+00:00" if isinstance(raw, str) and raw.endswith("Z") else raw
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(ZoneInfo("Europe/Kyiv")).strftime("%d.%m.%Y, %H:%M")
    except (TypeError, ValueError, OverflowError):
        return html.escape(str(raw))


def appeal_card(row, notes="") -> str:
    status_labels = {"new":"🆕 нова", "working":"🔄 в роботі", "resolved":"✅ вирішено", "closed":"❌ закрито"}
    urgency = "🔴 Термінове" if row["urgent"] else "🟢 Звичайне"
    identity = ""
    try:
        username = row["username"]
    except (KeyError, IndexError):
        username = None
    if username:
        safe_username = html.escape(username.lstrip("@"))
        identity = f"\nКонтакт студента: <a href=\"https://t.me/{safe_username}\">@{safe_username}</a>"
    text = f"<b>Звернення #{row['id']:04d}</b>\n━━━━━━━━━━\nКатегорія: {html.escape(row['category'])}\nТерміновість: {urgency}\nЧас: {format_kyiv_time(row['created_at'])}\nСтатус: {status_labels[row['status']]}\nВідповідальний: {html.escape(row['responsible']) if row['responsible'] else 'ще не призначено'}{identity}\n━━━━━━━━━━\n{html.escape(row['description'])}"
    if notes:
        text += "\n━━━━━━━━━━\n<b>Нотатки:</b>\n" + notes
    return text


@router.message(F.text == "📝 Подати анонімне звернення", IsPrivate())
async def start_appeal(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AppealStates.category)
    await message.answer(APPEAL_WARNING, reply_markup=appeal_categories())


@router.callback_query(F.data.startswith("cat:"), AppealStates.category)
async def category(call: CallbackQuery, state: FSMContext):
    await call.answer()
    category = call.data.split(":", 1)[1]
    await state.update_data(category=category, description=None, attachments=[])
    await state.set_state(AppealStates.description)
    await call.message.edit_text("Крок 1 з 3\nНапиши, що сталося. Можна додати до 5 вкладень, потім натисни «Готово». Придумай стислу опису ситуації — мінімум 10 символів.", reply_markup=appeal_done_cancel())


@router.message(AppealStates.description, F.text, F.chat.type == "private")
async def description(message: Message, state: FSMContext, db: Database):
    if message.text in ("✅ Готово", "❌ Скасувати"):
        return
    if len(message.text) < 10:
        await message.answer("⚠️ Напиши трохи детальніше — щонайменше 10 символів.")
        return
    await state.update_data(description=message.text)
    await state.set_state(AppealStates.urgency)
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🟢 Звичайне", callback_data="urgency:0")
    keyboard.button(text="🔴 Термінове", callback_data="urgency:1")
    keyboard.adjust(1)
    await message.answer("Крок 2 з 3\nОберіть терміновість:", reply_markup=keyboard.as_markup())


@router.message(AppealStates.description, F.content_type != "text", F.chat.type == "private")
async def attachment(message: Message, state: FSMContext):
    data = await state.get_data(); attachments = data.get("attachments", [])
    if len(attachments) >= 5:
        await message.answer("⚠️ Максимум 5 вкладень.")
        return
    attachments.append(message.message_id)
    await state.update_data(attachments=attachments)
    await message.answer(f"Вкладення додано ({len(attachments)}/5). Додай текст або натисни «Готово».", reply_markup=appeal_done_cancel())


@router.callback_query(F.data == "appeal_done", AppealStates.description)
async def done(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    if not data.get("description") and not data.get("attachments"):
        await call.message.answer("⚠️ Додай опис або хоча б одне вкладення."); return
    await state.set_state(AppealStates.urgency)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder(); b.button(text="🟢 Звичайне", callback_data="urgency:0"); b.button(text="🔴 Термінове", callback_data="urgency:1"); b.adjust(1)
    await call.message.edit_text("Крок 2 з 3\nОберіть терміновість:", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("urgency:"), AppealStates.urgency)
async def urgency(call: CallbackQuery, state: FSMContext):
    await call.answer(); urgent = call.data.endswith("1")
    await state.update_data(urgent=urgent); await state.set_state(AppealStates.confirm)
    data = await state.get_data()
    summary = f"<b>Перевірка звернення</b>\n━━━━━━━━━━\nКатегорія: {html.escape(data['category'])}\nТерміновість: {'🔴 Термінове' if urgent else '🟢 Звичайне'}\nОпис: {html.escape(data.get('description') or 'без текстового опису')}"
    await call.message.edit_text(summary + "\n\n<i>☐ Адміни не побачать твій @username.</i>", reply_markup=appeal_confirm_keyboard())


@router.callback_query(AppealIdentityCB.filter(), AppealStates.confirm)
async def toggle_username(call: CallbackQuery, callback_data: AppealIdentityCB, state: FSMContext):
    await call.answer()
    await state.update_data(share_username=callback_data.share_username)
    data = await state.get_data()
    summary = f"<b>Перевірка звернення</b>\n━━━━━━━━━━\nКатегорія: {html.escape(data['category'])}\nТерміновість: {'🔴 Термінове' if data['urgent'] else '🟢 Звичайне'}\nОпис: {html.escape(data.get('description') or 'без текстового опису')}"
    await call.message.edit_text(summary + ("\n\n<i>☑️ Твій @username буде видно адмінам.</i>" if callback_data.share_username else "\n\n<i>☐ Адміни не побачать твій @username.</i>"), reply_markup=appeal_confirm_keyboard(callback_data.share_username))


@router.callback_query(F.data == "appeal_submit", AppealStates.confirm)
async def submit(call: CallbackQuery, state: FSMContext, db: Database, crypto: CryptoService, settings, bot):
    await call.answer("Зберігаємо…"); data = await state.get_data(); user = call.from_user
    user_hash = crypto.user_hash(user.id)
    if not await db.consume_appeal_slot(user_hash, settings.max_appeals_per_hour, settings.max_appeals_per_day):
        await call.message.answer("⚠️ Занадто багато звернень за короткий час. Спробуй, будь ласка, пізніше."); return
    shared_username = user.username if data.get("share_username") else None
    appeal_id = await db.create_appeal(user_hash, crypto.encrypt(str(user.id)), data["category"], data.get("description") or "Вкладення без тексту", bool(data["urgent"]), shared_username)
    row = await db.get_appeal(appeal_id)
    delivered = False
    for admin_id in settings.admin_ids:
        msg = await safe_send_message(bot, admin_id, appeal_card(row), reply_markup=appeal_admin_keyboard(appeal_id, "new"))
        if msg:
            delivered = True; await db.add_admin_card("appeal", appeal_id, admin_id, msg.message_id); await db.add_admin_msg_map(admin_id, msg.message_id, "appeal", appeal_id)
        for mid in data.get("attachments", []):
            copied = await safe_copy_message(bot, admin_id, call.message.chat.id, mid)
            if copied: await db.add_admin_msg_map(admin_id, copied.message_id, "appeal", appeal_id)
    await db.set_appeal_delivery(appeal_id, delivered)
    await state.clear()
    await call.message.edit_text(f"✅ Звернення #{appeal_id:04d} прийнято. Відповідь прийде сюди, зазвичай до 48 годин. Збережи номер звернення.", reply_markup=None)


@router.callback_query(AppealStatusCB.filter(), IsAdmin())
async def appeal_status(call: CallbackQuery, callback_data: AppealStatusCB, db: Database, settings, bot):
    await call.answer()
    changed = await db.set_appeal_status(callback_data.appeal_id, callback_data.status)
    if not changed: return
    row = await db.get_appeal(callback_data.appeal_id)
    cards = await db.get_admin_cards("appeal", callback_data.appeal_id)
    admin_name = html.escape(call.from_user.full_name)
    notes = await db.get_notes("appeal", callback_data.appeal_id)
    note_text = "\n".join(f"• {html.escape(n['text'])}" for n in notes)
    text = appeal_card(row, note_text) + f"\n━━━━━━━━━━\nСтатус: {callback_data.status} · Змінив: {admin_name}"
    for card in cards:
        try:
            await bot.edit_message_text(text, chat_id=card["admin_id"], message_id=card["message_id"], reply_markup=appeal_admin_keyboard(callback_data.appeal_id, callback_data.status))
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    crypto = CryptoService(settings.fernet_key)
    texts = {"working":"Твоє звернення стало в роботі. Ми вже почали розбиратися.", "resolved":"Добра новина: твоє звернення позначено як вирішене. Якщо проблема залишилась — напиши нам.", "closed":"Звернення закрито. Якщо потрібно доповнити — створи нову переписку через меню.", "new":"Звернення повернули до нового статусу."}
    try:
        await bot.send_message(crypto.decrypt(row["chat_id_enc"]), texts[callback_data.status])
    except TelegramForbiddenError:
        await call.message.answer("⚠️ Студент заблокував бота, неможливо надіслати повідомлення.")


@router.callback_query(AppealActionCB.filter(F.action == "take"), IsAdmin())
async def take(call: CallbackQuery, callback_data: AppealActionCB, db: Database, crypto: CryptoService, bot):
    await call.answer()
    before = await db.get_appeal(callback_data.appeal_id)
    changed = await db.set_appeal_status(callback_data.appeal_id, "working", call.from_user.full_name)
    if not changed:
        await call.answer("⚠️ Відповідального вже призначено або звернення недоступне")
        return
    row = await db.get_appeal(callback_data.appeal_id)
    notes = await db.get_notes("appeal", callback_data.appeal_id)
    note_text = "\n".join(f"• {html.escape(n['text'])}" for n in notes)
    text = appeal_card(row, note_text) + f"\n━━━━━━━━━━\nСтатус: в роботі · Змінив: {html.escape(call.from_user.full_name)}"
    for card in await db.get_admin_cards("appeal", callback_data.appeal_id):
        try:
            await call.bot.edit_message_text(text, chat_id=card["admin_id"], message_id=card["message_id"], reply_markup=appeal_admin_keyboard(callback_data.appeal_id, row["status"]))
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    if before and before["status"] != "working":
        try:
            await bot.send_message(crypto.decrypt(row["chat_id_enc"]), "Твоє звернення взяли в роботу. Ми вже почали розбиратися.")
        except (TelegramForbiddenError, TelegramBadRequest):
            await call.message.answer("⚠️ Студент заблокував бота, неможливо надіслати повідомлення.")
    await call.answer("✅ Ти взяв(-ла) звернення в роботу")


@router.callback_query(AppealActionCB.filter(F.action == "reply"), IsAdmin())
async def reply_mode(call: CallbackQuery, callback_data: AppealActionCB, state: FSMContext):
    await call.answer()
    await state.set_state(AdminReplyStates.waiting)
    await state.update_data(kind="appeal", item_id=callback_data.appeal_id)
    await call.message.answer("Напиши наступне повідомлення — я надішлю його студенту. Скасувати: /cancel")


@router.message(AdminReplyStates.waiting, IsAdmin(), F.text)
async def admin_reply_text(message: Message, state: FSMContext, db: Database, settings, crypto: CryptoService, bot):
    data = await state.get_data(); row = await db.get_appeal(data["item_id"])
    try:
        await bot.send_message(crypto.decrypt(row["chat_id_enc"]), f"<b>💬 Відповідь від Правозахисного відділу щодо звернення #{row['id']:04d}:</b>\n{html.escape(message.text)}")
    except TelegramForbiddenError:
        await message.answer("⚠️ Студент заблокував бота, неможливо надіслати повідомлення."); await state.clear(); return
    await message.answer("✅ Доставлено")
    await state.clear()


@router.message(F.text == "📂 Мої звернення", IsPrivate())
async def my_appeals(message: Message, db: Database, crypto: CryptoService):
    rows = await db.get_appeals_by_hash(crypto.user_hash(message.from_user.id), 10)
    if not rows:
        await message.answer("У тебе ще немає звернень."); return
    labels = {"new":"🆕 нова", "working":"🔄 в роботі", "resolved":"✅ вирішено", "closed":"❌ закрито"}
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    text = "<b>📂 Мої звернення</b>\n━━━━━━━━━━\n"
    for row in rows:
        text += f"#{row['id']:04d} — {labels[row['status']]}\n"; b.button(text=f"✍️ #{row['id']:04d}", callback_data=MyAppealCB(appeal_id=row['id'], action="add"))
    b.adjust(1)
    await message.answer(text, reply_markup=b.as_markup())
