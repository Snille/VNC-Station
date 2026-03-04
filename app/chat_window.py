"""Chat UI components: input widget with shortcuts and the chat window."""

from datetime import datetime
from typing import Callable, List

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .constants import CHAT_ICON_PATH


class ChatInput(QTextEdit):
    """Custom text input with Enter-send and Up/Down history navigation."""

    def __init__(self, submit: Callable[[], None], history_nav: Callable[[int], None], clear_away: Callable[[], None]) -> None:
        """Store callbacks for send/history/away handling and configure editor."""
        super().__init__()
        self._submit = submit
        self._history_nav = history_nav
        self._clear_away = clear_away
        self.setPlaceholderText("Type message. Enter=send, Shift+Enter=new line.\n/help for help")
        self.setFixedHeight(70)

    def keyPressEvent(self, event) -> None:
        """Map keyboard shortcuts to chat actions before default handling."""
        # Only local keyboard interaction should clear away status.
        self._clear_away()
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self._submit()
            return
        if event.key() == Qt.Key_Up:
            self._history_nav(-1)
            return
        if event.key() == Qt.Key_Down:
            self._history_nav(1)
            return
        super().keyPressEvent(event)


class ChatWindow(QMainWindow):
    """Top-level chat window with target selection, log, and composer."""

    def __init__(
        self,
        station_name: str,
        send_message: Callable[[str, str], None],
        refresh_stations: Callable[[], None],
        clear_away: Callable[[], None],
        parent=None,
    ) -> None:
        """Construct chat controls and wire provided callback hooks."""
        super().__init__(parent)
        self.setWindowTitle(f"VNC Chat - {station_name}")
        if CHAT_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(CHAT_ICON_PATH)))
        self.resize(680, 500)
        self._send = send_message
        self._refresh = refresh_stations
        self._history: List[str] = []
        self._history_index = -1

        body = QWidget(self)
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)

        top = QHBoxLayout()
        layout.addLayout(top)
        top.addWidget(QLabel("Target:"))
        self.target_box = QComboBox()
        self.target_box.addItem("All stations")
        top.addWidget(self.target_box, 1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        top.addWidget(refresh_btn)

        self.topic_label = QLabel("Topic: #General")
        self.topic_label.setStyleSheet("font-weight: 700;")
        layout.addWidget(self.topic_label)

        # Use plain-text log so multiline text is rendered as real new lines
        # and never treated as HTML.
        self.chat_log = QPlainTextEdit()
        self.chat_log.setReadOnly(True)
        layout.addWidget(self.chat_log, 1)

        self.input = ChatInput(self._on_submit, self._navigate_history, clear_away)
        layout.addWidget(self.input)

    def set_station_title(self, station_name: str) -> None:
        """Update window title when local station name changes."""
        self.setWindowTitle(f"VNC Chat - {station_name}")

    def set_topic(self, topic: str) -> None:
        """Update visible topic label."""
        self.topic_label.setText(f"Topic: {topic}")

    def _navigate_history(self, direction: int) -> None:
        """Move through sent-message history and repopulate the editor."""
        if not self._history:
            return
        self._history_index = max(0, min(len(self._history) - 1, self._history_index + direction))
        self.input.setPlainText(self._history[self._history_index])
        cursor = self.input.textCursor()
        cursor.movePosition(cursor.End)
        self.input.setTextCursor(cursor)

    def _on_submit(self) -> None:
        """Send current message text and push it into input history."""
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self._history.append(text)
        self._history_index = len(self._history)
        self._send(text, self.target_box.currentText())

    def add_message(self, sender: str, text: str, action: bool = False) -> None:
        """Append a chat/action line to the log with a local timestamp."""
        now = datetime.now().strftime("%H:%M:%S")
        safe_text = text.replace("\r\n", "\n").replace("\r", "\n")
        if action:
            line = f"[{now}] * {sender} {safe_text}"
        else:
            line = f"[{now}] <{sender}> {safe_text}"
        self.chat_log.appendPlainText(line)

    def add_notice(self, text: str) -> None:
        """Append a system notice line (status/update style)."""
        now = datetime.now().strftime("%H:%M:%S")
        self.chat_log.appendPlainText(f"[{now}] *** {text}")

    def set_targets(self, stations: List[str]) -> None:
        """Refresh the target dropdown while preserving current selection."""
        current = self.target_box.currentText()
        self.target_box.blockSignals(True)
        self.target_box.clear()
        self.target_box.addItem("All stations")
        for station in sorted(set(stations), key=str.lower):
            self.target_box.addItem(station)
        idx = self.target_box.findText(current)
        self.target_box.setCurrentIndex(max(0, idx))
        self.target_box.blockSignals(False)
