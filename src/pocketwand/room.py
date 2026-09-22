"""The Game-facing API: a Room that Controllers join, polled for their state."""

from __future__ import annotations

import asyncio
import secrets
import socket
import threading
from typing import Callable

from .orientation import Quaternion, recentre_offset
from .server import Server
from .tunnel import Tunnel


class Controller:
    """The live state of one Slot. Safe to read from any thread, every frame."""

    def __init__(self, slot: int):
        self.slot = slot
        self._lock = threading.Lock()
        self._raw = Quaternion.identity()
        self._offset = Quaternion.identity()
        self._button = False
        self._connected = False
        self._has_data = False

    @property
    def orientation(self) -> Quaternion:
        """Rotation from phone frame to world frame (+X right, +Y towards the screen, +Z up)."""
        with self._lock:
            return self._offset * self._raw

    @property
    def euler(self) -> tuple[float, float, float]:
        """(yaw, pitch, roll) in degrees. See Quaternion.euler."""
        return self.orientation.euler()

    @property
    def button(self) -> bool:
        with self._lock:
            return self._button

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    def recenter(self) -> None:
        """Make the direction the phone currently faces count as straight ahead."""
        with self._lock:
            self._offset = recentre_offset(self._raw)

    def __repr__(self) -> str:
        yaw, pitch, roll = self.euler
        return (
            f"Controller(slot={self.slot}, connected={self.connected}, button={self.button}, "
            f"yaw={yaw:.0f}, pitch={pitch:.0f}, roll={roll:.0f})"
        )

    # Called by the server thread.

    def _update(self, raw: Quaternion, button: bool) -> None:
        with self._lock:
            first = not self._has_data
            self._raw = raw
            self._button = button
            self._has_data = True
        if first:
            self.recenter()

    def _set_connected(self, connected: bool) -> None:
        with self._lock:
            self._connected = connected


class Slots:
    """Hands out Slots, giving a returning Controller its old one back."""

    def __init__(self):
        self._by_id: dict[str, int] = {}

    def claim(self, controller_id: str) -> int:
        if controller_id not in self._by_id:
            self._by_id[controller_id] = len(self._by_id)
        return self._by_id[controller_id]


class Room:
    """One Game's session. Creating it starts the server and the public tunnel.

    >>> room = pocketwand.Room()
    >>> room.controller(0).euler
    """

    def __init__(self, *, tunnel: bool = True, port: int = 0, show_qr: bool = True):
        self.code = secrets.token_urlsafe(6)
        self.on_join: Callable[[Controller], None] | None = None
        self.on_leave: Callable[[Controller], None] | None = None

        self._controllers: dict[int, Controller] = {}
        self._controllers_lock = threading.Lock()
        self._slots = Slots()

        self.port = port or _free_port()
        self._loop = asyncio.new_event_loop()
        self._server = Server(self, self._loop, host="127.0.0.1" if tunnel else "0.0.0.0", port=self.port)
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True, name="pocketwand-server")
        self._thread.start()
        ready.wait()

        if tunnel:
            self._tunnel: Tunnel | None = Tunnel(self.port)
            base = self._tunnel.url
        else:
            self._tunnel = None
            base = f"http://{_lan_ip()}:{self.port}"
        self.join_url = f"{base}/?room={self.code}"

        if show_qr:
            self.print_qr()

    def controller(self, slot: int = 0) -> Controller:
        """The Controller in `slot`. Never None: an empty Slot reads as disconnected."""
        with self._controllers_lock:
            if slot not in self._controllers:
                self._controllers[slot] = Controller(slot)
            return self._controllers[slot]

    @property
    def controllers(self) -> list[Controller]:
        """Every Controller that is currently connected, ordered by Slot."""
        with self._controllers_lock:
            return [c for _, c in sorted(self._controllers.items()) if c.connected]

    def print_qr(self) -> None:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(self.join_url)
        qr.print_ascii(invert=True)
        print(f"Scan with your phone, or open: {self.join_url}")

    def close(self) -> None:
        if self._tunnel:
            self._tunnel.close()
        if self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._server.stop(), self._loop).result(timeout=3)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)

    def __enter__(self) -> Room:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _run(self, ready: threading.Event) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._server.start())
        ready.set()
        self._loop.run_forever()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _lan_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"
