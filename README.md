# PocketWand

Turn any phone into a motion controller for your Python program. The phone streams its rotation through its web browser, so there's no app to install, and it works on iPhone and Android, on any network (campus Wi-Fi included).

## Try the demo

```sh
pip install "pocketwand[demo] @ git+https://github.com/<you>/pocketwand"
pocketwand demo
```

1. A window opens with a QR code (it takes a few seconds to get a public link).
2. Scan it with your phone's camera and open the link.
3. Tap **Enable motion** and allow access.
4. Point your phone at the screen and move it. The phone on screen copies it.

Press **R** (or the Recentre button on the phone) to make "pointing at the screen" count as straight ahead again.

`pocketwand print` does the same without a window and prints the Controller state to the terminal.

## Use it in your own Game

```python
import pocketwand

room = pocketwand.Room()                  # starts the server and tunnel, prints a QR code
room.on_join = lambda c: print("joined slot", c.slot)

while True:
    c = room.controller(0)             # never None; an empty Slot reads as disconnected
    if c.connected:
        c.orientation                  # Quaternion(w, x, y, z)
        c.orientation.matrix()         # 3x3 rotation matrix
        yaw, pitch, roll = c.euler     # degrees
        c.button                       # True while the on-screen button is held
    # c.recenter() makes the current facing count as straight ahead
```

**Frames.** Orientation rotates the phone's frame (+X right edge, +Y top of the phone, +Z out of the screen) into the world frame (+X right, +Y towards your screen, +Z up). Recentring only changes heading, so tilt always matches gravity.

**Several phones.** Every phone that opens the link gets its own Slot (`room.controller(1)`, …). A phone that reconnects gets its old Slot back. `room.controllers` lists the connected ones.

State is updated on a background thread; reading it from your game loop every frame is safe and cheap.

## How it works

`Room()` runs a small web server on your computer and opens a free [Cloudflare quick tunnel](https://try.cloudflare.com) to it (the `cloudflared` program is downloaded automatically on first run). The phone opens the page over HTTPS, which iOS requires before a page can read motion sensors, and streams its orientation back over a WebSocket. Both sides only make outgoing connections, so firewalls and campus client isolation don't get in the way.

Needs Python 3.10+ and an internet connection.
