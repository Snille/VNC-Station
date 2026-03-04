"""Pure helper logic for lock checks and chat command parsing."""

from typing import Dict, Optional, Tuple


def find_remote_holder(
    connection_name: str,
    remote_sessions: Dict[Tuple[str, str], str],
    local_station_name: str,
) -> Optional[str]:
    """Return holder station for a connection (any mode), excluding local station."""
    for (remote_connection, _remote_mode), holder in remote_sessions.items():
        if remote_connection == connection_name and holder != local_station_name:
            return holder
    return None


def parse_chat_command(text: str) -> Tuple[str, str]:
    """Return (command, payload) where command includes leading slash or empty."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return "", stripped
    parts = stripped.split(maxsplit=1)
    command = parts[0].lower()
    payload = parts[1].strip() if len(parts) > 1 else ""
    return command, payload

