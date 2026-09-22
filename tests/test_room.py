import asyncio
import json

import aiohttp
import pytest

from pocketwand import Room
from pocketwand.room import Slots


def test_returning_controller_reclaims_its_slot():
    slots = Slots()
    assert slots.claim("phone-a") == 0
    assert slots.claim("phone-b") == 1
    assert slots.claim("phone-a") == 0
    assert slots.claim("phone-c") == 2


def test_empty_slot_reads_as_disconnected():
    room = Room(tunnel=False, show_qr=False)
    try:
        c = room.controller(3)
        assert not c.connected
        assert c.euler == pytest.approx((0, 0, 0))
    finally:
        room.close()


@pytest.fixture
def room():
    r = Room(tunnel=False, show_qr=False)
    yield r
    r.close()


def ws_url(room, code, controller_id="phone-a"):
    return f"ws://127.0.0.1:{room.port}/ws?room={code}&id={controller_id}"


def run(coro):
    return asyncio.run(coro)


def test_wrong_room_code_is_refused(room):
    async def go():
        async with aiohttp.ClientSession() as s:
            with pytest.raises(aiohttp.WSServerHandshakeError):
                await s.ws_connect(ws_url(room, "wrong"))

    run(go())


def test_controller_streams_orientation_and_button(room):
    joined = []
    room.on_join = joined.append

    async def go():
        async with aiohttp.ClientSession() as s:
            async with s.ws_connect(ws_url(room, room.code)) as ws:
                assert json.loads((await ws.receive()).data) == {"t": "slot", "slot": 0}
                await ws.send_json({"a": 10, "b": 30, "g": -15, "p": 0})  # first reading recentres
                await ws.send_json({"a": 40, "b": 30, "g": -15, "p": 1})
                await asyncio.sleep(0.2)
                c = room.controller(0)
                assert c.connected and c.button
                yaw, pitch, roll = c.euler
                assert yaw == pytest.approx(30, abs=1e-6)
                assert pitch == pytest.approx(30, abs=1e-6)
                assert roll == pytest.approx(-15, abs=1e-6)
            await asyncio.sleep(0.2)

    run(go())
    assert joined == [room.controller(0)]
    assert not room.controller(0).connected


def test_reloaded_tab_replaces_old_connection_in_same_slot(room):
    async def go():
        async with aiohttp.ClientSession() as s:
            old = await s.ws_connect(ws_url(room, room.code))
            await old.receive()
            new = await s.ws_connect(ws_url(room, room.code))
            assert json.loads((await new.receive()).data)["slot"] == 0
            await asyncio.sleep(0.2)
            assert room.controller(0).connected
            assert len(room.controllers) == 1
            await new.close()
            await old.close()

    run(go())
