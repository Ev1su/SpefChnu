import asyncio
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence

import aiosqlite
from sqlalchemy import MetaData, Table, Column, Integer, BigInteger, Text, Boolean, Float, String, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine


class RowMapping(Mapping[str, Any], Sequence[Any]):
    """Mapping row with integer indexing for backward compatibility."""

    def __init__(self, values: Mapping[str, Any]):
        self._mapping = dict(values)
        self._keys = tuple(self._mapping.keys())
        self._values = tuple(self._mapping.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)


metadata = MetaData()
admins = Table("admins", metadata,
    Column("admin_id", BigInteger, primary_key=True),
    Column("added_by", BigInteger, nullable=False), Column("created_at", Text, nullable=False))
appeals = Table("appeals", metadata,
    Column("id", Integer, primary_key=True), Column("user_hash", Text, nullable=False),
    Column("chat_id_enc", Text, nullable=False), Column("username", Text), Column("category", Text, nullable=False),
    Column("description", Text, nullable=False), Column("urgent", Boolean, nullable=False, server_default="false"),
    Column("status", Text, nullable=False, server_default="new"), Column("responsible", Text),
    Column("delivery", Boolean, nullable=False, server_default="false"), Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False))
appeal_messages = Table("appeal_messages", metadata,
    Column("id", Integer, primary_key=True), Column("appeal_id", Integer, nullable=False),
    Column("direction", Text, nullable=False), Column("content_type", Text, nullable=False),
    Column("file_id", Text), Column("text", Text), Column("created_at", Text, nullable=False))
join_applications = Table("join_applications", metadata,
    Column("id", Integer, primary_key=True), Column("user_id_enc", Text, nullable=False), Column("username", Text),
    Column("full_name_enc", Text, nullable=False), Column("birth_date_enc", Text, nullable=False), Column("phone_enc", Text, nullable=False),
    Column("group_name", Text, nullable=False), Column("instagram", Text), Column("telegram", Text, nullable=False),
    Column("motivation", Text, nullable=False), Column("experience", Text), Column("hours", Integer, nullable=False),
    Column("consent", Boolean, nullable=False, server_default="false"), Column("status", Text, nullable=False, server_default="new"),
    Column("responsible", Text), Column("delivery", Boolean, nullable=False, server_default="false"),
    Column("created_at", Text, nullable=False), Column("updated_at", Text, nullable=False))
admin_cards = Table("admin_cards", metadata,
    Column("id", Integer, primary_key=True), Column("kind", Text, nullable=False), Column("item_id", Integer, nullable=False),
    Column("admin_id", BigInteger, nullable=False), Column("message_id", BigInteger, nullable=False))
admin_msg_map = Table("admin_msg_map", metadata,
    Column("admin_id", BigInteger, nullable=False), Column("message_id", BigInteger, nullable=False),
    Column("kind", Text, nullable=False), Column("item_id", Integer, nullable=False))
notes = Table("notes", metadata,
    Column("id", Integer, primary_key=True), Column("kind", Text, nullable=False), Column("item_id", Integer, nullable=False),
    Column("admin_name", Text, nullable=False), Column("text", Text, nullable=False), Column("created_at", Text, nullable=False))
rate_limits = Table("rate_limits", metadata,
    Column("user_hash", Text, nullable=False), Column("kind", Text, nullable=False), Column("created_at", Float, nullable=False))
schema_version = Table("schema_version", metadata, Column("version", Integer, nullable=False))


SQLITE_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY, added_by INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS appeals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_hash TEXT NOT NULL, chat_id_enc TEXT NOT NULL, username TEXT, category TEXT NOT NULL, description TEXT NOT NULL, urgent INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'new', responsible TEXT, delivery INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS appeal_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, appeal_id INTEGER NOT NULL, direction TEXT NOT NULL, content_type TEXT NOT NULL, file_id TEXT, text TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS join_applications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id_enc TEXT NOT NULL, username TEXT, full_name_enc TEXT NOT NULL, birth_date_enc TEXT NOT NULL, phone_enc TEXT NOT NULL, group_name TEXT NOT NULL, instagram TEXT, telegram TEXT NOT NULL, motivation TEXT NOT NULL, experience TEXT, hours INTEGER NOT NULL, consent INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'new', responsible TEXT, delivery INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admin_cards (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL CHECK(kind IN ('appeal','application')), item_id INTEGER NOT NULL, admin_id INTEGER NOT NULL, message_id INTEGER NOT NULL, UNIQUE(kind,item_id,admin_id));
CREATE TABLE IF NOT EXISTS admin_msg_map (admin_id INTEGER NOT NULL, message_id INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('appeal','application')), item_id INTEGER NOT NULL, UNIQUE(admin_id,message_id));
CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL CHECK(kind IN ('appeal','application')), item_id INTEGER NOT NULL, admin_name TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rate_limits (user_hash TEXT NOT NULL, kind TEXT NOT NULL, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_appeals_hash ON appeals(user_hash); CREATE INDEX IF NOT EXISTS idx_appeals_status ON appeals(status); CREATE INDEX IF NOT EXISTS idx_join_status ON join_applications(status); CREATE INDEX IF NOT EXISTS idx_admin_cards ON admin_cards(kind,item_id); CREATE INDEX IF NOT EXISTS idx_admin_map ON admin_msg_map(admin_id,message_id); CREATE INDEX IF NOT EXISTS idx_rate_limits ON rate_limits(user_hash,kind,created_at);
"""


def normalize_database_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class Database:
    def __init__(self, path: str, database_url: str | None = None):
        self.path = path
        self.database_url = normalize_database_url(database_url)
        self.backend = "postgresql" if self.database_url else "sqlite"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn: aiosqlite.Connection | None = None
        self.engine: AsyncEngine | None = None
        self.lock = asyncio.Lock()

    async def connect(self) -> None:
        if self.backend == "postgresql":
            self.engine = create_async_engine(self.database_url, pool_pre_ping=True)
            async with self.engine.begin() as connection:
                await connection.run_sync(metadata.create_all)
            return
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.executescript(SQLITE_SCHEMA)
        await self._migrate_sqlite_usernames()
        cur = await self.conn.execute("SELECT COUNT(*) FROM schema_version")
        if (await cur.fetchone())[0] == 0:
            await self.conn.execute("INSERT INTO schema_version(version) VALUES(1)")
        await self.conn.commit()

    async def _migrate_sqlite_usernames(self) -> None:
        for table in ("join_applications", "appeals"):
            cur = await self.conn.execute(f"PRAGMA table_info({table})")
            if "username" not in {row[1] for row in await cur.fetchall()}:
                await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN username TEXT")

    async def close(self) -> None:
        if self.conn:
            await self.conn.close(); self.conn = None
        if self.engine:
            await self.engine.dispose(); self.engine = None

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")

    def _postgres_params(self, params: tuple | list | dict) -> dict:
        if isinstance(params, dict): return params
        return {str(i): value for i, value in enumerate(params)}

    async def _pg_execute(self, statement: str, params: tuple = ()) -> Any:
        if isinstance(params, tuple):
            params = {str(i): value for i, value in enumerate(params)}
        async with self.engine.begin() as connection:
            return await connection.execute(text(statement), params)

    def _row(self, row: Any) -> RowMapping | None:
        if row is None: return None
        if isinstance(row, RowMapping): return row
        if hasattr(row, "_mapping"):
            return RowMapping(dict(row._mapping.items()))
        if isinstance(row, Mapping): return RowMapping(row)
        if hasattr(row, "keys"):
            keys = tuple(row.keys())
            return RowMapping({key: row[key] for key in keys})
        return RowMapping({str(i): value for i, value in enumerate(tuple(row))})

    async def _all(self, statement: str, params: tuple = ()) -> list[RowMapping]:
        if self.backend == "sqlite":
            async with self.lock:
                cur = await self.conn.execute(statement, params)
                return [self._row(row) for row in await cur.fetchall()]
        async with self.engine.connect() as connection:
            result = await connection.execute(text(statement), self._postgres_params(params))
            return [self._row(row) for row in result.fetchall()]

    async def _one(self, statement: str, params: tuple = ()) -> RowMapping | None:
        if self.backend == "sqlite":
            async with self.lock:
                cur = await self.conn.execute(statement, params)
                return self._row(await cur.fetchone())
        async with self.engine.connect() as connection:
            result = await connection.execute(text(statement), self._postgres_params(params))
            return self._row(result.fetchone())

    def _sql(self, statement: str) -> str:
        if self.backend == "postgresql":
            import re
            i = 0
            def repl(_match):
                nonlocal i
                value = str(i); i += 1
                return ":" + value
            return re.sub(r"\?", repl, statement)
        return statement

    async def sync_initial_admins(self, admin_ids: tuple[int, ...]) -> None:
        async with self.lock:
            if self.backend == "sqlite":
                for admin_id in admin_ids:
                    await self.conn.execute("INSERT OR IGNORE INTO admins(admin_id,added_by,created_at) VALUES(?,?,?)", (admin_id, admin_id, self.now()))
                await self.conn.commit()
            else:
                async with self.engine.begin() as connection:
                    for admin_id in admin_ids:
                        await connection.execute(text("INSERT INTO admins(admin_id,added_by,created_at) VALUES (:0,:1,:2) ON CONFLICT(admin_id) DO NOTHING"), {"0": admin_id, "1": admin_id, "2": self.now()})

    async def add_admin(self, admin_id: int, added_by: int) -> bool:
        if admin_id <= 0: return False
        async with self.lock:
            if self.backend == "sqlite":
                cur = await self.conn.execute("INSERT OR IGNORE INTO admins(admin_id,added_by,created_at) VALUES(?,?,?)", (admin_id, added_by, self.now()))
                await self.conn.commit(); return cur.rowcount == 1
            async with self.engine.begin() as connection:
                result = await connection.execute(text("INSERT INTO admins(admin_id,added_by,created_at) VALUES (:0,:1,:2) ON CONFLICT(admin_id) DO NOTHING"), {"0": admin_id, "1": added_by, "2": self.now()})
                return result.rowcount == 1

    async def list_admins(self) -> tuple[int, ...]:
        rows = await self._all("SELECT admin_id FROM admins ORDER BY admin_id")
        return tuple(int(row[0]) for row in rows)

    async def execute(self, sql: str, params: tuple = ()) -> None:
        async with self.lock:
            if self.backend == "sqlite":
                await self.conn.execute(sql, params); await self.conn.commit()
            else:
                await self._pg_execute(self._sql(sql), params)

    async def create_appeal(self, user_hash: str, chat_id_enc: str, category: str, description: str, urgent: bool, username: str | None = None) -> int:
        now = self.now(); sql = "INSERT INTO appeals(user_hash,chat_id_enc,username,category,description,urgent,status,delivery,created_at,updated_at) VALUES(?,?,?,?,?,?, 'new',0,?,?)"
        params = (user_hash, chat_id_enc, username, category, description, int(urgent), now, now)
        async with self.lock:
            if self.backend == "sqlite":
                cur = await self.conn.execute(sql, params); await self.conn.commit(); return int(cur.lastrowid)
            async with self.engine.begin() as connection:
                result = await connection.execute(text("INSERT INTO appeals(user_hash,chat_id_enc,username,category,description,urgent,status,delivery,created_at,updated_at) VALUES (:0,:1,:2,:3,:4,:5,'new',false,:6,:7) RETURNING id"), {str(i): v for i,v in enumerate(params)})
                return int(result.scalar_one())

    async def add_appeal_message(self, appeal_id: int, direction: str, content_type: str, file_id: str | None = None, text_value: str | None = None) -> None:
        await self.execute("INSERT INTO appeal_messages(appeal_id,direction,content_type,file_id,text,created_at) VALUES(?,?,?,?,?,?)", (appeal_id, direction, content_type, file_id, text_value, self.now()))

    async def get_appeal(self, appeal_id: int): return await self._one(self._sql("SELECT * FROM appeals WHERE id=?"), (appeal_id,))
    async def get_appeals_by_hash(self, user_hash: str, limit: int = 10): return await self._all(self._sql("SELECT * FROM appeals WHERE user_hash=? ORDER BY id DESC LIMIT ?"), (user_hash, limit))
    async def get_open_appeals_by_hash(self, user_hash: str): return await self._all(self._sql("SELECT * FROM appeals WHERE user_hash=? AND status NOT IN ('resolved','closed') ORDER BY id DESC"), (user_hash,))

    async def set_appeal_status(self, appeal_id: int, status: str, responsible: str | None = None) -> bool:
        async with self.lock:
            if self.backend == "sqlite":
                cur = await self.conn.execute("SELECT status FROM appeals WHERE id=?", (appeal_id,)); row = await cur.fetchone()
                if not row: return False
                if row[0] == status:
                    if responsible:
                        await self.conn.execute("UPDATE appeals SET responsible=?, updated_at=? WHERE id=?", (responsible,self.now(),appeal_id)); await self.conn.commit(); return True
                    return False
                await self.conn.execute("UPDATE appeals SET status=?, responsible=COALESCE(?,responsible), updated_at=? WHERE id=?", (status,responsible,self.now(),appeal_id)); await self.conn.commit(); return True
            async with self.engine.begin() as connection:
                row = (await connection.execute(text("SELECT status FROM appeals WHERE id=:0"), {"0":appeal_id})).first()
                if not row: return False
                if row[0] == status:
                    if responsible:
                        await connection.execute(text("UPDATE appeals SET responsible=:0,updated_at=:1 WHERE id=:2"), {"0":responsible,"1":self.now(),"2":appeal_id}); return True
                    return False
                await connection.execute(text("UPDATE appeals SET status=:0,responsible=COALESCE(:1,responsible),updated_at=:2 WHERE id=:3"), {"0":status,"1":responsible,"2":self.now(),"3":appeal_id}); return True

    async def set_appeal_delivery(self, appeal_id: int, delivered: bool) -> None:
        await self.execute("UPDATE appeals SET delivery=? WHERE id=?", (1 if delivered else 0, appeal_id))
    async def get_pending_appeals(self): return await self._all(self._sql("SELECT * FROM appeals WHERE delivery=?"), (0,))

    async def create_join_application(self, data: dict) -> int:
        now = self.now(); sql = "INSERT INTO join_applications(user_id_enc,username,full_name_enc,birth_date_enc,phone_enc,group_name,instagram,telegram,motivation,experience,hours,consent,status,delivery,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        params = (data["user_id_enc"],data.get("username"),data["full_name_enc"],data["birth_date_enc"],data["phone_enc"],data["group_name"],data["instagram"],data["telegram"],data["motivation"],data["experience"],data["hours"],1,"new",0,now,now)
        async with self.lock:
            if self.backend == "sqlite":
                cur = await self.conn.execute(sql, params); await self.conn.commit(); return int(cur.lastrowid)
            values = ",".join(f":{i}" for i in range(16))
            async with self.engine.begin() as connection:
                result = await connection.execute(text("INSERT INTO join_applications(user_id_enc,username,full_name_enc,birth_date_enc,phone_enc,group_name,instagram,telegram,motivation,experience,hours,consent,status,delivery,created_at,updated_at) VALUES(" + values + ") RETURNING id"), {str(i):v for i,v in enumerate(params)})
                return int(result.scalar_one())

    async def get_join_application(self, application_id: int): return await self._one(self._sql("SELECT * FROM join_applications WHERE id=?"), (application_id,))
    async def count_join_limits(self, user_id_enc: str) -> tuple[int,int]:
        cutoff=(datetime.now(UTC)-timedelta(days=7)).isoformat(timespec="seconds")
        active_row=await self._one(self._sql("SELECT COUNT(*) AS count FROM join_applications WHERE user_id_enc=? AND status NOT IN ('accepted','rejected')"),(user_id_enc,))
        recent_row=await self._one(self._sql("SELECT COUNT(*) AS count FROM join_applications WHERE user_id_enc=? AND status='new' AND created_at>?"),(user_id_enc,cutoff))
        return int(active_row[0]),int(recent_row[0])

    async def set_join_status(self, application_id: int, status: str, responsible: str | None = None) -> bool:
        async with self.lock:
            if self.backend == "sqlite":
                cur=await self.conn.execute("SELECT status FROM join_applications WHERE id=?",(application_id,));row=await cur.fetchone()
                if not row:return False
                if row[0]==status:
                    if responsible: await self.conn.execute("UPDATE join_applications SET responsible=?,updated_at=? WHERE id=?",(responsible,self.now(),application_id));await self.conn.commit();return True
                    return False
                await self.conn.execute("UPDATE join_applications SET status=?,responsible=COALESCE(?,responsible),updated_at=? WHERE id=?",(status,responsible,self.now(),application_id));await self.conn.commit();return True
            async with self.engine.begin() as connection:
                row=(await connection.execute(text("SELECT status FROM join_applications WHERE id=:0"),{"0":application_id})).first()
                if not row:return False
                if row[0]==status:
                    if responsible: await connection.execute(text("UPDATE join_applications SET responsible=:0,updated_at=:1 WHERE id=:2"),{"0":responsible,"1":self.now(),"2":application_id});return True
                    return False
                await connection.execute(text("UPDATE join_applications SET status=:0,responsible=COALESCE(:1,responsible),updated_at=:2 WHERE id=:3"),{"0":status,"1":responsible,"2":self.now(),"3":application_id});return True

    async def set_join_delivery(self, application_id: int, delivered: bool) -> None: await self.execute("UPDATE join_applications SET delivery=? WHERE id=?",(1 if delivered else 0,application_id))
    async def get_pending_join_applications(self): return await self._all(self._sql("SELECT * FROM join_applications WHERE delivery=?"),(0,))

    async def add_admin_card(self, kind: str,item_id:int,admin_id:int,message_id:int)->None:
        if self.backend=="sqlite": await self.execute("INSERT OR REPLACE INTO admin_cards(kind,item_id,admin_id,message_id) VALUES(?,?,?,?)",(kind,item_id,admin_id,message_id))
        else:
            async with self.engine.begin() as connection:
                await connection.execute(text("INSERT INTO admin_cards(kind,item_id,admin_id,message_id) VALUES(:0,:1,:2,:3) ON CONFLICT(kind,item_id,admin_id) DO UPDATE SET message_id=EXCLUDED.message_id"),{"0":kind,"1":item_id,"2":admin_id,"3":message_id})
    async def get_admin_cards(self,kind:str,item_id:int):return await self._all(self._sql("SELECT * FROM admin_cards WHERE kind=? AND item_id=?"),(kind,item_id))
    async def add_admin_msg_map(self,admin_id:int,message_id:int,kind:str,item_id:int)->None:
        if self.backend=="sqlite":await self.execute("INSERT OR IGNORE INTO admin_msg_map(admin_id,message_id,kind,item_id) VALUES(?,?,?,?)",(admin_id,message_id,kind,item_id))
        else:
            async with self.engine.begin() as connection:await connection.execute(text("INSERT INTO admin_msg_map(admin_id,message_id,kind,item_id) VALUES(:0,:1,:2,:3) ON CONFLICT(admin_id,message_id) DO NOTHING"),{"0":admin_id,"1":message_id,"2":kind,"3":item_id})
    async def get_admin_msg_item(self,admin_id:int,message_id:int):return await self._one(self._sql("SELECT kind,item_id FROM admin_msg_map WHERE admin_id=? AND message_id=? LIMIT 1"),(admin_id,message_id))
    async def add_note(self,kind:str,item_id:int,admin_name:str,text_value:str)->None:await self.execute("INSERT INTO notes(kind,item_id,admin_name,text,created_at) VALUES(?,?,?,?,?)",(kind,item_id,admin_name,text_value,self.now()))
    async def get_notes(self,kind:str,item_id:int):return await self._all(self._sql("SELECT * FROM notes WHERE kind=? AND item_id=? ORDER BY id DESC LIMIT 10"),(kind,item_id))

    async def list_items(self,kind:str,status:str|None=None,offset:int=0,limit:int=8):
        table="appeals" if kind=="appeal" else "join_applications"
        if status and status!="all":return await self._all(self._sql(f"SELECT * FROM {table} WHERE status=? ORDER BY id DESC LIMIT ? OFFSET ?"),(status,limit,offset))
        return await self._all(self._sql(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ? OFFSET ?"),(limit,offset))

    async def check_appeal_limits(self,user_hash:str,max_hour:int,max_day:int)->bool:
        async with self.lock:
            now=time.time()
            if self.backend=="sqlite":
                await self.conn.execute("DELETE FROM rate_limits WHERE created_at<=?",(now-86400,));cur=await self.conn.execute("SELECT COUNT(*) FROM rate_limits WHERE user_hash=? AND kind='hour' AND created_at>?",(user_hash,now-3600));hour=(await cur.fetchone())[0];cur=await self.conn.execute("SELECT COUNT(*) FROM rate_limits WHERE user_hash=? AND kind='day' AND created_at>?",(user_hash,now-86400));day=(await cur.fetchone())[0];await self.conn.commit();return hour<max_hour and day<max_day
            async with self.engine.begin() as connection:
                await connection.execute(text("DELETE FROM rate_limits WHERE created_at<=:0"),{"0":now-86400});hour=int((await connection.execute(text("SELECT COUNT(*) FROM rate_limits WHERE user_hash=:0 AND kind='hour' AND created_at>:1"),{"0":user_hash,"1":now-3600})).scalar());day=int((await connection.execute(text("SELECT COUNT(*) FROM rate_limits WHERE user_hash=:0 AND kind='day' AND created_at>:1"),{"0":user_hash,"1":now-86400})).scalar());return hour<max_hour and day<max_day

    async def record_appeal_limit(self,user_hash:str)->None:
        async with self.lock:
            now=time.time()
            if self.backend=="sqlite":await self.conn.execute("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(?,?,?)",(user_hash,"hour",now));await self.conn.execute("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(?,?,?)",(user_hash,"day",now));await self.conn.commit()
            else:
                async with self.engine.begin() as connection:await connection.execute(text("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(:0,'hour',:1),(:0,'day',:1)"),{"0":user_hash,"1":now})

    async def consume_appeal_slot(self,user_hash:str,max_hour:int,max_day:int)->bool:
        async with self.lock:
            now=time.time()
            if self.backend=="sqlite":
                await self.conn.execute("DELETE FROM rate_limits WHERE created_at<=?",(now-86400,));cur=await self.conn.execute("SELECT COUNT(*) FROM rate_limits WHERE user_hash=? AND kind='hour' AND created_at>?",(user_hash,now-3600));hour=int((await cur.fetchone())[0]);cur=await self.conn.execute("SELECT COUNT(*) FROM rate_limits WHERE user_hash=? AND kind='day' AND created_at>?",(user_hash,now-86400));day=int((await cur.fetchone())[0])
                if hour>=max_hour or day>=max_day:await self.conn.commit();return False
                await self.conn.execute("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(?,?,?)",(user_hash,"hour",now));await self.conn.execute("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(?,?,?)",(user_hash,"day",now));await self.conn.commit();return True
            async with self.engine.begin() as connection:
                await connection.execute(text("DELETE FROM rate_limits WHERE created_at<=:0"),{"0":now-86400});hour=int((await connection.execute(text("SELECT COUNT(*) FROM rate_limits WHERE user_hash=:0 AND kind='hour' AND created_at>:1"),{"0":user_hash,"1":now-3600})).scalar());day=int((await connection.execute(text("SELECT COUNT(*) FROM rate_limits WHERE user_hash=:0 AND kind='day' AND created_at>:1"),{"0":user_hash,"1":now-86400})).scalar())
                if hour>=max_hour or day>=max_day:return False
                await connection.execute(text("INSERT INTO rate_limits(user_hash,kind,created_at) VALUES(:0,'hour',:1),(:0,'day',:1)"),{"0":user_hash,"1":now});return True

    async def cleanup(self, retention_days: int) -> tuple[list[int], list[int]]:
        cutoff=(datetime.now(UTC)-timedelta(days=retention_days)).isoformat(timespec="seconds")
        async with self.lock:
            if self.backend=="sqlite":
                cur=await self.conn.execute("SELECT id FROM appeals WHERE status IN ('resolved','closed') AND updated_at<?",(cutoff,));appeal_ids=[int(row[0]) for row in await cur.fetchall()];cur=await self.conn.execute("SELECT id FROM join_applications WHERE status IN ('accepted','rejected') AND updated_at<?",(cutoff,));join_ids=[int(row[0]) for row in await cur.fetchall()]
                for item_id in appeal_ids:
                    for sql,params in (("DELETE FROM appeal_messages WHERE appeal_id=?",(item_id,)),("DELETE FROM notes WHERE kind='appeal' AND item_id=?",(item_id,)),("DELETE FROM admin_cards WHERE kind='appeal' AND item_id=?",(item_id,)),("DELETE FROM admin_msg_map WHERE kind='appeal' AND item_id=?",(item_id,)),("DELETE FROM appeals WHERE id=?",(item_id,))):await self.conn.execute(sql,params)
                for item_id in join_ids:
                    for sql,params in (("DELETE FROM notes WHERE kind='application' AND item_id=?",(item_id,)),("DELETE FROM admin_cards WHERE kind='application' AND item_id=?",(item_id,)),("DELETE FROM admin_msg_map WHERE kind='application' AND item_id=?",(item_id,)),("DELETE FROM join_applications WHERE id=?",(item_id,))):await self.conn.execute(sql,params)
                await self.conn.execute("DELETE FROM rate_limits WHERE created_at<?",(time.time()-604800,));await self.conn.commit();return appeal_ids,join_ids
            async with self.engine.begin() as connection:
                appeal_ids=[int(row[0]) for row in (await connection.execute(text("SELECT id FROM appeals WHERE status IN ('resolved','closed') AND updated_at<:0"),{"0":cutoff})).all()];join_ids=[int(row[0]) for row in (await connection.execute(text("SELECT id FROM join_applications WHERE status IN ('accepted','rejected') AND updated_at<:0"),{"0":cutoff})).all()]
                for item_id in appeal_ids:
                    await connection.execute(text("DELETE FROM appeal_messages WHERE appeal_id=:0; DELETE FROM notes WHERE kind='appeal' AND item_id=:0; DELETE FROM admin_cards WHERE kind='appeal' AND item_id=:0; DELETE FROM admin_msg_map WHERE kind='appeal' AND item_id=:0; DELETE FROM appeals WHERE id=:0"),{"0":item_id})
                for item_id in join_ids:
                    await connection.execute(text("DELETE FROM notes WHERE kind='application' AND item_id=:0; DELETE FROM admin_cards WHERE kind='application' AND item_id=:0; DELETE FROM admin_msg_map WHERE kind='application' AND item_id=:0; DELETE FROM join_applications WHERE id=:0"),{"0":item_id})
                await connection.execute(text("DELETE FROM rate_limits WHERE created_at<:0"),{"0":time.time()-604800})
                return appeal_ids,join_ids

    async def stats(self) -> dict[str,int]:
        result:dict[str,int]={};cutoff7=(datetime.now(UTC)-timedelta(days=7)).isoformat(timespec="seconds");cutoff30=(datetime.now(UTC)-timedelta(days=30)).isoformat(timespec="seconds")
        for status in ("new","working","resolved","closed"):
            row=await self._one(self._sql("SELECT COUNT(*) AS count FROM appeals WHERE status=?"),(status,));result[f"appeal_{status}"]=int(row[0])
        row=await self._one(self._sql("SELECT COUNT(*) AS count FROM appeals WHERE created_at>=?"),(cutoff7,));result["appeal_7"]=int(row[0]);row=await self._one(self._sql("SELECT COUNT(*) AS count FROM appeals WHERE created_at>=?"),(cutoff30,));result["appeal_30"]=int(row[0]);        row=await self._one("SELECT COUNT(*) AS count FROM appeals WHERE urgent=" + ("true" if self.backend == "postgresql" else "1") + " AND status NOT IN ('resolved','closed')");result["appeal_urgent_open"]=int(row[0]);row=await self._one(self._sql("SELECT COUNT(*) AS count FROM appeals WHERE delivery=?"),(0,));result["appeal_undelivered"]=int(row[0])
        for status in ("new","review","accepted","rejected"):
            row=await self._one(self._sql("SELECT COUNT(*) AS count FROM join_applications WHERE status=?"),(status,));result[f"join_{status}"]=int(row[0])
        row=await self._one(self._sql("SELECT COUNT(*) AS count FROM join_applications WHERE created_at>=?"),(cutoff7,));result["join_7"]=int(row[0]);row=await self._one(self._sql("SELECT COUNT(*) AS count FROM join_applications WHERE created_at>=?"),(cutoff30,));result["join_30"]=int(row[0]);row=await self._one(self._sql("SELECT COUNT(*) AS count FROM join_applications WHERE delivery=?"),(0,));result["join_undelivered"]=int(row[0]);return result
