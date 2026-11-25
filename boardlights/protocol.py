"""Pure-Python encoding of the Aurora (Kilter/Tension/...) LED Bluetooth protocol.

No Bluetooth or hardware needed here, so this module is easy to read, test and
experiment with. It mirrors ``climbdex/static/js/bluetooth.js`` (which is based on
Philipp Bazun's reverse-engineering write-up:
https://web.archive.org/web/20240203155713/https://www.bazun.me/blog/kiterboard/).

Only the "API level 3" format is implemented (3 bytes per LED). Boards that report
``@3`` at the end of their Bluetooth name (e.g. ``Kilter Board#751814@3``) use it.

Wire format
-----------
A *frame* is "this set of LEDs should be on, with these colours". It is encoded as:

1. Every LED becomes 3 bytes: ``[position_low, position_high, colour]`` where the
   colour is packed into one byte as ``RRRGGGBB`` (so only 8 x 8 x 4 colours exist).
2. LEDs are grouped into *messages* of at most 255 bytes. Each message starts with
   a type byte: ``PACKET_ONLY`` (the frame fits in one message) or
   ``PACKET_FIRST`` / ``PACKET_MIDDLE`` / ``PACKET_LAST``.
3. Each message is wrapped as ``[0x01, length, checksum, 0x02, *body, 0x03]``.
4. The concatenated bytes are written to the board in chunks of 20 bytes (the BLE
   default payload size).
"""

from __future__ import annotations

from typing import Iterable, Mapping, Union

SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
"""Nordic UART service exposed by the board's LED controller."""
CHARACTERISTIC_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
"""Writable characteristic (UART RX) that receives the LED data."""
ADVERTISED_SERVICE_UUID = "4488b571-7806-4df6-bcff-a2897e4953ff"
"""Service UUID Aurora boards advertise (used to recognise boards while scanning)."""

MAX_BLUETOOTH_MESSAGE_SIZE = 20
MESSAGE_BODY_MAX_LENGTH = 255

PACKET_MIDDLE = 81
PACKET_FIRST = 82
PACKET_LAST = 83
PACKET_ONLY = 84

Color = Union[str, tuple]
"""A colour: ``"FF0000"``, ``"#ff0000"`` or an ``(r, g, b)`` tuple with 0-255 values."""


def to_hex(color: Color) -> str:
    """Normalise a colour to a 6-character upper-case hex string."""
    if isinstance(color, str):
        hex_color = color.lstrip("#").upper()
        if len(hex_color) != 6:
            raise ValueError(f"Expected a colour like 'FF0000', got {color!r}")
        int(hex_color, 16)  # raises ValueError if not hex
        return hex_color
    r, g, b = color
    for v in (r, g, b):
        if not 0 <= int(v) <= 255:
            raise ValueError(f"RGB values must be 0-255, got {color!r}")
    return f"{int(r):02X}{int(g):02X}{int(b):02X}"


def checksum(data: Iterable[int]) -> int:
    total = 0
    for value in data:
        total = (total + value) & 255
    return ~total & 255


def wrap_bytes(body: list[int]) -> list[int]:
    if len(body) > MESSAGE_BODY_MAX_LENGTH:
        raise ValueError(f"Message body too long ({len(body)} > {MESSAGE_BODY_MAX_LENGTH})")
    return [1, len(body), checksum(body), 2, *body, 3]


def encode_position(position: int) -> list[int]:
    if not 0 <= position <= 0xFFFF:
        raise ValueError(f"LED position out of range: {position}")
    return [position & 0xFF, (position >> 8) & 0xFF]


def encode_color(color: Color) -> int:
    """Pack a colour into one byte (3 bits red, 3 bits green, 2 bits blue)."""
    hex_color = to_hex(color)
    r = int(hex_color[0:2], 16) // 32
    g = int(hex_color[2:4], 16) // 32
    b = int(hex_color[4:6], 16) // 64
    return (r << 5) | (g << 2) | b


def encode_led(position: int, color: Color) -> list[int]:
    return [*encode_position(position), encode_color(color)]


def build_frame(leds: Mapping[int, Color]) -> bytes:
    """Encode ``{led_position: colour}`` into the bytes the board expects.

    An empty mapping produces a single empty message, which turns all LEDs off.
    """
    messages: list[list[int]] = []
    current = [PACKET_MIDDLE]
    for position, color in leds.items():
        if len(current) + 3 > MESSAGE_BODY_MAX_LENGTH:
            messages.append(current)
            current = [PACKET_MIDDLE]
        current.extend(encode_led(int(position), color))
    messages.append(current)

    if len(messages) == 1:
        messages[0][0] = PACKET_ONLY
    else:
        messages[0][0] = PACKET_FIRST
        messages[-1][0] = PACKET_LAST

    out: list[int] = []
    for message in messages:
        out.extend(wrap_bytes(message))
    return bytes(out)


def split_chunks(data: bytes, size: int = MAX_BLUETOOTH_MESSAGE_SIZE) -> list[bytes]:
    """Split encoded data into BLE-sized writes."""
    return [data[i : i + size] for i in range(0, len(data), size)]
