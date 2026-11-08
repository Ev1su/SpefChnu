import pytest

from bot.db import Database
from bot.handlers.appeals import format_kyiv_time


@pytest.mark.asyncio
async def test_admin_persistence(tmp_path):
    db = Database(str(tmp_path / "admins.db"))
    await db.connect()
    await db.sync_initial_admins((1, 2))
    assert await db.add_admin(3, 1) is True
    assert await db.add_admin(3, 1) is False
    assert await db.list_admins() == (1, 2, 3)
    await db.close()


async def test_create_status_notes_cleanup(tmp_path):
    db = Database(str(tmp_path / "bot.db"))
    await db.connect()
    appeal_id = await db.create_appeal("hash", "enc", "Інше", "Тестове звернення довше 10 символів", False)
    assert await db.set_appeal_status(appeal_id, "working") is True
    assert await db.set_appeal_status(appeal_id, "working") is False
    await db.add_note("appeal", appeal_id, "Адмін", "Перевірка")
    assert len(await db.get_notes("appeal", appeal_id)) == 1
    await db.close()

@pytest.mark.asyncio
async def test_cleanup(tmp_path):
    db = Database(str(tmp_path / "bot.db"))
    await db.connect()
    item = await db.create_appeal("hash", "enc", "Інше", "Тестове звернення довше 10 символів", True)
    await db.set_appeal_status(item, "closed")
    await db.execute("UPDATE appeals SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (item,))
    appeal_ids, _join_ids = await db.cleanup(30)
    assert item in appeal_ids
    await db.close()


@pytest.mark.asyncio
async def test_appeal_username_consent_and_stats(tmp_path):
    db = Database(str(tmp_path / "identity.db"))
    await db.connect()
    without = await db.create_appeal("hash-a", "enc-a", "Інше", "Анонімне звернення", False)
    with_name = await db.create_appeal("hash-b", "enc-b", "Інше", "Звернення з username", False, "student_name")
    anonymous = await db.get_appeal(without)
    shared = await db.get_appeal(with_name)
    assert anonymous["username"] is None
    assert shared["username"] == "student_name"
    stats = await db.stats()
    assert stats["appeal_new"] == 2
    await db.close()


@pytest.mark.asyncio
async def test_join_username_and_stats(tmp_path):
    db = Database(str(tmp_path / "join.db"))
    await db.connect()
    application_id = await db.create_join_application({
        "user_id_enc": "id-enc",
        "username": "candidate_name",
        "full_name_enc": "name-enc",
        "birth_date_enc": "date-enc",
        "phone_enc": "phone-enc",
        "group_name": "1КІ",
        "instagram": "@candidate",
        "telegram": "@candidate",
        "motivation": "Хочу допомагати студентам",
        "experience": "Немає досвіду",
        "hours": 4,
    })
    row = await db.get_join_application(application_id)
    assert row["username"] == "candidate_name"
    stats = await db.stats()
    assert stats["join_new"] == 1
    await db.close()


@pytest.mark.asyncio
async def test_atomic_appeal_limits_and_responsible(tmp_path):
    db = Database(str(tmp_path / "limits.db"))
    await db.connect()
    appeal_id = await db.create_appeal("rate-user", "enc", "Інше", "Тестове звернення", False)

    assert await db.consume_appeal_slot("rate-user", 1, 3) is True
    assert await db.consume_appeal_slot("rate-user", 1, 3) is False

    assert await db.set_appeal_status(appeal_id, "working", "Олена Адмінка") is True
    row = await db.get_appeal(appeal_id)
    assert row["status"] == "working"
    assert row["responsible"] == "Олена Адмінка"

    assert await db.set_join_status(1, "review", "Іван Адмін") is False
    await db.close()


@pytest.mark.asyncio
async def test_expired_appeal_limit_slot_is_reusable(tmp_path):
    db = Database(str(tmp_path / "expired.db"))
    await db.connect()
    await db.execute("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(?,?,?)", ("old-user", "day", 1))
    await db.execute("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(?,?,?)", ("old-user", "hour", 1))
    assert await db.consume_appeal_slot("old-user", 1, 1) is True
    assert await db.consume_appeal_slot("old-user", 1, 1) is False
    await db.close()


def test_kyiv_time_is_human_readable():
    assert format_kyiv_time("2026-11-06T16:29:12+00:00") == "06.11.2026, 18:29"


@pytest.mark.asyncio
async def test_join_take(tmp_path):
    db = Database(str(tmp_path / "join_take.db"))
    await db.connect()
    application_id = await db.create_join_application({
        "user_id_enc": "id",
        "username": None,
        "full_name_enc": "name",
        "birth_date_enc": "date",
        "phone_enc": "phone",
        "group_name": "1КІ",
        "instagram": None,
        "telegram": "@candidate",
        "motivation": "Допомогти студентам і навчатись",
        "experience": "",
        "hours": 4,
    })
    assert await db.set_join_status(application_id, "review", "Марія Адмін") is True
    row = await db.get_join_application(application_id)
    assert row["status"] == "review"
    assert row["responsible"] == "Марія Адмін"
    await db.close()
