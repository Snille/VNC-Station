"""Data models shared by UI, config, and runtime process management."""

from dataclasses import dataclass, field
import time
from pathlib import Path
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class ConnectionEntry:
    """Single connection row data discovered from .vnc files on disk."""

    name: str
    view_vnc_path: Optional[Path]
    control_vnc_path: Optional[Path]


@dataclass
class SessionSettings:
    """Runtime/editable settings for VNC window geometry and overlay label."""

    x: int = 1
    y: int = 1
    width: int = 1300
    height: int = 880
    label_text: str = "Default"
    label_x: int = 10
    label_y: int = 10
    label_bg: str = "white"
    label_width: int = 200
    label_height: int = 100
    label_font: int = 18
    label_font_color: str = "black"
    label_border_size: int = 5
    label_border_color: str = "yellow"
    station_name: str = "Station 01"

    @staticmethod
    def from_mapping(data: Dict[str, object]) -> "SessionSettings":
        """Create settings from loose JSON-like values with safe int coercion."""

        def to_int(value: object, fallback: int) -> int:
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return fallback

        defaults = SessionSettings()
        return SessionSettings(
            x=to_int(data.get("x"), defaults.x),
            y=to_int(data.get("y"), defaults.y),
            width=to_int(data.get("width"), defaults.width),
            height=to_int(data.get("height"), defaults.height),
            label_text=str(data.get("label_text", defaults.label_text)),
            label_x=to_int(data.get("label_x"), defaults.label_x),
            label_y=to_int(data.get("label_y"), defaults.label_y),
            label_bg=str(data.get("label_bg", defaults.label_bg)),
            label_width=to_int(data.get("label_width"), defaults.label_width),
            label_height=to_int(data.get("label_height"), defaults.label_height),
            label_font=to_int(data.get("label_font"), defaults.label_font),
            label_font_color=str(data.get("label_font_color", defaults.label_font_color)),
            label_border_size=to_int(data.get("label_border_size"), defaults.label_border_size),
            label_border_color=str(data.get("label_border_color", defaults.label_border_color)),
            station_name=str(data.get("station_name", defaults.station_name)),
        )

    def to_json(self) -> Dict[str, str]:
        """Serialize settings to the on-disk schema (string values)."""
        return {
            "x": str(self.x),
            "y": str(self.y),
            "width": str(self.width),
            "height": str(self.height),
            "label_text": self.label_text,
            "label_x": str(self.label_x),
            "label_y": str(self.label_y),
            "label_bg": self.label_bg,
            "label_width": str(self.label_width),
            "label_height": str(self.label_height),
            "label_font": str(self.label_font),
            "label_font_color": self.label_font_color,
            "label_border_size": str(self.label_border_size),
            "label_border_color": self.label_border_color,
        }


@dataclass
class SessionRecord:
    """Tracks a live launched VNC process and its linked overlay state."""

    key: Tuple[str, str]
    process: object
    settings: SessionSettings
    overlay: object
    vnc_path: Path
    hwnd: Optional[int] = None
    label_offset: Tuple[int, int] = field(default_factory=lambda: (0, 0))
    started_ts: float = field(default_factory=time.time)
