import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class TaskStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=10)) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS research_tasks (
                    id TEXT PRIMARY KEY, created TEXT NOT NULL, updated TEXT NOT NULL,
                    topic TEXT NOT NULL, title TEXT NOT NULL, pages INTEGER NOT NULL,
                    status TEXT NOT NULL, sources TEXT NOT NULL DEFAULT '[]',
                    output_path TEXT NOT NULL DEFAULT '', message TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS message_attempts (
                    draft_id TEXT PRIMARY KEY, created TEXT NOT NULL, status TEXT NOT NULL);
            """)

    def create(self, topic, title, pages):
        identifier, now = uuid4().hex, datetime.now(UTC).isoformat()
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            connection.execute("INSERT INTO research_tasks(id,created,updated,topic,title,pages,status) "
                               "VALUES(?,?,?,?,?,?,?)", (identifier, now, now, topic, title, pages, "queued"))
        return identifier

    def update(self, identifier, status, sources=None, output_path=None, message=None):
        values = {"status": status, "updated": datetime.now(UTC).isoformat()}
        if sources is not None:
            values["sources"] = json.dumps(sources, ensure_ascii=False)
        if output_path is not None:
            values["output_path"] = str(output_path)
        if message is not None:
            values["message"] = str(message)[:2000]
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            connection.execute("UPDATE research_tasks SET " + ",".join(key + "=?" for key in values) +
                               " WHERE id=?", (*values.values(), identifier))

    def get(self, identifier):
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM research_tasks ORDER BY created DESC LIMIT 1").fetchone() if identifier == "latest" else connection.execute("SELECT * FROM research_tasks WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise ValueError("Tarefa não encontrada.")
            return dict(row)
    def claim_send(self, draft_id):
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            try:
                connection.execute("INSERT INTO message_attempts VALUES(?,?,?)",
                                   (draft_id, datetime.now(UTC).isoformat(), "attempted"))
            except sqlite3.IntegrityError as exc:
                raise RuntimeError("Esse envio já foi tentado. Confira a conversa antes de um novo pedido.") from exc

    def send_status(self, draft_id, status):
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            connection.execute("UPDATE message_attempts SET status=? WHERE draft_id=?", (status, draft_id))


def recent_tasks(path):
    path = Path(path)
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as connection:
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute("SELECT id,status,output_path,message,title FROM research_tasks "
                                      "ORDER BY created DESC LIMIT 20").fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]
