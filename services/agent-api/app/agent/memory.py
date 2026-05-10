import json
import time
from pathlib import Path
from typing import Any


class SessionMemory:
    def __init__(self, db_path: str = "data/memory.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def _ensure_db(self) -> None:
        if self._initialized:
            return
        import aiosqlite

        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT DEFAULT '',
                created_at REAL DEFAULT (strftime('%s', 'now')),
                updated_at REAL DEFAULT (strftime('%s', 'now')),
                history TEXT DEFAULT '[]',
                context TEXT DEFAULT '{}'
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                preferences TEXT DEFAULT '{}',
                body_info TEXT DEFAULT '{}',
                interactions TEXT DEFAULT '[]',
                created_at REAL DEFAULT (strftime('%s', 'now')),
                updated_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)
        await self._db.commit()
        self._initialized = True

    async def load_session(self, session_id: str) -> dict[str, Any]:
        await self._ensure_db()
        cursor = await self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if row:
            return {
                "id": row["id"],
                "user_id": row["user_id"],
                "history": json.loads(row["history"]),
                "context": json.loads(row["context"]),
            }
        return {"id": session_id, "user_id": "", "history": [], "context": {}}

    async def save_session(self, session_id: str, history: list, context: dict, user_id: str = "") -> None:
        await self._ensure_db()
        await self._db.execute(
            """INSERT OR REPLACE INTO sessions (id, user_id, history, context, updated_at)
               VALUES (?, ?, ?, ?, strftime('%s', 'now'))""",
            (session_id, user_id, json.dumps(history, ensure_ascii=False), json.dumps(context, ensure_ascii=False)),
        )
        await self._db.commit()

    async def load_user_profile(self, user_id: str) -> dict[str, Any]:
        await self._ensure_db()
        cursor = await self._db.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return {
                "user_id": row["user_id"],
                "preferences": json.loads(row["preferences"]),
                "body_info": json.loads(row["body_info"]),
                "interactions": json.loads(row["interactions"]),
            }
        return {"user_id": user_id, "preferences": {}, "body_info": {}, "interactions": []}

    async def update_user_profile(self, user_id: str, updates: dict[str, Any]) -> None:
        await self._ensure_db()
        profile = await self.load_user_profile(user_id)
        profile["preferences"].update(updates)
        profile["interactions"].append({"ts": time.time(), "updates": updates})
        profile["interactions"] = profile["interactions"][-50:]
        await self._db.execute(
            """INSERT OR REPLACE INTO user_profiles (user_id, preferences, body_info, interactions, updated_at)
               VALUES (?, ?, ?, ?, strftime('%s', 'now'))""",
            (user_id, json.dumps(profile["preferences"], ensure_ascii=False),
             json.dumps(profile["body_info"], ensure_ascii=False),
             json.dumps(profile["interactions"], ensure_ascii=False)),
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._initialized:
            await self._db.close()
            self._initialized = False
