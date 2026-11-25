"""Command line interface: ``python -m boardlights <command>``.

Examples::

    python -m boardlights scan
    python -m boardlights describe --address FC:0C:87:2B:53:25
    python -m boardlights light 5 FF0000 12 00FF00
    python -m boardlights climb "Swiss Chard"
    python -m boardlights rainbow --seconds 20
    python -m boardlights clear
"""

from __future__ import annotations

import argparse
import asyncio
import colorsys
import sys

from .board import Board, scan
from .wall import Wall, list_configurations


def _rgb_hex(h: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1, 1)
    return f"{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


async def _connect(args) -> Board:
    board = await Board.connect(address=args.address, name_contains=args.name)
    print(f"Connected to {board.address}")
    return board


async def run(args) -> int:
    if args.command == "scan":
        devices = await scan(timeout=args.timeout, only_boards=not args.all)
        if not devices:
            print("Nothing found." + ("" if args.all else " Try --all to list every BLE device."))
        for d in devices:
            print(d)
        return 0

    if args.command == "configs":
        for row in list_configurations(args.db) if args.db else list_configurations():
            print("layout {:>2} {:<28} size {:>2} {:<10} {:<28} {:>4} LEDs".format(
                row[0], row[1], row[2], row[3], row[4] or "", row[5]))
        return 0

    board = await _connect(args)
    try:
        if args.command == "describe":
            print(await board.describe())
        elif args.command == "clear":
            await board.clear()
        elif args.command == "light":
            pairs = args.pairs
            if len(pairs) % 2:
                print("Give pairs of <position> <colour>, e.g. 5 FF0000", file=sys.stderr)
                return 2
            await board.show({int(pairs[i]): pairs[i + 1] for i in range(0, len(pairs), 2)})
        elif args.command == "climb":
            wall = Wall(args.layout, args.size)
            matches = wall.find_climbs(args.climb_name, limit=5)
            if not matches:
                print(f"No climb matching {args.climb_name!r}", file=sys.stderr)
                return 1
            climb = next((c for c in matches if c.name == args.climb_name), matches[0])
            print(f"Lighting {climb.name!r}")
            await board.show(wall.frames_to_leds(climb.frames))
        elif args.command == "rainbow":
            wall = Wall(args.layout, args.size)
            holds = wall.unique_holds()
            min_y = min(h.y for h in holds)
            height = max(h.y for h in holds) - min_y or 1
            n = await board.animate(
                lambda t: {h.position: _rgb_hex((h.y - min_y) / height + t * 0.3) for h in holds},
                duration=args.seconds,
                fps=args.fps,
            )
            print(f"Sent {n} frames ({n / args.seconds:.1f} fps)")
            await board.clear()
    finally:
        await board.disconnect()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m boardlights", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def with_board(p):
        p.add_argument("--address", help="Bluetooth address (default: closest board found)")
        p.add_argument("--name", help="pick the board whose name contains this text")
        return p

    def with_wall(p):
        p.add_argument("--layout", type=int, default=8, help="layout id (default 8 = Kilter Homewall)")
        p.add_argument("--size", type=int, default=18, help="size id (default 18 = 7x10 Mainline)")
        return p

    p = sub.add_parser("scan", help="list nearby boards")
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--all", action="store_true", help="show every BLE device, not just boards")

    p = sub.add_parser("configs", help="list layout/size ids in the database")
    p.add_argument("--db", help="path to db.sqlite3")

    with_board(sub.add_parser("describe", help="print the board's BLE services"))
    with_board(sub.add_parser("clear", help="turn all LEDs off"))
    p = with_board(sub.add_parser("light", help="light LEDs: <position> <colour> ..."))
    p.add_argument("pairs", nargs="+")
    p = with_wall(with_board(sub.add_parser("climb", help="light a climb from the database")))
    p.add_argument("climb_name")
    p = with_wall(with_board(sub.add_parser("rainbow", help="rainbow demo animation")))
    p.add_argument("--seconds", type=float, default=15)
    p.add_argument("--fps", type=float, default=4)

    args = parser.parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
