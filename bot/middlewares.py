import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot.texts import THROTTLE_ERROR


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, max_per_second: int = 4):
        self.max_per_second = max_per_second
        self.history: dict[int, deque[float]] = defaultdict(deque)

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        now = time.monotonic()
        queue = self.history[user.id]
        while queue and now - queue[0] > 1.0:
            queue.popleft()
        if len(queue) >= self.max_per_second:
            if isinstance(event, Message):
                await event.answer(THROTTLE_ERROR)
            return None
        queue.append(now)
        return await handler(event, data)
