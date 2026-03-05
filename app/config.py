"""Helpers for reading/writing JSON settings and discovering VNC files."""

import json
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from .constants import DEFAULT_CONFIG_PATH, VNC_CONTROL_DIR, VNC_POSITIONS_DIR, VNC_VIEW_DIR
from .models import ConnectionEntry, PositionPreset, SessionSettings


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


def _to_int(value: object, fallback: int) -> int:
    """Parse int-like values found in JSON strings/numbers."""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return fallback


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


def load_session_overrides(config_path: Path) -> Dict[str, object]:
    """Load only explicit per-session overrides from JSON."""
    return _load_json(config_path)


def update_session_overrides(config_path: Path, updates: Mapping[str, object]) -> None:
    """Merge/update per-session override keys and persist to disk."""
    data = _load_json(config_path)
    for key, value in updates.items():
        data[key] = value
    save_json(config_path, data)


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


def scan_positions() -> List[PositionPreset]:
    """Read all position definitions from vnc-positions/*.json."""
    VNC_POSITIONS_DIR.mkdir(parents=True, exist_ok=True)
    presets: List[PositionPreset] = []
    for path in sorted(VNC_POSITIONS_DIR.glob("*.json"), key=lambda p: p.name.lower()):
        data = _load_json(path)
        if not data:
            continue
        fallback_name = path.stem
        name = str(data.get("name", fallback_name)).strip() or fallback_name
        presets.append(
            PositionPreset(
                name=name,
                x=_to_int(data.get("x"), 1),
                y=_to_int(data.get("y"), 1),
                width=max(100, _to_int(data.get("width"), 1300)),
                height=max(100, _to_int(data.get("height"), 880)),
                path=path,
            )
        )
    return presets


def position_by_name(name: str) -> Optional[PositionPreset]:
    """Resolve one position preset by its display name."""
    cleaned = name.strip().lower()
    if not cleaned:
        return None
    for preset in scan_positions():
        if preset.name.strip().lower() == cleaned:
            return preset
    return None


def config_path_for(connection_name: str, mode: str) -> Path:
    """Return the JSON config path for a given connection and mode."""
    directory = VNC_VIEW_DIR if mode == "view" else VNC_CONTROL_DIR
    return directory / f"{connection_name}.json"


def resolve_ks_target(ks_value: str) -> Tuple[Optional[Path], str]:
    """Resolve configured KS value to an openable file path.

    `ks_value` can be either:
    - a direct file path (legacy behavior), or
    - a folder path; in this case the latest modified file in that folder is used.
    """
    cleaned = ks_value.strip()
    if not cleaned:
        return None, "No KS folder configured."

    target = Path(cleaned)
    if target.is_file():
        return target, ""
    if target.is_dir():
        files: List[Path] = []
        for child in target.iterdir():
            if child.is_file():
                files.append(child)
        if not files:
            return None, f"No files found in KS folder: {target}"
        latest = max(files, key=lambda p: p.stat().st_mtime)
        return latest, ""

    return None, f"KS path not found: {target}"
