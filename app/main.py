"""Application entrypoint for launching the PyQt main window."""

import logging
import sys

from PyQt5.QtWidgets import QApplication

try:
    from .constants import APP_VERSION
    from .logging_setup import configure_logging
    from .main_window import MainWindow
except ImportError:  # Frozen/script fallback
    from app.constants import APP_VERSION
    from app.logging_setup import configure_logging
    from app.main_window import MainWindow


def main() -> int:
    """Create QApplication, show the main UI, and run the Qt event loop."""
    configure_logging()
    logging.getLogger(__name__).info("Starting VNC Station Controller v%s", APP_VERSION)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
