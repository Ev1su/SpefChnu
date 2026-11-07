import logging

from aiogram import Bot

from bot.db import Database

logger = logging.getLogger(__name__)


async def cleanup_job(bot: Bot, db: Database, retention_days: int) -> None:
    appeal_ids, join_ids = await db.cleanup(retention_days)
    logger.info("Автоочищення: видалено %d звернень і %d анкет", len(appeal_ids), len(join_ids))
