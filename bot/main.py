import asyncio
import copy
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import (
    BotCommandScopeChat,
    BotCommandScopeDefault,
    ErrorEvent,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import load_settings
from bot.db import Database
from bot.handlers.about import router as about_router
from bot.handlers.admin import router as admin_router
from bot.handlers.appeals import router as appeals_router
from bot.handlers.fallback import router as fallback_router
from bot.handlers.join import router as join_router
from bot.handlers.start import ADMIN_COMMANDS, PUBLIC_COMMANDS
from bot.handlers.start import router as start_router
from bot.middlewares import ThrottleMiddleware
from bot.services.cleanup import cleanup_job
from bot.services.crypto import CryptoService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__) 


def build_dispatcher(settings=None, db=None, crypto=None) -> Dispatcher:
    """Собирает и проверяемо конфигурирует диспетчер без запуска polling."""
    dp = Dispatcher()
    if settings is not None:
        dp["settings"] = settings
    if db is not None:
        dp["db"] = db
    if crypto is not None:
        dp["crypto"] = crypto
    dp.message.middleware(ThrottleMiddleware(max_per_second=2))

    @dp.error()
    async def global_error(event: ErrorEvent):
        logger.exception("Помилка диспетчера: %s", type(event.exception).__name__, exc_info=event.exception)
        update = event.update
        if update.message:
            await update.message.answer("Сталася помилка, спробуй пізніше")
        elif update.callback_query:
            await update.callback_query.answer("Сталася помилка, спробуй пізніше", show_alert=True)
        return True

    dp.include_router(copy.deepcopy(admin_router))
    dp.include_router(copy.deepcopy(start_router))
    dp.include_router(copy.deepcopy(appeals_router))
    dp.include_router(copy.deepcopy(join_router))
    dp.include_router(copy.deepcopy(about_router))
    dp.include_router(copy.deepcopy(fallback_router))
    return dp


async def main() -> None:
    settings = load_settings()
    db = Database(settings.db_path)
    await db.connect()
    crypto = CryptoService(settings.fernet_key, settings.hash_salt)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = build_dispatcher(settings, db, crypto)

    await bot.set_my_commands(PUBLIC_COMMANDS, BotCommandScopeDefault())
    for admin_id in settings.admin_ids:
        await bot.set_my_commands(ADMIN_COMMANDS, BotCommandScopeChat(chat_id=admin_id))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_job, "interval", hours=24, args=[bot, db, settings.retention_days])

    async def retry_delivery():
        for row in await db.get_pending_appeals():
            pass
        for row in await db.get_pending_join_applications():
            pass

    scheduler.add_job(retry_delivery, "interval", hours=1)
    scheduler.start()

    try:
        await bot.send_message(settings.admin_ids[0], "🟢 Бот запущено")
    except TelegramForbiddenError as exc:
        logger.warning("Суперадмін недоступний під час запуску: %s", type(exc).__name__)

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
