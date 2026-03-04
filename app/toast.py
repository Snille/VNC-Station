"""Small non-blocking toast notification widget."""

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QLabel, QWidget


class ToastLabel(QLabel):
    """Transient in-window message shown without blocking user interaction."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        # Keep this as a normal child widget so it never appears as a global OS popup.
        self.set_theme("dark")
        self.setWordWrap(True)
        self.hide()

    def set_theme(self, theme: str) -> None:
        """Set toast style from logical theme value ('light' or 'dark')."""
        t = (theme or "dark").lower()
        if t == "light":
            # Light toast (used when app theme is dark).
            self.setStyleSheet(
                "background:#f8f9fa;color:#111111;border:1px solid #adb5bd;padding:8px 10px;border-radius:6px;"
            )
            return
        # Dark toast (used when app theme is light).
        self.setStyleSheet(
            "background:#1f2328;color:#e6edf3;border:1px solid #30363d;padding:8px 10px;border-radius:6px;"
        )

    def show_message(self, text: str, timeout_ms: int = 2600) -> None:
        """Show and auto-hide a toast fully inside the main window."""
        self.setText(text)
        parent = self.parentWidget()
        if parent is not None:
            margin = 14
            max_width = max(180, parent.width() - (margin * 2))
            self.setFixedWidth(max_width)
            self.adjustSize()
            # Place it centered near the bottom to improve readability in narrow windows.
            x = max(margin, int((parent.width() - self.width()) / 2))
            y = max(margin, parent.height() - self.height() - margin)
            self.move(x, y)
        self.show()
        self.raise_()
        QTimer.singleShot(timeout_ms, self.hide)
