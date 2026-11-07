from aiogram import F, Router
from aiogram.types import Message

router = Router(name="fallback")


@router.message(F.chat.type == "private")
async def unknown_message(message: Message):
    await message.answer("Обери дію в меню нижче. Якщо потрібна допомога — скористайся /help.")
