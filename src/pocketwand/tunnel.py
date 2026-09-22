"""Gives the local server a public HTTPS address with a Cloudflare quick tunnel.

A tunnel rather than a hosted relay or a LAN-only server: iOS needs HTTPS for motion
sensors, campus Wi-Fi blocks device-to-device traffic, and nobody has to host anything.
"""

from __future__ import annotations

import atexit
import json
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


class Tunnel:
    def __init__(self, port: int, timeout: float = 30.0):
        exe = _cloudflared()
        print("pocketwand: opening a public tunnel (a few seconds)...")
        self._process = subprocess.Popen(
            [exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        atexit.register(self.close)

        found = threading.Event()
        self.url = ""

        def read_log():
            # Keep draining stderr for the tunnel's whole life, or cloudflared blocks once the pipe fills.
            for line in self._process.stderr:
                if not self.url and (m := URL_PATTERN.search(line)):
                    self.url = m.group(0)
                    found.set()

        threading.Thread(target=read_log, daemon=True, name="pocketwand-tunnel-log").start()
        if not found.wait(timeout):
            self.close()
            raise RuntimeError("cloudflared did not report a tunnel URL; check your internet connection")
        _wait_until_reachable(self.url, timeout)

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()


def _cloudflared() -> str:
    """A cloudflared already on PATH, otherwise one downloaded by pycloudflared on first use."""
    if exe := shutil.which("cloudflared"):
        return exe
    from pycloudflared.util import download, get_info

    info = get_info()
    if not Path(info.executable).exists():
        download(info)
    return info.executable


def _wait_until_reachable(url: str, timeout: float) -> None:
    """New quick-tunnel hostnames take a few seconds to exist; don't hand out a dead link.

    Only ask Cloudflare's own DNS. Looking the name up through the local resolver
    before it exists makes that resolver cache "no such host" for 30 minutes (the
    trycloudflare.com negative TTL), breaking the link for every device on the network.
    """
    host = url.removeprefix("https://")
    query = f"https://1.1.1.1/dns-query?name={host}&type=A"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(query, headers={"accept": "application/dns-json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if json.load(resp).get("Answer"):
                    return
        except Exception:
            pass
        time.sleep(1)
    print("pocketwand: tunnel is slow to come up; the link may take a moment to work")
