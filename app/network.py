"""UDP broadcast bus for station discovery, session state, and chat messages."""

import json
import socket
import threading
import time
import uuid
from typing import Dict, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal

from .constants import STATION_TIMEOUT_SECONDS, UDP_BUFFER, UDP_PORT


class NetworkBus(QObject):
    """Background UDP transport with Qt signals for UI-safe event delivery."""

    # station_seen: station_name, ip
    station_seen = pyqtSignal(str, str)
    # session_state: connection_name, mode, station_name, opened, station_id
    session_state = pyqtSignal(str, str, str, bool, str)
    # chat_received: sender_station, text, target, is_action, is_notify
    chat_received = pyqtSignal(str, str, str, bool, bool)
    # takeover_notice: station_name, connection_name, previous_holder_name
    takeover_notice = pyqtSignal(str, str, str)
    # topic_changed: station_name, topic_text
    topic_changed = pyqtSignal(str, str)
    # away_changed: station_name, is_away, message
    away_changed = pyqtSignal(str, bool, str)
    # nick_changed: old_name, new_name
    nick_changed = pyqtSignal(str, str)
    # session_sync_requested: requesting_station_name
    session_sync_requested = pyqtSignal(str)

    def __init__(self, station_name: str) -> None:
        """Open the UDP socket and start listener thread immediately."""
        super().__init__()
        self.station_id = str(uuid.uuid4())
        self.station_name = station_name
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("", UDP_PORT))
        self._running = True
        # station_id -> (station_name, ip, last_seen_timestamp)
        self._stations_by_id: Dict[str, Tuple[str, str, float]] = {}
        # (connection, mode) -> (holder_station_id, opened_timestamp)
        self._remote_sessions: Dict[Tuple[str, str], Tuple[str, float]] = {}
        self._listener = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener.start()

    @property
    def stations(self) -> Dict[str, Tuple[str, float]]:
        """Return only recently seen stations (age-filtered)."""
        now = time.time()
        result: Dict[str, Tuple[str, float]] = {}
        for station_name, ip, ts in self._stations_by_id.values():
            if now - ts <= STATION_TIMEOUT_SECONDS:
                result[station_name] = (ip, ts)
        return result

    @property
    def remote_sessions(self) -> Dict[Tuple[str, str], str]:
        """Snapshot mapping of (connection, mode) -> station currently holding it."""
        now = time.time()
        resolved: Dict[Tuple[str, str], str] = {}
        for key, (holder_id, _opened_ts) in self._remote_sessions.items():
            station = self._stations_by_id.get(holder_id)
            if station is None:
                continue
            station_name, _ip, ts = station
            if now - ts <= STATION_TIMEOUT_SECONDS:
                resolved[key] = station_name
        return resolved

    @property
    def remote_session_holders(self) -> Dict[Tuple[str, str], str]:
        """Return mapping of (connection, mode) -> holder station_id."""
        now = time.time()
        holders: Dict[Tuple[str, str], str] = {}
        for key, (holder_id, _opened_ts) in self._remote_sessions.items():
            station = self._stations_by_id.get(holder_id)
            if station is None:
                continue
            _name, _ip, seen_ts = station
            if now - seen_ts <= STATION_TIMEOUT_SECONDS:
                holders[key] = holder_id
        return holders

    def station_name_for_id(self, station_id: str) -> str:
        """Resolve latest display name for station id."""
        station = self._stations_by_id.get(station_id)
        if station is None:
            return "Unknown station"
        return station[0]

    @property
    def remote_sessions_info(self) -> Dict[Tuple[str, str], Tuple[str, float]]:
        """Return mapping of (connection, mode) -> (station_name, age_seconds)."""
        now = time.time()
        info: Dict[Tuple[str, str], Tuple[str, float]] = {}
        for key, (holder_id, opened_ts) in self._remote_sessions.items():
            station = self._stations_by_id.get(holder_id)
            if station is None:
                continue
            station_name, _ip, seen_ts = station
            if now - seen_ts > STATION_TIMEOUT_SECONDS:
                continue
            info[key] = (station_name, max(0.0, now - opened_ts))
        return info

    def set_station_name(self, name: str) -> None:
        """Update local station identity and announce it to peers."""
        self.station_name = name
        self.send_hello()

    def close(self) -> None:
        """Stop listener loop and close the UDP socket."""
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass

    def send_hello(self) -> None:
        """Broadcast presence packet used for station discovery."""
        self._send({"type": "hello", "station": self.station_name})

    def send_session(self, connection: str, mode: str, opened: bool) -> None:
        """Broadcast local session open/close state for lock awareness."""
        self._send(
            {
                "type": "session",
                "station": self.station_name,
                "connection": connection,
                "mode": mode,
                "opened": opened,
            }
        )

    def send_chat(
        self,
        text: str,
        to_station: Optional[str] = None,
        is_action: bool = False,
        is_notify: bool = False,
    ) -> None:
        """Broadcast chat message, optionally targeting a specific station name."""
        self._send(
            {
                "type": "chat",
                "station": self.station_name,
                "to": to_station or "*",
                "text": text,
                "is_action": is_action,
                "is_notify": is_notify,
            }
        )

    def send_takeover(self, connection: str, previous_holder: str) -> None:
        """Broadcast a session takeover event for UI notice logs."""
        self._send(
            {
                "type": "takeover",
                "station": self.station_name,
                "connection": connection,
                "previous_holder": previous_holder,
            }
        )

    def send_topic(self, topic: str) -> None:
        """Broadcast global topic changes to all online stations."""
        self._send(
            {
                "type": "topic",
                "station": self.station_name,
                "topic": topic,
            }
        )

    def send_away(self, is_away: bool, message: str = "") -> None:
        """Broadcast away status changes to all online stations."""
        self._send(
            {
                "type": "away",
                "station": self.station_name,
                "is_away": bool(is_away),
                "message": message,
            }
        )

    def send_session_sync_request(self) -> None:
        """Ask peers to immediately rebroadcast currently open sessions."""
        self._send(
            {
                "type": "session_sync_request",
                "station": self.station_name,
            }
        )

    def _send(self, payload: Dict[str, object]) -> None:
        """Attach sender metadata and send payload to LAN broadcast address."""
        payload["id"] = self.station_id
        payload["ts"] = time.time()
        blob = json.dumps(payload).encode("utf-8", errors="replace")
        self._sock.sendto(blob, ("255.255.255.255", UDP_PORT))

    def _listen_loop(self) -> None:
        """Receive packets forever, update local state, and emit Qt signals."""
        while self._running:
            try:
                data, addr = self._sock.recvfrom(UDP_BUFFER)
            except OSError:
                break
            try:
                packet = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(packet, dict):
                continue
            packet_station_id = str(packet.get("id", "")).strip()
            if packet_station_id == self.station_id:
                # Ignore our own broadcast packets.
                continue
            ptype = packet.get("type")
            station = str(packet.get("station", "")).strip() or "Unknown"
            ip = str(addr[0])
            previous = self._stations_by_id.get(packet_station_id)
            if previous is not None:
                previous_name = previous[0]
                if previous_name != station:
                    self.nick_changed.emit(previous_name, station)
            self._stations_by_id[packet_station_id] = (station, ip, time.time())
            self.station_seen.emit(station, ip)

            if ptype == "session":
                # Keep last known holder for each session key.
                connection = str(packet.get("connection", ""))
                mode = str(packet.get("mode", ""))
                opened = bool(packet.get("opened", False))
                if connection and mode:
                    key = (connection, mode)
                    if opened:
                        existing = self._remote_sessions.get(key)
                        if existing and existing[0] == packet_station_id:
                            # Heartbeat from same holder: keep original opened timestamp.
                            self._remote_sessions[key] = (packet_station_id, existing[1])
                        else:
                            # New holder or reopen: start a fresh age counter.
                            self._remote_sessions[key] = (packet_station_id, time.time())
                    else:
                        self._remote_sessions.pop(key, None)
                    self.session_state.emit(connection, mode, station, opened, packet_station_id)
            elif ptype == "chat":
                # Deliver all broadcast messages and direct messages for this station.
                target = str(packet.get("to", "*"))
                if target not in ("*", self.station_name):
                    continue
                text = str(packet.get("text", ""))
                is_action = bool(packet.get("is_action", False))
                is_notify = bool(packet.get("is_notify", False))
                self.chat_received.emit(station, text, target, is_action, is_notify)
            elif ptype == "takeover":
                connection = str(packet.get("connection", "")).strip()
                previous_holder = str(packet.get("previous_holder", "")).strip() or "Unknown station"
                if connection:
                    self.takeover_notice.emit(station, connection, previous_holder)
            elif ptype == "topic":
                topic = str(packet.get("topic", "")).strip()
                if topic:
                    self.topic_changed.emit(station, topic)
            elif ptype == "away":
                is_away = bool(packet.get("is_away", False))
                message = str(packet.get("message", "")).strip()
                self.away_changed.emit(station, is_away, message)
            elif ptype == "session_sync_request":
                self.session_sync_requested.emit(station)
