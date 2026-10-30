import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

from assistant.core.action_executor import ActionExecutor
from assistant.core.intent_router import Action, IntentRouter
from assistant.storage.activity import ActivityStore, database_snapshot


def test_navigation_survives_new_store_and_clear_preserves_usage_and_conversation(tmp_path):
    path = tmp_path / "usage.sqlite3"
    store = ActivityStore(path)
    store.remember_navigation({"site": "youtube", "run_id": "session", "tab_id": "tab",
                               "url": "https://www.youtube.com"})
    store.record("task", "abre YouTube", Action("open_site", {"url": "https://www.youtube.com"}),
                 "completed", "ok")
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE usage(id INTEGER PRIMARY KEY, cost REAL)")
        connection.execute("INSERT INTO usage(cost) VALUES(2.5)")
        connection.execute("CREATE TABLE conversation(id INTEGER PRIMARY KEY, user_text TEXT)")
        connection.execute("INSERT INTO conversation(user_text) VALUES('keep conversation')")
    reopened = ActivityStore(path)
    assert reopened.navigation()["site"] == "youtube"
    reopened.clear()
    assert reopened.navigation() is None
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM command_history").fetchone()[0] == 0
        assert connection.execute("SELECT cost FROM usage").fetchone()[0] == 2.5
        assert connection.execute("SELECT user_text FROM conversation").fetchone()[0] == "keep conversation"


def test_history_supports_sonic_tool_thread_and_redacts_known_secret_patterns(tmp_path):
    store = ActivityStore(tmp_path / "usage.sqlite3")
    action = Action("search_web", {"query": "Python", "engine": "youtube"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda index: store.record(str(index), "senha=secret AKIA1234567890123456",
                                                 action, "completed", "ok"), range(5)))
    columns, rows = database_snapshot(store.path)["Comandos"]
    assert len(rows) == 5
    assert "secret" not in str(rows)
    assert "AKIA1234567890123456" not in str(rows)
    assert "command_text" in columns


def test_retention_removes_expired_context_and_commands(tmp_path):
    store = ActivityStore(tmp_path / "usage.sqlite3", 1)
    store.record("old", "abra YouTube", Action("open_site", {}), "completed", "ok")
    store.remember_navigation({"site": "youtube", "run_id": "run", "tab_id": "tab",
                               "url": "https://www.youtube.com"})
    with store.connect() as connection:
        connection.execute("UPDATE command_history SET created='2000-01-01'")
        connection.execute("UPDATE navigation_context SET updated='2000-01-01'")
    store.purge()
    assert store.navigation() is None
    assert database_snapshot(store.path)["Comandos"][1] == []


def test_history_failure_does_not_turn_completed_action_into_error():
    backend = Mock()
    backend.open_site.return_value = "opened"
    activity = Mock()
    activity.record.side_effect = sqlite3.OperationalError("locked")
    executor = ActionExecutor(backend, Mock(), activity=activity)
    assert executor.execute(Action("open_site", {"url": "https://www.youtube.com"})) == "opened"
    backend.open_site.assert_called_once()


def test_denied_correlated_result_is_recorded_without_opening(tmp_path):
    store = ActivityStore(tmp_path / "usage.sqlite3")
    backend = Mock()
    backend.describe_correlated_result.return_value = "Title\nhttps://www.youtube.com/watch?v=kJQP7kiw5Fk"
    executor = ActionExecutor(backend, Mock(return_value=False), activity=store)
    executor.set_command("abre o primeiro")
    assert executor.execute(Action("open_correlated_result", {"position": 1})) == "Action denied by user."
    backend.open_correlated_result.assert_not_called()
    columns, rows = database_snapshot(store.path)["Comandos"]
    assert rows[0][columns.index("status")] == "denied"


def test_router_resolves_follow_up_at_execution_time_and_preserves_explicit_engine():
    router = IntentRouter()
    assert router.route("pesquisa Café", "youtube") == [Action("search_current_site", {"query": "Café"})]
    assert router.route("pesquisa Café no Google", "youtube")[0].arguments["engine"] == "google"
    assert router.route("abre o primeiro vídeo")[0] == Action("open_correlated_result", {"position": 1})


def test_read_only_view_does_not_show_unrelated_secret_tables_or_create_database(tmp_path):
    path = tmp_path / "usage.sqlite3"
    assert not any(rows for columns, rows in database_snapshot(path).values())
    assert not path.exists()
    store = ActivityStore(path)
    with store.connect() as connection:
        connection.execute("CREATE TABLE credentials(secret TEXT)")
        connection.execute("INSERT INTO credentials VALUES('never-display-this')")
    assert "never-display-this" not in str(database_snapshot(path))
