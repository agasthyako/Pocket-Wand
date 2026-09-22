import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="pocketwand", description="Turn your phone into a motion controller.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help in (("demo", "open a window with a 3D phone that copies your phone's rotation"),
                       ("print", "print Controller state to the terminal")):
        p = sub.add_parser(name, help=help)
        p.add_argument("--local", action="store_true",
                       help="skip the public tunnel and serve plain http on your network (phones won't send motion data without HTTPS)")
    args = parser.parse_args()

    if args.command == "demo":
        try:
            from .demo import run
        except ModuleNotFoundError as e:
            if e.name != "pygame":
                raise
            raise SystemExit('The demo needs pygame. Install it with:  pip install "pocketwand[demo]"')
        run(tunnel=not args.local)
    else:
        _print(tunnel=not args.local)


def _print(tunnel: bool) -> None:
    import time

    from . import Room

    room = Room(tunnel=tunnel)
    room.on_join = lambda c: print(f"\njoined: slot {c.slot}")
    room.on_leave = lambda c: print(f"\nleft: slot {c.slot}")
    try:
        while True:
            print(f"\r{room.controller(0)!r}    ", end="", flush=True)
            time.sleep(1 / 20)
    except KeyboardInterrupt:
        room.close()
