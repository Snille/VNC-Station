"""Dialog used to edit per-connection window and overlay settings."""

from typing import Dict

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .constants import GEARS_ICON_PATH
from .models import SessionSettings


class SettingsDialog(QDialog):
    """Simple form-based editor for SessionSettings values."""

    def __init__(self, title: str, settings: SessionSettings, parent=None) -> None:
        """Build the settings form and prefill it from an existing settings object."""
        super().__init__(parent)
        self.setWindowTitle(title)
        if GEARS_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(GEARS_ICON_PATH)))
        self.setModal(True)
        self.resize(290, 415)
        self._fields: Dict[str, object] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self._add_spin(form, "x", "Window X", settings.x, -10000, 10000)
        self._add_spin(form, "y", "Window Y", settings.y, -10000, 10000)
        self._add_spin(form, "width", "Window Width", settings.width, 100, 6000)
        self._add_spin(form, "height", "Window Height", settings.height, 100, 6000)
        self._add_text(form, "label_text", "Label Text", settings.label_text)
        self._add_spin(form, "label_x", "Label Offset X", settings.label_x, -10000, 10000)
        self._add_spin(form, "label_y", "Label Offset Y", settings.label_y, -10000, 10000)
        self._add_spin(form, "label_width", "Label Width", settings.label_width, 30, 4000)
        self._add_spin(form, "label_height", "Label Height", settings.label_height, 20, 2000)
        self._add_text(form, "label_bg", "Label Background", settings.label_bg)
        self._add_spin(form, "label_font", "Label Font Size", settings.label_font, 8, 180)
        self._add_text(form, "label_font_color", "Label Font Color", settings.label_font_color)
        self._add_spin(form, "label_border_size", "Label Border Size", settings.label_border_size, 0, 40)
        self._add_text(form, "label_border_color", "Label Border Color", settings.label_border_color)
        self._add_file_picker(form, "ks", "KS File", settings.ks)

        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        save.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        buttons.addWidget(save)

    def _add_spin(self, form: QFormLayout, key: str, label: str, value: int, low: int, high: int) -> None:
        """Add an integer field to the form and cache it by key."""
        field = QSpinBox()
        field.setRange(low, high)
        field.setValue(value)
        self._fields[key] = field
        form.addRow(label, field)

    def _add_text(self, form: QFormLayout, key: str, label: str, value: str) -> None:
        """Add a text field to the form and cache it by key."""
        field = QLineEdit(value)
        self._fields[key] = field
        form.addRow(label, field)

    def _add_file_picker(self, form: QFormLayout, key: str, label: str, value: str) -> None:
        """Add editable file path input with browse button."""
        row = QHBoxLayout()
        field = QLineEdit(value)
        browse_btn = QPushButton("Browse...")

        def browse() -> None:
            path, _ = QFileDialog.getOpenFileName(self, "Select KS File", field.text().strip() or "")
            if path:
                field.setText(path)

        browse_btn.clicked.connect(browse)
        row.addWidget(field, 1)
        row.addWidget(browse_btn)
        wrapper = QVBoxLayout()
        wrapper.addLayout(row)
        self._fields[key] = field
        form.addRow(label, wrapper)

    def values(self) -> SessionSettings:
        """Read all current UI fields back into a SessionSettings object."""
        try:
            return SessionSettings(
                x=self._fields["x"].value(),
                y=self._fields["y"].value(),
                width=self._fields["width"].value(),
                height=self._fields["height"].value(),
                label_text=self._fields["label_text"].text().strip() or "Label",
                label_x=self._fields["label_x"].value(),
                label_y=self._fields["label_y"].value(),
                label_bg=self._fields["label_bg"].text().strip() or "white",
                label_width=self._fields["label_width"].value(),
                label_height=self._fields["label_height"].value(),
                label_font=self._fields["label_font"].value(),
                label_font_color=self._fields["label_font_color"].text().strip() or "black",
                label_border_size=self._fields["label_border_size"].value(),
                label_border_color=self._fields["label_border_color"].text().strip() or "black",
                station_name="",
                ks=self._fields["ks"].text().strip(),
            )
        except Exception as exc:
            # Keep the dialog resilient; return defaults if field casting fails.
            QMessageBox.warning(self, "Invalid Input", f"Could not read values: {exc}")
            return SessionSettings()
