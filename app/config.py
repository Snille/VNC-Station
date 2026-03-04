"""Helpers for reading/writing JSON settings and discovering VNC files."""

import json
from pathlib import Path
from typing import Dict, List

from .constants import DEFAULT_CONFIG_PATH, VNC_CONTROL_DIR, VNC_VIEW_DIR
from .models import ConnectionEntry, SessionSettings


def _load_json(path: Path) -> Dict[str, object]:
    """Load a JSON object from disk, returning {} on missing/invalid files."""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def save_json(path: Path, data: Dict[str, object]) -> None:
    """Persist JSON data with UTF-8 encoding and stable indentation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def load_default_settings() -> SessionSettings:
    """Read defaults from default.json and convert to SessionSettings."""
    return SessionSettings.from_mapping(_load_json(DEFAULT_CONFIG_PATH))


def load_session_settings(config_path: Path) -> SessionSettings:
    """Load per-session settings merged on top of default settings."""
    defaults = load_default_settings()
    # The JSON schema stores numeric values as strings, so we normalize to str.
    merged = defaults.to_json()
    merged["station_name"] = defaults.station_name
    merged.update({k: str(v) for k, v in _load_json(config_path).items()})
    return SessionSettings.from_mapping(merged)


def scan_connections() -> List[ConnectionEntry]:
    """Build the unified connection list from vnc-control/ and vnc-view/."""
    # Ensure both folders exist so first run does not fail.
    VNC_CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    VNC_VIEW_DIR.mkdir(parents=True, exist_ok=True)

    control = {p.stem: p for p in VNC_CONTROL_DIR.glob("*.vnc")}
    view = {p.stem: p for p in VNC_VIEW_DIR.glob("*.vnc")}

    names = sorted(set(control.keys()).union(view.keys()), key=str.lower)
    return [
        ConnectionEntry(name=n, view_vnc_path=view.get(n), control_vnc_path=control.get(n))
        for n in names
    ]


def config_path_for(connection_name: str, mode: str) -> Path:
    """Return the JSON config path for a given connection and mode."""
    directory = VNC_VIEW_DIR if mode == "view" else VNC_CONTROL_DIR
    return directory / f"{connection_name}.json"
