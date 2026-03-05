"""Launch and manage TightVNC viewer processes plus overlay label windows."""

import subprocess
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QLabel, QWidget

from .constants import VIEWER_EXE_PATH
from .models import SessionRecord, SessionSettings

try:
    import win32con
    import win32gui
    import win32process
except ImportError:  # pragma: no cover
    win32con = None
    win32gui = None
    win32process = None


class OverlayLabel(QWidget):
    """Always-on-top, click-through label shown above a VNC window."""

    def __init__(self, settings: SessionSettings) -> None:
        """Create overlay UI using sizing/colors from session settings."""
        super().__init__()
        self.label = QLabel(settings.label_text, self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        self._apply_style(settings)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setGeometry(
            settings.x + settings.label_x,
            settings.y + settings.label_y,
            max(30, settings.label_width),
            max(20, settings.label_height),
        )
        self.label.setGeometry(0, 0, self.width(), self.height())

    def _apply_style(self, settings: SessionSettings) -> None:
        """Apply current visual style for label text, background, and border."""
        border = max(0, settings.label_border_size)
        self.label.setStyleSheet(
            (
                f"background: {settings.label_bg};"
                f"color: {settings.label_font_color};"
                f"border: {border}px solid {settings.label_border_color};"
                f"font-size: {max(8, settings.label_font)}px;"
                "font-weight: 700;"
            )
        )


class SessionManager:
    """Owns live viewer processes and keeps overlays synced to VNC windows."""

    def __init__(
        self,
        on_closed: Callable[[Tuple[str, str]], None],
        on_error: Callable[[str], None],
        on_unexpected_exit: Optional[Callable[[Tuple[str, str]], None]] = None,
    ) -> None:
        """Initialize storage and start periodic overlay-follow polling."""
        self._sessions: Dict[Tuple[str, str], SessionRecord] = {}
        self._on_closed = on_closed
        self._on_error = on_error
        self._on_unexpected_exit = on_unexpected_exit

        self._follow_timer = QTimer()
        self._follow_timer.timeout.connect(self._sync_overlays)
        self._follow_timer.start(350)

    @property
    def sessions(self) -> Dict[Tuple[str, str], SessionRecord]:
        """Expose active sessions map for read-only iteration by callers."""
        return self._sessions

    def launch(self, key: Tuple[str, str], vnc_path: Path, settings: SessionSettings) -> bool:
        """Start viewer with options file, create overlay, and track session."""
        if not VIEWER_EXE_PATH.exists():
            self._on_error(f"Missing VNC viewer: {VIEWER_EXE_PATH}")
            return False
        if not vnc_path.exists():
            self._on_error(f"Missing VNC file: {vnc_path}")
            return False

        self.close_session(key)
        try:
            # TightVNC documented way to load .vnc connection profiles.
            proc = subprocess.Popen([str(VIEWER_EXE_PATH), f"-optionsfile={vnc_path}"])
        except OSError as exc:
            self._on_error(f"Failed to start viewer for {vnc_path.name}: {exc}")
            return False

        overlay = OverlayLabel(settings)
        overlay.show()
        record = SessionRecord(
            key=key,
            process=proc,
            settings=settings,
            overlay=overlay,
            vnc_path=vnc_path,
            label_offset=(settings.label_x, settings.label_y),
        )
        self._sessions[key] = record

        QTimer.singleShot(600, lambda: self._position_initial_window(key))
        return True

    def close_session(self, key: Tuple[str, str]) -> None:
        """Terminate one session process, remove overlay, and emit close callback."""
        record = self._sessions.pop(key, None)
        if not record:
            return
        try:
            if record.overlay:
                record.overlay.close()
        except Exception:
            pass
        try:
            if record.process and record.process.poll() is None:
                record.process.terminate()
                time.sleep(0.1)
                if record.process.poll() is None:
                    record.process.kill()
        except Exception:
            pass
        self._on_closed(key)

    def close_all(self) -> None:
        """Close every active tracked session."""
        keys = list(self._sessions.keys())
        for key in keys:
            self.close_session(key)

    def _position_initial_window(self, key: Tuple[str, str]) -> None:
        """Find new viewer window and apply configured initial geometry."""
        record = self._sessions.get(key)
        if not record:
            return
        hwnd = self._find_main_window(record.process.pid)
        record.hwnd = hwnd
        if hwnd is None:
            return
        self._move_window(hwnd, record.settings.x, record.settings.y, record.settings.width, record.settings.height)
        ox, oy = record.label_offset
        record.overlay.setGeometry(
            record.settings.x + ox,
            record.settings.y + oy,
            max(30, record.settings.label_width),
            max(20, record.settings.label_height),
        )
        record.overlay.label.setGeometry(0, 0, record.overlay.width(), record.overlay.height())

    def _sync_overlays(self) -> None:
        """Poll active windows and move overlays so they follow window movement."""
        dead = []
        for key, record in self._sessions.items():
            if record.process.poll() is not None:
                dead.append(key)
                continue

            if record.hwnd is None or not self._is_valid_window(record.hwnd):
                record.hwnd = self._find_main_window(record.process.pid)
            if record.hwnd is None:
                continue

            rect = self._window_rect(record.hwnd)
            if rect is None:
                continue
            x, y, _, _ = rect
            ox, oy = record.label_offset
            record.overlay.move(x + ox, y + oy)
            record.overlay.raise_()

        for key in dead:
            if self._on_unexpected_exit is not None:
                self._on_unexpected_exit(key)
            self.close_session(key)

    def _is_valid_window(self, hwnd: int) -> bool:
        """Return True only for existing, visible native windows."""
        return bool(win32gui and win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd))

    def _window_rect(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        """Read native window bounds as (left, top, right, bottom)."""
        if not win32gui:
            return None
        try:
            return win32gui.GetWindowRect(hwnd)
        except Exception:
            return None

    def _move_window(self, hwnd: int, x: int, y: int, width: int, height: int) -> None:
        """Resize/reposition target window, with fallback API call."""
        if not win32gui:
            return
        try:
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                int(x),
                int(y),
                max(200, int(width)),
                max(100, int(height)),
                0,
            )
        except Exception:
            try:
                win32gui.MoveWindow(hwnd, int(x), int(y), max(200, int(width)), max(100, int(height)), True)
            except Exception:
                pass

    def _find_main_window(self, pid: int) -> Optional[int]:
        """Locate first visible top-level window for the given process id."""
        if not (win32gui and win32process):
            return None
        result = []

        def callback(hwnd: int, _: int) -> bool:
            try:
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid and win32gui.IsWindowVisible(hwnd):
                    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                    if style & win32con.WS_OVERLAPPEDWINDOW:
                        result.append(hwnd)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(callback, 0)
        return result[0] if result else None
