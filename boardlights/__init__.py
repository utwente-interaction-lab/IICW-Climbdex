"""boardlights: control the LEDs of an Aurora-style climbing board (Kilter, Tension, ...)
from Python, over Bluetooth Low Energy.

Experimental, made for students. See docs/controlling-lights.md.

    from boardlights import Board, Wall

    wall = Wall(layout_id=8, size_id=18)      # Kilter Homewall 7x10 Mainline
    board = await Board.connect()
    await board.show(wall.climb_leds("Swiss Chard"))
"""

from .protocol import build_frame, encode_color, to_hex
from .wall import Climb, Hold, Wall, fill, list_configurations

try:  # bleak is only needed when actually talking to a board
    from .board import Board, FoundDevice, scan
except ImportError:  # pragma: no cover
    pass

__all__ = [
    "Board",
    "Climb",
    "FoundDevice",
    "Hold",
    "Wall",
    "build_frame",
    "encode_color",
    "fill",
    "list_configurations",
    "scan",
    "to_hex",
]
