from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot

from bot.main import main


@pytest.mark.asyncio
async def test_main_initialization_reaches_polling_with_fake_token(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123456:TEST")
    monkeypatch.setenv("ADMIN_IDS", "1,2")
    monkeypatch.setenv("HASH_SALT", "test-salt")
    monkeypatch.setenv("FERNET_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "startup.db"))

    async def stop_polling(*args, **kwargs):
        return None

    with (
        patch.object(Bot, "set_my_commands", new=AsyncMock()),
        patch.object(Bot, "send_message", new=AsyncMock()),
        patch.object(Bot, "delete_webhook", new=AsyncMock()),
        patch("aiogram.dispatcher.dispatcher.Dispatcher.start_polling", new=stop_polling),
    ):
        await main()
