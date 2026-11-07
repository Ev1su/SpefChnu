from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message


class IsPrivate(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        chat = getattr(event, "chat", None) or getattr(getattr(event, "message", None), "chat", None)
        return chat is not None and chat.type == "private"


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, settings) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in settings.admin_ids)
