import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

logger = logging.getLogger(__name__)


async def safe_send_message(bot: Bot, chat_id: int, text: str, **kwargs):
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        try:
            return await bot.send_message(chat_id, text, **kwargs)
        except (TelegramForbiddenError, TelegramBadRequest) as exc2:
            logger.warning("Повторна спроба доставки не вдалася для %s: %s", chat_id, type(exc2).__name__)
            return None
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        logger.warning("Не вдалося доставити повідомлення для %s: %s", chat_id, type(exc).__name__)
        return None
    except Exception as exc:
        logger.exception("Невідома помилка доставки для %s: %s", chat_id, type(exc).__name__)
        return None


async def safe_copy_message(bot: Bot, chat_id: int, from_chat_id: int, message_id: int, **kwargs):
    try:
        return await bot.copy_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id, **kwargs)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        try:
            return await bot.copy_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id, **kwargs)
        except (TelegramForbiddenError, TelegramBadRequest) as exc2:
            logger.warning("Повторна спроба copy не вдалася для %s: %s", chat_id, type(exc2).__name__)
            return None
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        logger.warning("Не вдалося copy-повідомлення для %s: %s", chat_id, type(exc).__name__)
        return None
    except Exception as exc:
        logger.exception("Невідома помилка copy для %s: %s", chat_id, type(exc).__name__)
        return None
