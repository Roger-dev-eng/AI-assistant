import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(sys._MEIPASS) / "browsers")

from assistant.main import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("--gui")
    try:
        raise SystemExit(main())
    except Exception as exc:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, "Assistente — erro ao iniciar", str(exc))
        raise SystemExit(1) from exc
