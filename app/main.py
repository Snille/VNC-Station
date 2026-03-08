"""Application entrypoint for launching the PyQt main window."""

import hashlib
import logging
import os
import sys

from PyQt5.QtWidgets import QApplication, QMessageBox

try:
    from .config import load_default_mapping
    from .constants import APP_VERSION, ROOT_DIR
    from .logging_setup import configure_logging
    from .main_window import MainWindow
except ImportError:  # Frozen/script fallback
    from app.config import load_default_mapping
    from app.constants import APP_VERSION, ROOT_DIR
    from app.logging_setup import configure_logging
    from app.main_window import MainWindow

_INSTANCE_MUTEX_HANDLE = None


def _to_bool(value: object, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return fallback


def _allow_multiple_instances() -> bool:
    try:
        mapping = load_default_mapping()
    except Exception:
        return False
    return _to_bool(mapping.get("allow_multiple_instances", False), False)


def _acquire_single_instance_lock() -> bool:
    """Use a named Windows mutex to restrict one local app instance."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return True

    digest = hashlib.sha1(str(ROOT_DIR).encode("utf-8", errors="replace")).hexdigest()[:16]
    mutex_name = f"Local\\VNCStationController-{digest}"
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if not handle:
        # Fallback to allow launch if lock cannot be created.
        return True
    already_exists = kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    if already_exists:
        return False

    global _INSTANCE_MUTEX_HANDLE
    _INSTANCE_MUTEX_HANDLE = handle
    return True


def main() -> int:
    """Create QApplication, show the main UI, and run the Qt event loop."""
    configure_logging()
    logging.getLogger(__name__).info("Starting VNC Station Controller v%s", APP_VERSION)
    app = QApplication(sys.argv)
    if not _allow_multiple_instances() and not _acquire_single_instance_lock():
        QMessageBox.warning(
            None,
            "VNC Station Controller",
            "Another instance is already running on this station.\n\n"
            "Enable 'Allow multiple instances on the same station' in Change Settings to allow this.",
        )
        return 0
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
