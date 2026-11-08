import os
import sys
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv


@dataclass
class Settings:
    bot_token: str
    admin_ids: tuple[int, ...]
    super_admin_id: int
    admin_usernames: tuple[str, ...]
    hash_salt: str
    fernet_key: str
    retention_days: int
    max_hour: int
    max_day: int
    db_path: str
    database_url: str | None = None
    max_appeals_per_hour: int = 10
    max_appeals_per_day: int = 30


def load_settings() -> Settings:
    load_dotenv()
    required = ("BOT_TOKEN", "ADMIN_IDS", "HASH_SALT", "FERNET_KEY")
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError("Исправь .env: не заполнены переменные: " + ", ".join(missing))
    try:
        admin_ids = tuple(int(x.strip()) for x in os.environ["ADMIN_IDS"].split(",") if x.strip())
    except ValueError as exc:
        raise RuntimeError("Исправь ADMIN_IDS в .env: используй Telegram ID через запятую, только числа") from exc
    if not admin_ids:
        raise RuntimeError("Исправь ADMIN_IDS в .env: нужен хотя бы один Telegram ID")
    try:
        Fernet(os.environ["FERNET_KEY"].strip().encode())
    except (ValueError, InvalidToken) as exc:
        raise RuntimeError("Исправь FERNET_KEY в .env: ключ должен быть валидным base64-ключом Fernet") from exc
    def positive_int(name: str, default: int) -> int:
        raw = os.getenv(name, str(default)).strip()
        try:
            value = int(raw)
        except ValueError as exc:
            raise RuntimeError(f"Исправь {name} в .env: должно быть целое число") from exc
        if value < 1:
            raise RuntimeError(f"Исправь {name} в .env: значение должно быть больше нуля")
        return value
    raw_contacts = os.getenv("ADMIN_USERNAMES", "").strip()
    admin_usernames = tuple(
        item.strip().rstrip(";")
        for item in raw_contacts.split(";")
        if item.strip()
    ) if ";" in raw_contacts else tuple(
        item.strip()
        for item in raw_contacts.split(",")
        if item.strip()
    )
    return Settings(
        bot_token=os.environ["BOT_TOKEN"].strip(),
        admin_ids=admin_ids,
        super_admin_id=admin_ids[0],
        admin_usernames=admin_usernames,
        hash_salt=os.environ["HASH_SALT"].strip(),
        fernet_key=os.environ["FERNET_KEY"].strip(),
        retention_days=positive_int("RETENTION_DAYS", 30),
        max_hour=positive_int("MAX_APPEALS_PER_HOUR", 10),
        max_day=positive_int("MAX_APPEALS_PER_DAY", 30),
        max_appeals_per_hour=positive_int("MAX_APPEALS_PER_HOUR", 10),
        max_appeals_per_day=positive_int("MAX_APPEALS_PER_DAY", 30),
        db_path=os.getenv("DB_PATH", "data/bot.db").strip(),
        database_url=(
            os.getenv("DATABASE_URL", "").strip().replace("postgres://", "postgresql://", 1)
            or None
        ),
    )


def fail_config() -> None:
    try:
        load_settings()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
