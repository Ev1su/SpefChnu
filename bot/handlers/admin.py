import html
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import BotCommandScopeChat, CallbackQuery, Message

from bot.callbacks import AdminCardCB, AdminListCB
from bot.db import Database
from bot.filters import IsAdmin, IsPrivate
from bot.handlers.appeals import appeal_card
from bot.handlers.join import join_card
from bot.handlers.start import ADMIN_COMMANDS
from bot.keyboards import (
    admin_list_keyboard,
    appeal_admin_keyboard,
    join_status_keyboard,
)
from bot.services.crypto import CryptoService

router = Router(name="admin")


@router.message(Command("addadmin"), IsPrivate())
async def add_admin(message: Message, db: Database, settings, bot):
    if message.from_user.id != settings.super_admin_id:
        await message.answer("⛔ Команда доступна лише головному адміністратору.")
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) != 2 or not re.fullmatch(r"[1-9]\d{5,15}", parts[1].strip()):
        await message.answer("Використання: <code>/addadmin 123456789</code>\nДізнатися ID можна в боті через /myid.")
        return

    new_admin_id = int(parts[1].strip())
    if not await db.add_admin(new_admin_id, message.from_user.id):
        await message.answer("ℹ️ Цей користувач уже є адміністратором.")
        return

    settings.admin_ids = await db.list_admins()
    await bot.set_my_commands([], BotCommandScopeChat(chat_id=new_admin_id))
    await bot.set_my_commands(ADMIN_COMMANDS, BotCommandScopeChat(chat_id=new_admin_id))
    await message.answer(f"✅ Користувача <code>{new_admin_id}</code> додано як адміністратора.")


@router.message(F.text.in_({"📋 Звернення", "📋 Анкети", "📊 Статистика"}), IsPrivate(), IsAdmin())
async def admin_menu(message: Message, db: Database, crypto: CryptoService):
    if message.text == "📊 Статистика":
        s = await db.stats()
        text = (
            "<b>📊 Статистика організації</b>\n━━━━━━━━━━\n"
            "<b>Звернення</b>\n"
            f"🆕 Нові: <b>{s['appeal_new']}</b>  ·  🔄 У роботі: <b>{s['appeal_working']}</b>\n"
            f"✅ Вирішені: <b>{s['appeal_resolved']}</b>  ·  ❌ Закриті: <b>{s['appeal_closed']}</b>\n"
            f"🔴 Срочні відкриті: <b>{s['appeal_urgent_open']}</b>\n"
            f"За 7 днів: <b>{s['appeal_7']}</b>  ·  За 30 днів: <b>{s['appeal_30']}</b>\n"
            f"⚠️ Недоставлені: <b>{s['appeal_undelivered']}</b>\n"
            "━━━━━━━━━━\n<b>Анкети</b>\n"
            f"🆕 Нові: <b>{s['join_new']}</b>  ·  👀 Розглядаються: <b>{s['join_review']}</b>\n"
            f"✅ Прийнято: <b>{s['join_accepted']}</b>  ·  ❌ Відхилено: <b>{s['join_rejected']}</b>\n"
            f"За 7 днів: <b>{s['join_7']}</b>  ·  За 30 днів: <b>{s['join_30']}</b>\n"
            f"⚠️ Недоставлені: <b>{s['join_undelivered']}</b>"
        )
        await message.answer(text)
    elif message.text == "📋 Звернення":
        rows = await db.list_items("appeal", "all", 0, 8)
        await message.answer("<b>📋 Звернення</b>", reply_markup=admin_list_keyboard("appeal", "all", 0, rows, len(rows)==8))
    else:
        rows = await db.list_items("application", "all", 0, 8)
        await message.answer("<b>📋 Анкети</b>", reply_markup=admin_list_keyboard("application", "all", 0, rows, len(rows)==8))


@router.callback_query(AdminListCB.filter(), IsAdmin())
async def list_filter(call: CallbackQuery, callback_data: AdminListCB, db: Database):
    await call.answer()
    rows = await db.list_items(callback_data.kind, callback_data.status, callback_data.offset, 8)
    await call.message.edit_text("Список оновлено:", reply_markup=admin_list_keyboard(callback_data.kind, callback_data.status, callback_data.offset, rows, len(rows)==8))


@router.callback_query(AdminCardCB.filter(), IsAdmin())
async def card(call: CallbackQuery, callback_data: AdminCardCB, db: Database, crypto: CryptoService):
    await call.answer()
    if callback_data.kind == "appeal":
        row = await db.get_appeal(callback_data.item_id); notes = await db.get_notes("appeal", callback_data.item_id)
        text = appeal_card(row, "\n".join(f"• {html.escape(n['text'])}" for n in notes))
        await call.message.edit_text(text, reply_markup=appeal_admin_keyboard(callback_data.item_id, row["status"]))
    else:
        row = await db.get_join_application(callback_data.item_id); notes = await db.get_notes("application", callback_data.item_id)
        text = join_card(row, crypto) + ("\n━━━━━━━━━━\n<b>Нотатки:</b>\n"+"\n".join(f"• {html.escape(n['text'])}" for n in notes) if notes else "")
        await call.message.edit_text(text, reply_markup=join_status_keyboard(callback_data.item_id, row["status"]))


@router.message(Command("note"), IsPrivate(), IsAdmin())
async def add_note(message: Message, db: Database):
    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Приклад: /note #0427 Текст нотатки або /note A12 Текст"); return
    match = re.fullmatch(r"#(\d{4}|\d+)", parts[1])
    if match: kind, item_id = "appeal", int(match.group(1))
    else:
        match = re.fullmatch(r"A(\d+)", parts[1], re.IGNORECASE)
        if not match: await message.answer("Вкажи номер у форматі #0427 або A12."); return
        kind, item_id = "application", int(match.group(1))
    await db.add_note(kind, item_id, message.from_user.full_name, parts[2])
    await message.answer("✅ Нотатку збережено та показано адмінам.")
    for card in await db.get_admin_cards(kind, item_id):
        try:
            if kind == "appeal":
                row = await db.get_appeal(item_id); notes = await db.get_notes(kind,item_id)
                await message.bot.edit_message_text(appeal_card(row,"\n".join(f"• {html.escape(n['text'])}" for n in notes)), chat_id=card["admin_id"], message_id=card["message_id"], reply_markup=appeal_admin_keyboard(item_id,row["status"]))
        except (TelegramForbiddenError, TelegramBadRequest):
            pass


@router.message(F.chat.type == "private", F.reply_to_message)
async def admin_reply(message: Message, db: Database, crypto: CryptoService, settings, bot):
    if message.from_user.id not in settings.admin_ids: return
    mapped = await db.get_admin_msg_item(message.from_user.id, message.reply_to_message.message_id)
    if not mapped: return
    kind,item_id = mapped["kind"],mapped["item_id"]
    if kind == "appeal": row = await db.get_appeal(item_id); chat_id=crypto.decrypt(row["chat_id_enc"]); prefix=f"💬 Відповідь від Правозахисного відділу щодо звернення #{item_id:04d}:"
    else: row=await db.get_join_application(item_id); chat_id=crypto.decrypt(row["user_id_enc"]); prefix="💬 Відповідь від Правозахисного відділу:"
    try:
        await bot.send_message(chat_id, f"<b>{prefix}</b>\n{html.escape(message.text)}")
    except TelegramForbiddenError:
        await message.answer("⚠️ Користувач заблокував бота, неможливо надіслати повідомлення."); return
    await message.answer("✅ Доставлено")
    for card in await db.get_admin_cards(kind,item_id):
        if card["admin_id"] != message.from_user.id:
            await bot.send_message(card["admin_id"], f"✉️ Відповів: {html.escape(message.from_user.full_name)}\nКоротко: {html.escape(message.text[:120])}")
