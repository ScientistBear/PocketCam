"""Dependency-free local TCP server used by the PocketCam Blender add-on.

The protocol is newline-delimited UTF-8 JSON. Pose packets are coalesced so a
busy phone cannot flood Blender's main thread; commands are queued in order.
This module intentionally has no Blender imports so it can be unit tested with
normal CPython.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
from dataclasses import dataclass
from typing import Any


PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 256 * 1024


@dataclass(frozen=True)
class ServerEvent:
    kind: str
    payload: dict[str, Any]


def discover_local_ip() -> str:
    """Return the preferred LAN address without sending internet traffic."""

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # UDP connect only asks the OS which interface it would use.
        probe.connect(("1.1.1.1", 80))
        return str(probe.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        probe.close()


class PoseServer:
    """Single-client TCP server with a main-thread-friendly event interface."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8766) -> None:
        self.host = host
        self.port = int(port)
        self.bound_port = int(port)
        self._listener: socket.socket | None = None
        self._client: socket.socket | None = None
        self._client_address: tuple[str, int] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._events: queue.Queue[ServerEvent] = queue.Queue(maxsize=256)
        self._pose_lock = threading.Lock()
        self._initial_pose: dict[str, Any] | None = None
        self._latest_pose: dict[str, Any] | None = None
        self._pose_started = False
        self._control_outbound: queue.Queue[bytes] = queue.Queue(maxsize=64)
        self._preview_lock = threading.Lock()
        self._latest_preview: bytes | None = None
        self._sender_thread: threading.Thread | None = None
        self._state_lock = threading.Lock()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    @property
    def client_connected(self) -> bool:
        with self._state_lock:
            return self._client is not None

    @property
    def client_address(self) -> tuple[str, int] | None:
        with self._state_lock:
            return self._client_address

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._serve,
            name="PocketCamPoseServer",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._state_lock:
            client = self._client
            listener = self._listener
        for sock in (client, listener):
            if sock is None:
                continue
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        with self._state_lock:
            self._client = None
            self._client_address = None
            self._listener = None

    def pop_latest_pose(self) -> dict[str, Any] | None:
        with self._pose_lock:
            if self._initial_pose is not None:
                pose = self._initial_pose
                self._initial_pose = None
                return pose
            pose = self._latest_pose
            self._latest_pose = None
            return pose

    def drain_events(self, limit: int = 64) -> list[ServerEvent]:
        events: list[ServerEvent] = []
        for _ in range(max(0, limit)):
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return events

    def send_json(self, payload: dict[str, Any]) -> bool:
        """Queue a small status/control packet without blocking Blender's main thread."""

        encoded = self._encode(payload)
        with self._state_lock:
            connected = self._client is not None
        if not connected:
            return False
        try:
            self._control_outbound.put_nowait(encoded)
        except queue.Full:
            # Control traffic is tiny and rare. If a broken client stops reading,
            # keep recent state instead of ever stalling Blender's UI thread.
            try:
                self._control_outbound.get_nowait()
            except queue.Empty:
                pass
            try:
                self._control_outbound.put_nowait(encoded)
            except queue.Full:
                return False
        return True

    def send_preview(self, payload: dict[str, Any]) -> bool:
        """Coalesce camera frames so a slow phone never builds a stale backlog."""

        encoded = self._encode(payload)
        with self._state_lock:
            connected = self._client is not None
        if not connected:
            return False
        with self._preview_lock:
            self._latest_preview = encoded
        return True

    @staticmethod
    def _encode(payload: dict[str, Any]) -> bytes:
        return (
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            + b"\n"
        )

    def _clear_outbound(self) -> None:
        while True:
            try:
                self._control_outbound.get_nowait()
            except queue.Empty:
                break
        with self._preview_lock:
            self._latest_preview = None

    def _sender(self, client: socket.socket) -> None:
        while not self._stop.is_set():
            with self._state_lock:
                if self._client is not client:
                    return
            encoded: bytes | None = None
            try:
                encoded = self._control_outbound.get(timeout=0.01)
            except queue.Empty:
                with self._preview_lock:
                    encoded = self._latest_preview
                    self._latest_preview = None
            if encoded is None:
                continue
            try:
                client.sendall(encoded)
            except OSError:
                return

    def _queue_event(self, kind: str, payload: dict[str, Any]) -> None:
        event = ServerEvent(kind=kind, payload=payload)
        try:
            self._events.put_nowait(event)
        except queue.Full:
            # Retain recent commands rather than blocking the network thread.
            try:
                self._events.get_nowait()
            except queue.Empty:
                pass
            try:
                self._events.put_nowait(event)
            except queue.Full:
                pass

    def _serve(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((self.host, self.port))
            listener.listen(1)
            listener.settimeout(0.5)
            self.bound_port = int(listener.getsockname()[1])
            with self._state_lock:
                self._listener = listener
            self._queue_event("server_started", {"port": self.bound_port})

            while not self._stop.is_set():
                try:
                    client, address = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                client.settimeout(0.5)
                self._clear_outbound()
                with self._pose_lock:
                    self._initial_pose = None
                    self._latest_pose = None
                    self._pose_started = False
                with self._state_lock:
                    self._client = client
                    self._client_address = (str(address[0]), int(address[1]))
                sender = threading.Thread(
                    target=self._sender,
                    args=(client,),
                    name="PocketCamFrameSender",
                    daemon=True,
                )
                self._sender_thread = sender
                sender.start()
                self._queue_event(
                    "client_connected",
                    {"host": str(address[0]), "port": int(address[1])},
                )
                self._read_client(client)
                with self._state_lock:
                    if self._client is client:
                        self._client = None
                        self._client_address = None
                try:
                    client.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    client.close()
                except OSError:
                    pass
                if sender.is_alive():
                    sender.join(timeout=0.5)
                self._queue_event("client_disconnected", {})
        except OSError as exc:
            self._queue_event("server_error", {"message": str(exc)})
        finally:
            try:
                listener.close()
            except OSError:
                pass
            with self._state_lock:
                if self._listener is listener:
                    self._listener = None

    def _read_client(self, client: socket.socket) -> None:
        buffer = bytearray()
        while not self._stop.is_set():
            try:
                chunk = client.recv(64 * 1024)
            except socket.timeout:
                continue
            except OSError:
                return
            if not chunk:
                return
            buffer.extend(chunk)
            if len(buffer) > MAX_LINE_BYTES and b"\n" not in buffer:
                self._queue_event("protocol_error", {"message": "Packet exceeded size limit"})
                return

            while b"\n" in buffer:
                raw_line, _, remainder = buffer.partition(b"\n")
                buffer = bytearray(remainder)
                if not raw_line.strip():
                    continue
                if len(raw_line) > MAX_LINE_BYTES:
                    self._queue_event("protocol_error", {"message": "Packet exceeded size limit"})
                    continue
                self._handle_line(raw_line)

    def _handle_line(self, raw_line: bytes) -> None:
        try:
            payload = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._queue_event("protocol_error", {"message": f"Invalid JSON: {exc}"})
            return
        if not isinstance(payload, dict):
            self._queue_event("protocol_error", {"message": "Packet must be a JSON object"})
            return

        packet_type = payload.get("type")
        if packet_type == "pose":
            with self._pose_lock:
                if not self._pose_started:
                    # Recenter must use a real first frame. Without this slot, a
                    # 60 FPS phone can overwrite pose 1 before Blender's first
                    # 10 ms timer tick, making the next pose the zero point too.
                    self._initial_pose = payload
                    self._pose_started = True
                else:
                    self._latest_pose = payload
            return
        if packet_type in {"hello", "command", "settings", "select_camera", "ping"}:
            self._queue_event(str(packet_type), payload)
            return
        self._queue_event(
            "protocol_error",
            {"message": f"Unknown packet type: {packet_type!r}"},
        )

