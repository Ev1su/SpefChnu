from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BotCommand, Message

from bot.keyboards import main_menu
from bot.texts import CANCELLED, WELCOME

router = Router(name="start")

PUBLIC_COMMANDS = [
    BotCommand(command="start", description="Головне меню"),
    BotCommand(command="menu", description="Відкрити меню"),
    BotCommand(command="cancel", description="Скасувати поточну дію"),
    BotCommand(command="myid", description="Показати Telegram ID"),
    BotCommand(command="help", description="Допомога"),
]
ADMIN_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand(command="note", description="Додати внутрішню нотатку"),
    BotCommand(command="addadmin", description="Додати адміністратора за Telegram ID"),
]


@router.message(CommandStart(), F.chat.type == "private")
@router.message(Command("menu"), F.chat.type == "private")
async def start(message: Message, state: FSMContext, settings):
    await state.clear()
    is_admin = message.from_user.id in settings.admin_ids
    await message.answer(WELCOME, reply_markup=main_menu(admin=is_admin))


@router.message(Command("cancel"), F.chat.type == "private")
@router.message(F.text == "❌ Скасувати", F.chat.type == "private")
async def cancel(message: Message, state: FSMContext, settings):
    await state.clear()
    await message.answer(CANCELLED, reply_markup=main_menu(admin=message.from_user.id in settings.admin_ids))


@router.message(Command("myid"), F.chat.type == "private")
async def myid(message: Message):
    await message.answer(f"Твій Telegram ID: <code>{message.from_user.id}</code>")


@router.message(Command("help"), F.chat.type == "private")
async def help_command(message: Message):
    await message.answer("Обери пункт меню або скористайся /cancel, щоб скасувати поточну дію.")


@router.message(F.text == "📞 Контакти", F.chat.type == "private")
async def public_contacts(message: Message, settings):
    if settings.admin_usernames:
        contact_lines = []
        for item in settings.admin_usernames:
            username, separator, role = item.partition("-")
            username = username.strip()
            if username.startswith("@") and username[1:].replace("_", "a").replace(".", "a").isalnum():
                if separator and role.strip():
                    line = f"• <a href=\"https://t.me/{username.lstrip('@')}\">{username}</a> — {role.strip()}"
                else:
                    line = f"• <a href=\"https://t.me/{username.lstrip('@')}\">{username}</a>"
            else:
                line = f"• {item}"
            contact_lines.append(line)
        contacts = "\n".join(contact_lines)
    else:
        contacts = "Список контактів адмінів ще не налаштовано."
    await message.answer(f"<b>📞 Контакти Правозахисного відділу</b>\n━━━━━━━━━━\n{contacts}", disable_web_page_preview=True)


@router.message(F.text == "👥 Про нас", F.chat.type == "private")
async def about_menu(message: Message):
    from bot.content import ABOUT_PAGES
    from bot.keyboards import about_keyboard

    page = ABOUT_PAGES[0]
    text = f"<b>{page['title']}</b>\n━━━━━━━━━━\n{page['text']}\n\nСторінка 1/{len(ABOUT_PAGES)}"
    await message.answer(text, reply_markup=about_keyboard(0, len(ABOUT_PAGES)))

