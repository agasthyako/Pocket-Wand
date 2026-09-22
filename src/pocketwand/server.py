"""Serves the Controller page and receives Controller messages over a WebSocket."""

from __future__ import annotations

import asyncio
import json
from importlib.resources import files
from typing import TYPE_CHECKING

from aiohttp import WSMsgType, web

from .orientation import from_device_angles

if TYPE_CHECKING:
    from .room import Room

PAGE = files("pocketwand").joinpath("static/controller.html")


class Server:
    def __init__(self, room: Room, loop: asyncio.AbstractEventLoop, host: str, port: int):
        self.room = room
        self.loop = loop
        self.host = host
        self.port = port
        self._sockets: dict[int, web.WebSocketResponse] = {}

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._page)
        app.router.add_get("/ws", self._ws)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, self.host, self.port).start()

    async def stop(self) -> None:
        for ws in list(self._sockets.values()):
            await ws.close()
        await self._runner.cleanup()

    async def _page(self, request: web.Request) -> web.Response:
        return web.Response(
            text=PAGE.read_text(encoding="utf-8"),
            content_type="text/html",
            headers={"Cache-Control": "no-store"},
        )

    async def _ws(self, request: web.Request) -> web.StreamResponse:
        if request.query.get("room") != self.room.code:
            raise web.HTTPForbidden(text="Wrong or missing Room code")
        controller_id = request.query.get("id", "")
        if not controller_id:
            raise web.HTTPBadRequest(text="Missing controller id")

        ws = web.WebSocketResponse(heartbeat=5)
        await ws.prepare(request)

        slot = self.room._slots.claim(controller_id)
        controller = self.room.controller(slot)

        # The same phone reconnecting (e.g. a reloaded tab) replaces its old connection.
        old = self._sockets.get(slot)
        self._sockets[slot] = ws
        if old is not None:
            await old.close()

        controller._set_connected(True)
        await ws.send_json({"t": "slot", "slot": slot})
        _call(self.room.on_join, controller)

        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                    if data.get("t") == "recentre":
                        controller.recenter()
                    elif "a" in data:
                        raw = from_device_angles(float(data["a"] or 0), float(data["b"] or 0), float(data["g"] or 0))
                        controller._update(raw, bool(data.get("p")))
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue  # ignore malformed messages
        finally:
            if self._sockets.get(slot) is ws:
                del self._sockets[slot]
                controller._set_connected(False)
                _call(self.room.on_leave, controller)
        return ws


def _call(callback, controller) -> None:
    if callback is None:
        return
    try:
        callback(controller)
    except Exception as e:  # a buggy Game callback must not kill the server
        print(f"pocketwand: callback raised {e!r}")
