import json
import sqlite3
from datetime import UTC, datetime, timedelta


class ConversationMemory:
    def __init__(self, path, retention_days=7, max_turns=6):
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.execute("PRAGMA secure_delete=ON")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS conversation (
            id INTEGER PRIMARY KEY, created TEXT NOT NULL, user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL)""")
        self.days, self.max_turns = retention_days, max_turns
        self.purge()

    def purge(self):
        cutoff = (datetime.now(UTC) - timedelta(days=self.days)).isoformat()
        with self.connection:
            self.connection.execute("DELETE FROM conversation WHERE created < ?", (cutoff,))
            self.connection.execute(
                "DELETE FROM conversation WHERE id NOT IN "
                "(SELECT id FROM conversation ORDER BY id DESC LIMIT ?)",
                (self.max_turns,),
            )

    def remember(self, user_text, assistant_text):
        with self.connection:
            self.connection.execute(
                "INSERT INTO conversation(created,user_text,assistant_text) VALUES(?,?,?)",
                (datetime.now(UTC).isoformat(), user_text[:12000], assistant_text[:12000]),
            )
        self.purge()

    def messages(self, max_bytes=4000):
        self.purge()
        rows = self.connection.execute(
            "SELECT user_text,assistant_text FROM conversation ORDER BY id DESC LIMIT ?",
            (self.max_turns,),
        ).fetchall()
        messages = []
        for user, assistant in rows:
            pair = [
                {"role": "user", "content": [{"text": user}]},
                {"role": "assistant", "content": [{"text": assistant}]},
            ]
            candidate = pair + messages
            if len(json.dumps(candidate, ensure_ascii=False).encode("utf-8")) > max_bytes:
                break
            messages = candidate
        return messages

    def clear(self):
        with self.connection:
            self.connection.execute("DELETE FROM conversation")
        self.connection.execute("VACUUM")

    def close(self):
        self.connection.close()
