"""Data models shared by UI, config, and runtime process management."""

from dataclasses import dataclass, field
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ConnectionEntry:
    """Single connection row data discovered from .vnc files on disk."""

    name: str
    view_vnc_path: Optional[Path]
    control_vnc_path: Optional[Path]


@dataclass(frozen=True)
class PositionPreset:
    """Named window rectangle loaded from vnc-positions/*.json files."""

    name: str
    x: int
    y: int
    width: int
    height: int
    path: Path


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
    position_name: str = ""
    linked_session: str = ""
    ks: str = ""
    ha_sensors: List[str] = field(default_factory=list)
    ha_sensor_icons: List[Dict[str, str]] = field(default_factory=list)

    @staticmethod
    def from_mapping(data: Dict[str, object]) -> "SessionSettings":
        """Create settings from loose JSON-like values with safe int coercion."""

        def to_int(value: object, fallback: int) -> int:
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return fallback

        defaults = SessionSettings()

        raw_sensors = data.get("ha_sensors", defaults.ha_sensors)
        sensor_values: List[str] = []
        if isinstance(raw_sensors, list):
            for value in raw_sensors:
                text = str(value).strip()
                if text:
                    sensor_values.append(text)
        elif isinstance(raw_sensors, str):
            for part in raw_sensors.split(","):
                text = part.strip()
                if text:
                    sensor_values.append(text)

        # Keep insertion order while removing duplicates.
        deduped_sensors = list(dict.fromkeys(sensor_values))

        raw_mappings = data.get("ha_sensor_icons", [])
        parsed_mappings: List[Dict[str, str]] = []
        if isinstance(raw_mappings, list):
            for item in raw_mappings:
                if not isinstance(item, dict):
                    continue
                entity_id = str(item.get("entity_id", "")).strip()
                if not entity_id:
                    continue
                parsed_mappings.append(
                    {
                        "entity_id": entity_id,
                        "icon": str(item.get("icon", "")).strip(),
                        "icon_on": str(item.get("icon_on", "")).strip(),
                        "icon_off": str(item.get("icon_off", "")).strip(),
                        "tooltip": str(item.get("tooltip", "")).strip(),
                    }
                )
        # Backward compatibility: convert legacy sensor strings into empty mappings.
        if not parsed_mappings and deduped_sensors:
            for entity_id in deduped_sensors:
                parsed_mappings.append(
                    {
                        "entity_id": entity_id,
                        "icon": "",
                        "icon_on": "",
                        "icon_off": "",
                        "tooltip": "",
                    }
                )
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
            position_name=str(data.get("position_name", defaults.position_name)),
            linked_session=str(data.get("linked_session", defaults.linked_session)),
            ks=str(data.get("ks", defaults.ks)),
            ha_sensors=deduped_sensors,
            ha_sensor_icons=parsed_mappings,
        )

    def to_json(self) -> Dict[str, object]:
        """Serialize settings to the on-disk schema."""
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
            "position_name": self.position_name,
            "linked_session": self.linked_session,
            "ks": self.ks,
            "ha_sensors": list(self.ha_sensors),
            "ha_sensor_icons": list(self.ha_sensor_icons),
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
