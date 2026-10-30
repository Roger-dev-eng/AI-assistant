"""Local action ledger and navigation references. Never store browser cookies or AWS settings."""

import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from assistant.core.intent_router import Action, normalize


def private_text(value):
    value = str(value)
    value = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[chave ocultada]", value)
    value = re.sub(
        r"(?i)(password|senha|secret|token|aws_secret_access_key)(%3a|%3d)[^&\s\"]+",
        r"\1\2[ocultado]", value,
    )
    return re.sub(
        r"(?i)(password|senha|secret|token|aws_secret_access_key)(\s*[:=]\s*)[^\s,;]+",
        r"\1\2[ocultado]", value,
    )[:4000]


class ActivityStore:
    def __init__(self, path, retention_days=30):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.days = retention_days
        with closing(self.connect()) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS command_history (
                    id INTEGER PRIMARY KEY, created TEXT NOT NULL, task_id TEXT NOT NULL,
                    command_text TEXT NOT NULL, normalized TEXT NOT NULL, tool TEXT NOT NULL,
                    arguments TEXT NOT NULL, status TEXT NOT NULL, result TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS command_history_created ON command_history(created);
                CREATE TABLE IF NOT EXISTS navigation_context (
                    site TEXT PRIMARY KEY, updated TEXT NOT NULL, run_id TEXT NOT NULL,
                    tab_id TEXT NOT NULL, url TEXT NOT NULL, query TEXT NOT NULL);
            """)
        self.purge()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA secure_delete=ON")
        connection.row_factory = sqlite3.Row
        return connection

    def purge(self):
        cutoff = (datetime.now(UTC) - timedelta(days=self.days)).isoformat()
        with closing(self.connect()) as connection, connection:
            connection.execute("DELETE FROM command_history WHERE created < ?", (cutoff,))
            connection.execute("DELETE FROM navigation_context WHERE updated < ?", (cutoff,))
            connection.execute("DELETE FROM command_history WHERE id NOT IN "
                               "(SELECT id FROM command_history ORDER BY id DESC LIMIT 1000)")

    def record(self, task_id, command, action, status, result):
        if ("whatsapp" in command.lower() or action.name.startswith("whatsapp_")
                or action.arguments.get("app") == "whatsapp"):
            command = "Comando do WhatsApp (conteúdo omitido)"
        if action.name == "whatsapp_prepare_message":
            action = Action(action.name, {**action.arguments, "text": "[conteúdo omitido]"})
            result = "Rascunho preparado, sem envio" if status == "completed" else result
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT INTO command_history(created,task_id,command_text,normalized,tool,arguments,"
                "status,result) VALUES(?,?,?,?,?,?,?,?)",
                (datetime.now(UTC).isoformat(), task_id, private_text(command),
                 normalize(private_text(command)), action.name,
                 private_text(json.dumps(action.arguments, ensure_ascii=False)), status,
                 private_text(result)),
            )
        self.purge()

    def navigation(self, site=None):
        self.purge()
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM navigation_context " + ("WHERE site=? " if site else "") +
                "ORDER BY updated DESC LIMIT 1", (site,) if site else (),
            ).fetchone()
            return dict(row) if row else None

    def remember_navigation(self, state, query=""):
        # Do not persist a URL containing a detected secret. The site/tab can still
        # be reused for a fresh search, but opening its old results will be refused.
        url = state["url"] if private_text(state["url"]) == state["url"] else ""
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT OR REPLACE INTO navigation_context(site,updated,run_id,tab_id,url,query) "
                "VALUES(?,?,?,?,?,?)",
                (state["site"], datetime.now(UTC).isoformat(), state["run_id"], state["tab_id"],
                 url, private_text(query)),
            )

    def clear(self):
        with closing(self.connect()) as connection, connection:
            connection.execute("DELETE FROM command_history")
            connection.execute("DELETE FROM navigation_context")


def database_snapshot(path):
    """Fixed read-only views; never expose arbitrary tables, SQL or environment files."""
    views = {
        "Comandos": "SELECT created,command_text,tool,arguments,status,result "
                    "FROM command_history ORDER BY id DESC LIMIT 200",
        "Navegação": "SELECT site,updated,url,query FROM navigation_context "
                     "ORDER BY updated DESC LIMIT 200",
        "Consumo": "SELECT created,model,input_tokens,output_tokens,cost,status "
                   "FROM usage ORDER BY id DESC LIMIT 200",
        "Conversas": "SELECT created,user_text,assistant_text FROM conversation ORDER BY id DESC LIMIT 200",
        "Tarefas": "SELECT id,updated,title,status,output_path,message,sources "
                   "FROM research_tasks ORDER BY created DESC LIMIT 200",
        "Envios": "SELECT created,draft_id,status FROM message_attempts ORDER BY created DESC LIMIT 200",
        "Aplicativos": "SELECT name,executable,aliases FROM applications ORDER BY name LIMIT 200",
    }
    if not Path(path).is_file():
        return {name: ([], []) for name in views}
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=3)) as connection:
        result = {}
        for name, query in views.items():
            try:
                cursor = connection.execute(query)
                result[name] = ([column[0] for column in cursor.description], cursor.fetchall())
            except sqlite3.OperationalError as exc:
                if "no such table" not in str(exc):
                    raise
                result[name] = ([], [])
        return result
