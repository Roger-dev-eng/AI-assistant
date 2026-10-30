"""User-managed application catalogue; no generated commands or automatic fuzzy launches."""

import json
import math
import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from assistant.core.intent_router import normalize

BLOCKED = {"cmd", "powershell", "pwsh", "wscript", "cscript", "mshta", "python", "pythonw", "bash"}

def terms(value):
    return Counter(re.findall(r"\w+", normalize(value)))


class ApplicationStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS applications (name TEXT PRIMARY KEY, "
                       "executable TEXT NOT NULL, aliases TEXT NOT NULL)")

    def list(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            return [{"name": name, "executable": path, "aliases": json.loads(aliases)}
                    for name, path, aliases in db.execute("SELECT name,executable,aliases FROM applications ORDER BY name")]

    def save(self, name, executable, aliases):
        name = name.strip()
        path = Path(executable)
        if not name or len(name) > 120 or not path.is_absolute() or path.suffix.lower() != ".exe" or not path.is_file():
            raise ValueError("Informe um nome e selecione um arquivo .exe existente pelo caminho completo.")
        aliases = list(dict.fromkeys(item.strip() for item in aliases if item.strip()))
        if any(not normalize(item) or re.search(r"[/\\:]|[\x00-\x1f]", item) for item in [name, *aliases]):
            raise ValueError("Nomes e apelidos não podem conter caminhos ou caracteres de controle.")
        if path.stem.lower() in BLOCKED or any(normalize(item) in BLOCKED for item in [name, *aliases]):
            raise ValueError("Interpretadores de comandos e scripts não podem ser cadastrados.")
        if len(aliases) > 30 or any(len(item) > 120 for item in aliases):
            raise ValueError("Use até 30 nomes alternativos de até 120 caracteres.")
        desired = {normalize(item) for item in [name, *aliases]}
        for app in self.list():
            if app["name"] != name and desired.intersection(normalize(item) for item in [app["name"], *app["aliases"]]):
                raise ValueError("Esse nome ou apelido já pertence a outro aplicativo.")
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("INSERT OR REPLACE INTO applications VALUES(?,?,?)",
                       (name, str(path.resolve()), json.dumps(aliases, ensure_ascii=False)))

    def remove(self, name):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("DELETE FROM applications WHERE name=?", (name,))

    def resolve(self, name):
        matches = [app for app in self.list()
                   if normalize(name) in {normalize(item) for item in [app["name"], *app["aliases"]]}]
        if len(matches) != 1:
            raise ValueError("Aplicativo não cadastrado ou nome ambíguo. Consulte o cadastro nas configurações.")
        return matches[0]

    def suggest(self, query):
        # Sparse local word vectors rank suggestions only. No cloud embeddings or fuzzy execution.
        vector = terms(query)
        def similarity(label):
            other = terms(label)
            denominator = math.sqrt(sum(x*x for x in vector.values()) * sum(x*x for x in other.values()))
            return sum(value * other[key] for key, value in vector.items()) / denominator if denominator else 0
        ranked = [(max(similarity(label) for label in [app["name"], *app["aliases"]]), app["name"])
                  for app in self.list()]
        return [name for score, name in sorted(ranked, reverse=True)[:3] if score > 0]
