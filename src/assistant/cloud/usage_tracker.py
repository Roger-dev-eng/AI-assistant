import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class UsageTracker:
    """Persist a reservation before network access; uncertain charges keep their reservation."""

    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.execute("""CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY, created TEXT NOT NULL, model TEXT NOT NULL,
            input_tokens INTEGER, output_tokens INTEGER, cost REAL NOT NULL,
            status TEXT NOT NULL)""")
        self.connection.commit()
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(usage)")}
        if "usage_json" not in columns:
            self.connection.execute("ALTER TABLE usage ADD COLUMN usage_json TEXT")
            self.connection.commit()

    def sonic_usage(self, record_id, counts, settings, complete=False):
        cost = (
            sum(
                counts.get(key, 0) * rate
                for key, rate in {
                    "input_text": settings.sonic_text_input_rate,
                    "output_text": settings.sonic_text_output_rate,
                    "input_speech": settings.sonic_audio_input_rate,
                    "output_speech": settings.sonic_audio_output_rate,
                }.items()
            )
            / 1_000_000
        )
        with self.connection:
            self.connection.execute(
                "UPDATE usage SET input_tokens=?,output_tokens=?,cost="
                + ("?" if complete else "MAX(cost,?)")
                + ",usage_json=?,status=? WHERE id=?",
                (
                    counts.get("input_text", 0) + counts.get("input_speech", 0),
                    counts.get("output_text", 0) + counts.get("output_speech", 0),
                    cost,
                    json.dumps(counts),
                    "complete" if complete else "reserved",
                    record_id,
                ),
            )
        return cost

    def reject(self, record_id):
        with self.connection:
            self.connection.execute(
                "UPDATE usage SET cost=0,status='rejected' WHERE id=?", (record_id,)
            )

    def reserve(self, settings, cost):
        now = datetime.now(UTC).isoformat()
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            daily = self.connection.execute(
                "SELECT COUNT(*) FROM usage WHERE substr(created,1,10)=?", (now[:10],)
            ).fetchone()[0]
            monthly = self.connection.execute(
                "SELECT COALESCE(SUM(cost),0) FROM usage WHERE substr(created,1,7)=?", (now[:7],)
            ).fetchone()[0]
            if daily >= settings.daily_requests:
                raise RuntimeError("Daily cloud request limit reached (UTC).")
            if monthly + cost > settings.monthly_budget:
                raise RuntimeError("Monthly estimated cloud budget reached (UTC).")
            cursor = self.connection.execute(
                "INSERT INTO usage(created,model,cost,status) VALUES(?,?,?,?)",
                (now, settings.model_id, cost, "reserved"),
            )
            return cursor.lastrowid

    def settle(self, record_id, usage, settings):
        incoming, outgoing = usage["inputTokens"], usage["outputTokens"]
        cost = (incoming * settings.input_rate + outgoing * settings.output_rate) / 1_000_000
        with self.connection:
            self.connection.execute(
                "UPDATE usage SET input_tokens=?, output_tokens=?, cost=?, status='complete' WHERE id=?",
                (incoming, outgoing, cost, record_id),
            )

    def summary(self):
        return self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(cost),0) FROM usage"
        ).fetchone()

    def close(self):
        self.connection.close()
