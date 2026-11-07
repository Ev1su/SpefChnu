from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from aiogram.types.input_file import FSInputFile

from bot.callbacks import AboutCb
from bot.content import ABOUT_PAGES
from bot.keyboards import about_keyboard

router = Router(name="about")


@router.callback_query(AboutCb.filter())
async def about_page(call: CallbackQuery, callback_data: AboutCb):
    await call.answer()
    index = max(0, min(callback_data.page, len(ABOUT_PAGES) - 1))
    page = ABOUT_PAGES[index]
    text = f"<b>{page['title']}</b>\n━━━━━━━━━━\n{page['text']}\n\nСторінка {index + 1}/{len(ABOUT_PAGES)}"
    photo = page.get("photo_path")
    try:
        if photo and __import__("pathlib").Path(photo).exists():
            await call.message.delete()
            await call.message.answer_photo(FSInputFile(photo), caption=text, reply_markup=about_keyboard(index, len(ABOUT_PAGES)))
        else:
            await call.message.edit_text(text, reply_markup=about_keyboard(index, len(ABOUT_PAGES)))
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
