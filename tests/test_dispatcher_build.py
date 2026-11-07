import pytest

from bot.config import load_settings
from bot.db import Database
from bot.main import build_dispatcher
from bot.services.crypto import CryptoService


@pytest.mark.asyncio
async def test_build_dispatcher_initializes_all_routers_and_middleware(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123456:TEST")
    monkeypatch.setenv("ADMIN_IDS", "1,2")
    monkeypatch.setenv("HASH_SALT", "test-salt")
    monkeypatch.setenv("FERNET_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "dispatcher.db"))

    settings = load_settings()
    db = Database(settings.db_path)
    await db.connect()
    crypto = CryptoService(settings.fernet_key, settings.hash_salt)

    try:
        dp = build_dispatcher(settings, db, crypto)
        assert dp["settings"] is settings
        assert dp["db"] is db
        assert dp["crypto"] is crypto
        assert dp.message.middleware is not None
        middleware_count = len(dp.message.middleware._middlewares)
        assert middleware_count == 1
        router_names = {
            "admin",
            "start",
            "appeals",
            "join",
            "about",
            "fallback",
        }
        assert {router.name for router in dp.sub_routers} >= router_names
    finally:
        await db.close()


def test_admin_usernames_are_parsed_as_contacts(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123456:TEST")
    monkeypatch.setenv("ADMIN_IDS", "1,2")
    monkeypatch.setenv("HASH_SALT", "test-salt")
    monkeypatch.setenv("FERNET_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    monkeypatch.setenv("ADMIN_USERNAMES", "@ZxcEv1su - Admin;@misssparkk - Голова відділу")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "contacts.db"))
    settings = load_settings()
    assert settings.admin_usernames == (
        "@ZxcEv1su - Admin",
        "@misssparkk - Голова відділу",
    )
