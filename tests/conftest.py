import os


def pytest_sessionstart(session):
    if os.environ.get("ASSISTANT_LOG_DIR"):
        from assistant.runtime_log import configure, mark

        configure()
        mark("pytest.session.start")
