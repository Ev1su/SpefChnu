import asyncio
import os
import time
from datetime import UTC, datetime, timedelta

import aiosqlite

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS appeals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_hash TEXT NOT NULL,
    chat_id_enc TEXT NOT NULL,
    username TEXT,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    urgent INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',
    responsible TEXT,
    delivery INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS appeal_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appeal_id INTEGER NOT NULL,
    direction TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_id TEXT,
    text TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS join_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id_enc TEXT NOT NULL,
    username TEXT,
    full_name_enc TEXT NOT NULL,
    birth_date_enc TEXT NOT NULL,
    phone_enc TEXT NOT NULL,
    group_name TEXT NOT NULL,
    instagram TEXT,
    telegram TEXT NOT NULL,
    motivation TEXT NOT NULL,
    experience TEXT,
    hours INTEGER NOT NULL,
    consent INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',
    responsible TEXT,
    delivery INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK(kind IN ('appeal','application')),
    item_id INTEGER NOT NULL,
    admin_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    UNIQUE(kind,item_id,admin_id)
);
CREATE TABLE IF NOT EXISTS admin_msg_map (
    admin_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('appeal','application')),
    item_id INTEGER NOT NULL,
    UNIQUE(admin_id,message_id)
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK(kind IN ('appeal','application')),
    item_id INTEGER NOT NULL,
    admin_name TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (
    user_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_appeals_hash ON appeals(user_hash);
CREATE INDEX IF NOT EXISTS idx_appeals_status ON appeals(status);
CREATE INDEX IF NOT EXISTS idx_join_status ON join_applications(status);
CREATE INDEX IF NOT EXISTS idx_admin_cards ON admin_cards(kind,item_id);
CREATE INDEX IF NOT EXISTS idx_admin_map ON admin_msg_map(admin_id,message_id);
CREATE INDEX IF NOT EXISTS idx_rate_limits ON rate_limits(user_hash,kind,created_at);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn: aiosqlite.Connection | None = None
        self.lock = asyncio.Lock()

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.executescript(SCHEMA)
        cur = await self.conn.execute("PRAGMA table_info(join_applications)")
        columns = {row[1] for row in await cur.fetchall()}
        if "username" not in columns:
            await self.conn.execute("ALTER TABLE join_applications ADD COLUMN username TEXT")
        cur = await self.conn.execute("PRAGMA table_info(appeals)")
        appeal_columns = {row[1] for row in await cur.fetchall()}
        if "username" not in appeal_columns:
            await self.conn.execute("ALTER TABLE appeals ADD COLUMN username TEXT")
        await self.conn.commit()
        cur = await self.conn.execute("SELECT COUNT(*) FROM schema_version")
        count = (await cur.fetchone())[0]
        if count == 0:
            await self.conn.execute("INSERT INTO schema_version(version) VALUES (1)")
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")

    async def execute(self, sql: str, params: tuple = ()) -> None:
        async with self.lock:
            await self.conn.execute(sql, params)
            await self.conn.commit()

    async def create_appeal(self, user_hash: str, chat_id_enc: str, category: str, description: str, urgent: bool, username: str | None = None) -> int:
        now = self.now()
        async with self.lock:
            cur = await self.conn.execute(
                "INSERT INTO appeals(user_hash,chat_id_enc,username,category,description,urgent,status,delivery,created_at,updated_at) VALUES(?,?,?,?,?,?, 'new',0,?,?)",
                (user_hash, chat_id_enc, username, category, description, int(urgent), now, now),
            )
            await self.conn.commit()
            return int(cur.lastrowid)

    async def add_appeal_message(self, appeal_id: int, direction: str, content_type: str, file_id: str | None = None, text: str | None = None) -> None:
        await self.execute("INSERT INTO appeal_messages(appeal_id,direction,content_type,file_id,text,created_at) VALUES(?,?,?,?,?,?)",
                           (appeal_id, direction, content_type, file_id, text, self.now()))

    async def get_appeal(self, appeal_id: int):
        async with self.lock:
            cur = await self.conn.execute("SELECT * FROM appeals WHERE id=?", (appeal_id,))
            return await cur.fetchone()

    async def get_appeals_by_hash(self, user_hash: str, limit: int = 10):
        async with self.lock:
            cur = await self.conn.execute("SELECT * FROM appeals WHERE user_hash=? ORDER BY id DESC LIMIT ?", (user_hash, limit))
            return await cur.fetchall()

    async def get_open_appeals_by_hash(self, user_hash: str):
        async with self.lock:
            cur = await self.conn.execute("SELECT * FROM appeals WHERE user_hash=? AND status NOT IN ('resolved','closed') ORDER BY id DESC", (user_hash,))
            return await cur.fetchall()

    async def set_appeal_status(self, appeal_id: int, status: str, responsible: str | None = None) -> bool:
        async with self.lock:
            cur = await self.conn.execute("SELECT status FROM appeals WHERE id=?", (appeal_id,))
            row = await cur.fetchone()
            if not row:
                return False
            if row[0] == status:
                if responsible:
                    await self.conn.execute("UPDATE appeals SET responsible=?, updated_at=? WHERE id=?", (responsible, self.now(), appeal_id))
                    await self.conn.commit()
                    return True
                return False
            await self.conn.execute("UPDATE appeals SET status=?, responsible=COALESCE(?,responsible), updated_at=? WHERE id=?",
                                    (status, responsible, self.now(), appeal_id))
            await self.conn.commit()
            return True

    async def set_appeal_delivery(self, appeal_id: int, delivered: bool) -> None:
        await self.execute("UPDATE appeals SET delivery=? WHERE id=?", (1 if delivered else 0, appeal_id))

    async def get_pending_appeals(self):
        async with self.lock:
            cur = await self.conn.execute("SELECT * FROM appeals WHERE delivery=0")
            return await cur.fetchall()

    async def create_join_application(self, data: dict) -> int:
        now = self.now()
        sql = """INSERT INTO join_applications(user_id_enc,username,full_name_enc,birth_date_enc,phone_enc,group_name,instagram,telegram,motivation,experience,hours,consent,status,delivery,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?, ?, 'new', 0, ?, ?)"""
        params = (data["user_id_enc"], data.get("username"), data["full_name_enc"], data["birth_date_enc"], data["phone_enc"], data["group_name"],
                  data["instagram"], data["telegram"], data["motivation"], data["experience"], data["hours"], 1, now, now)
        async with self.lock:
            cur = await self.conn.execute(sql, params)
            await self.conn.commit()
            return int(cur.lastrowid)

    async def get_join_application(self, application_id: int):
        async with self.lock:
            cur = await self.conn.execute("SELECT * FROM join_applications WHERE id=?", (application_id,))
            return await cur.fetchone()

    async def count_join_limits(self, user_id_enc: str) -> tuple[int, int]:
        async with self.lock:
            cur = await self.conn.execute("SELECT COUNT(*) FROM join_applications WHERE user_id_enc=? AND status NOT IN ('accepted','rejected')", (user_id_enc,))
            active = (await cur.fetchone())[0]
            cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat(timespec="seconds")
            cur = await self.conn.execute("SELECT COUNT(*) FROM join_applications WHERE user_id_enc=? AND status='new' AND created_at>?", (user_id_enc, cutoff))
            recent = (await cur.fetchone())[0]
            return active, recent

    async def set_join_status(self, application_id: int, status: str, responsible: str | None = None) -> bool:
        async with self.lock:
            cur = await self.conn.execute("SELECT status FROM join_applications WHERE id=?", (application_id,))
            row = await cur.fetchone()
            if not row:
                return False
            if row[0] == status:
                if responsible:
                    await self.conn.execute("UPDATE join_applications SET responsible=?, updated_at=? WHERE id=?", (responsible, self.now(), application_id))
                    await self.conn.commit()
                    return True
                return False
            await self.conn.execute("UPDATE join_applications SET status=?, responsible=COALESCE(?,responsible), updated_at=? WHERE id=?",
                                    (status, responsible, self.now(), application_id))
            await self.conn.commit()
            return True

    async def set_join_delivery(self, application_id: int, delivered: bool) -> None:
        await self.execute("UPDATE join_applications SET delivery=? WHERE id=?", (1 if delivered else 0, application_id))

    async def get_pending_join_applications(self):
        async with self.lock:
            cur = await self.conn.execute("SELECT * FROM join_applications WHERE delivery=0")
            return await cur.fetchall()

    async def add_admin_card(self, kind: str, item_id: int, admin_id: int, message_id: int) -> None:
        await self.execute("INSERT OR REPLACE INTO admin_cards(kind,item_id,admin_id,message_id) VALUES(?,?,?,?)", (kind, item_id, admin_id, message_id))

    async def get_admin_cards(self, kind: str, item_id: int):
        async with self.lock:
            cur = await self.conn.execute("SELECT * FROM admin_cards WHERE kind=? AND item_id=?", (kind, item_id))
            return await cur.fetchall()

    async def add_admin_msg_map(self, admin_id: int, message_id: int, kind: str, item_id: int) -> None:
        await self.execute("INSERT OR IGNORE INTO admin_msg_map(admin_id,message_id,kind,item_id) VALUES(?,?,?,?)", (admin_id, message_id, kind, item_id))

    async def get_admin_msg_item(self, admin_id: int, message_id: int):
        async with self.lock:
            cur = await self.conn.execute("SELECT kind,item_id FROM admin_msg_map WHERE admin_id=? AND message_id=? LIMIT 1", (admin_id, message_id))
            return await cur.fetchone()

    async def add_note(self, kind: str, item_id: int, admin_name: str, text: str) -> None:
        await self.execute("INSERT INTO notes(kind,item_id,admin_name,text,created_at) VALUES(?,?,?,?,?)", (kind, item_id, admin_name, text, self.now()))

    async def get_notes(self, kind: str, item_id: int):
        async with self.lock:
            cur = await self.conn.execute("SELECT * FROM notes WHERE kind=? AND item_id=? ORDER BY id DESC LIMIT 10", (kind, item_id))
            return await cur.fetchall()

    async def list_items(self, kind: str, status: str | None = None, offset: int = 0, limit: int = 8):
        table = "appeals" if kind == "appeal" else "join_applications"
        params: tuple
        if status and status != "all":
            sql = f"SELECT * FROM {table} WHERE status=? ORDER BY id DESC LIMIT ? OFFSET ?"
            params = (status, limit, offset)
        else:
            sql = f"SELECT * FROM {table} ORDER BY id DESC LIMIT ? OFFSET ?"
            params = (limit, offset)
        async with self.lock:
            cur = await self.conn.execute(sql, params)
            return await cur.fetchall()

    async def check_appeal_limits(self, user_hash: str, max_hour: int, max_day: int) -> bool:
        async with self.lock:
            now = time.time()
            await self.conn.execute("DELETE FROM rate_limits WHERE created_at<=?", (now - 86400,))
            cur = await self.conn.execute("SELECT COUNT(*) FROM rate_limits WHERE user_hash=? AND kind='hour' AND created_at>?", (user_hash, now - 3600))
            hour = (await cur.fetchone())[0]
            cur = await self.conn.execute("SELECT COUNT(*) FROM rate_limits WHERE user_hash=? AND kind='day' AND created_at>?", (user_hash, now - 86400))
            day = (await cur.fetchone())[0]
            await self.conn.commit()
            return hour < max_hour and day < max_day

    async def record_appeal_limit(self, user_hash: str) -> None:
        now = time.time()
        async with self.lock:
            await self.conn.execute("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(?,?,?)", (user_hash, "hour", now))
            await self.conn.execute("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(?,?,?)", (user_hash, "day", now))
            await self.conn.commit()

    async def consume_appeal_slot(self, user_hash: str, max_hour: int, max_day: int) -> bool:
        async with self.lock:
            now = time.time()
            await self.conn.execute("DELETE FROM rate_limits WHERE created_at<=?", (now - 86400,))
            cur = await self.conn.execute("SELECT COUNT(*) FROM rate_limits WHERE user_hash=? AND kind='hour' AND created_at>?", (user_hash, now - 3600))
            hour = int((await cur.fetchone())[0])
            cur = await self.conn.execute("SELECT COUNT(*) FROM rate_limits WHERE user_hash=? AND kind='day' AND created_at>?", (user_hash, now - 86400))
            day = int((await cur.fetchone())[0])
            if hour >= max_hour or day >= max_day:
                await self.conn.commit()
                return False
            await self.conn.execute("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(?,?,?)", (user_hash, "hour", now))
            await self.conn.execute("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(?,?,?)", (user_hash, "day", now))
            await self.conn.commit()
            return True

    async def cleanup(self, retention_days: int) -> tuple[list[int], list[int]]:
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat(timespec="seconds")
        async with self.lock:
            cur = await self.conn.execute("SELECT id FROM appeals WHERE status IN ('resolved','closed') AND updated_at<?", (cutoff,))
            appeal_ids = [int(row[0]) for row in await cur.fetchall()]
            cur = await self.conn.execute("SELECT id FROM join_applications WHERE status IN ('accepted','rejected') AND updated_at<?", (cutoff,))
            join_ids = [int(row[0]) for row in await cur.fetchall()]
            for item_id in appeal_ids:
                await self.conn.execute("DELETE FROM appeal_messages WHERE appeal_id=?", (item_id,))
                await self.conn.execute("DELETE FROM notes WHERE kind='appeal' AND item_id=?", (item_id,))
                await self.conn.execute("DELETE FROM admin_cards WHERE kind='appeal' AND item_id=?", (item_id,))
                await self.conn.execute("DELETE FROM admin_msg_map WHERE kind='appeal' AND item_id=?", (item_id,))
                await self.conn.execute("DELETE FROM appeals WHERE id=?", (item_id,))
            for item_id in join_ids:
                await self.conn.execute("DELETE FROM notes WHERE kind='application' AND item_id=?", (item_id,))
                await self.conn.execute("DELETE FROM admin_cards WHERE kind='application' AND item_id=?", (item_id,))
                await self.conn.execute("DELETE FROM admin_msg_map WHERE kind='application' AND item_id=?", (item_id,))
                await self.conn.execute("DELETE FROM join_applications WHERE id=?", (item_id,))
            await self.conn.execute("DELETE FROM rate_limits WHERE created_at<?", (time.time() - 604800,))
            await self.conn.commit()
            return appeal_ids, join_ids

    async def stats(self) -> dict[str, int]:
        async with self.lock:
            result: dict[str, int] = {}
            now = datetime.now(UTC)
            cutoff7 = (now - timedelta(days=7)).isoformat(timespec="seconds")
            cutoff30 = (now - timedelta(days=30)).isoformat(timespec="seconds")

            for status in ("new", "working", "resolved", "closed"):
                cur = await self.conn.execute("SELECT COUNT(*) FROM appeals WHERE status=?", (status,))
                result[f"appeal_{status}"] = int((await cur.fetchone())[0])
            cur = await self.conn.execute("SELECT COUNT(*) FROM appeals WHERE created_at>=?", (cutoff7,))
            result["appeal_7"] = int((await cur.fetchone())[0])
            cur = await self.conn.execute("SELECT COUNT(*) FROM appeals WHERE created_at>=?", (cutoff30,))
            result["appeal_30"] = int((await cur.fetchone())[0])
            cur = await self.conn.execute("SELECT COUNT(*) FROM appeals WHERE urgent=1 AND status NOT IN ('resolved','closed')")
            result["appeal_urgent_open"] = int((await cur.fetchone())[0])
            cur = await self.conn.execute("SELECT COUNT(*) FROM appeals WHERE delivery=0")
            result["appeal_undelivered"] = int((await cur.fetchone())[0])

            for status in ("new", "review", "accepted", "rejected"):
                cur = await self.conn.execute("SELECT COUNT(*) FROM join_applications WHERE status=?", (status,))
                result[f"join_{status}"] = int((await cur.fetchone())[0])
            cur = await self.conn.execute("SELECT COUNT(*) FROM join_applications WHERE created_at>=?", (cutoff7,))
            result["join_7"] = int((await cur.fetchone())[0])
            cur = await self.conn.execute("SELECT COUNT(*) FROM join_applications WHERE created_at>=?", (cutoff30,))
            result["join_30"] = int((await cur.fetchone())[0])
            cur = await self.conn.execute("SELECT COUNT(*) FROM join_applications WHERE delivery=0")
            result["join_undelivered"] = int((await cur.fetchone())[0])
            return result
