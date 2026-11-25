"""Talk to the board over Bluetooth Low Energy using `bleak`.

Everything here is ``async``. In a Jupyter notebook you can ``await`` directly::

    board = await Board.connect()          # first board found nearby
    await board.show({5: "FF0000"})        # LED 5 red
    await board.clear()
    await board.disconnect()

In a script, wrap it in ``asyncio.run(main())`` (see ``python -m boardlights --help``).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping, Optional, Union

from bleak import BleakClient, BleakScanner

from .protocol import (
    ADVERTISED_SERVICE_UUID,
    CHARACTERISTIC_UUID,
    Color,
    build_frame,
    split_chunks,
)

BOARD_NAME_HINTS = ("kilter", "tension", "decoy", "grasshopper", "touchstone", "aurora")


@dataclass
class FoundDevice:
    name: Optional[str]
    address: str
    rssi: int
    looks_like_board: bool

    def __str__(self) -> str:
        flag = "board?" if self.looks_like_board else "      "
        return f"{flag} {self.address}  rssi={self.rssi:>4}  {self.name}"


async def scan(timeout: float = 5.0, only_boards: bool = True) -> list[FoundDevice]:
    """Scan for nearby BLE devices, strongest signal first.

    A device "looks like a board" when its name contains a known board name
    (e.g. "Kilter") or it advertises the Aurora service UUID.
    """
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    devices = []
    for device, adv in found.values():
        name = device.name or adv.local_name
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        is_board = ADVERTISED_SERVICE_UUID in uuids or any(
            hint in (name or "").lower() for hint in BOARD_NAME_HINTS
        )
        if is_board or not only_boards:
            devices.append(FoundDevice(name, device.address, adv.rssi, is_board))
    return sorted(devices, key=lambda d: d.rssi, reverse=True)


class Board:
    """A connection to one board's LED controller."""

    def __init__(self, address: str, timeout: float = 10.0):
        self.address = address
        self.timeout = timeout
        self._client: Optional[BleakClient] = None

    # ----- connection -------------------------------------------------------

    @classmethod
    async def connect(
        cls, address: Optional[str] = None, name_contains: Optional[str] = None, timeout: float = 10.0
    ) -> "Board":
        """Connect to a board by address, or to the closest board found by scanning.

        ``name_contains`` picks the first scanned board whose name contains that text
        (case-insensitive), handy when several boards are in range.
        """
        if address is None:
            boards = await scan()
            if name_contains:
                boards = [b for b in boards if name_contains.lower() in (b.name or "").lower()]
            if not boards:
                raise RuntimeError(
                    "No board found. Is it powered on, and is the official app disconnected? "
                    "Try `python -m boardlights scan --all`."
                )
            address = boards[0].address
        board = cls(address, timeout=timeout)
        await board._ensure_connected()
        return board

    async def _ensure_connected(self) -> BleakClient:
        if self._client is None or not self._client.is_connected:
            self._client = BleakClient(self.address, timeout=self.timeout)
            await self._client.connect()
        return self._client

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    async def __aenter__(self) -> "Board":
        await self._ensure_connected()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    # ----- lights -----------------------------------------------------------

    async def show(self, leds: Mapping[int, Color], retries: int = 1) -> None:
        """Light exactly these LEDs (``{position: colour}``); every other LED turns off."""
        data = build_frame(leds)
        for attempt in range(retries + 1):
            try:
                client = await self._ensure_connected()
                for chunk in split_chunks(data):
                    await client.write_gatt_char(CHARACTERISTIC_UUID, chunk)
                return
            except Exception:
                self._client = None
                if attempt == retries:
                    raise
                await asyncio.sleep(0.5)

    async def clear(self) -> None:
        """Turn all LEDs off."""
        await self.show({})

    async def animate(
        self,
        frame_fn: Callable[[float], Union[Mapping[int, Color], Awaitable[Mapping[int, Color]]]],
        duration: float = 10.0,
        fps: float = 4.0,
    ) -> int:
        """Repeatedly call ``frame_fn(t)`` (t = seconds since start) and show the result.

        Bluetooth is slow: a full 165-LED frame takes roughly 0.1-0.5 s to send,
        so expect a few frames per second at best. Returns the number of frames sent.
        """
        start = time.monotonic()
        frames = 0
        while (t := time.monotonic() - start) < duration:
            leds = frame_fn(t)
            if asyncio.iscoroutine(leds):
                leds = await leds
            await self.show(leds)
            frames += 1
            await asyncio.sleep(max(0.0, (frames / fps) - (time.monotonic() - start)))
        return frames

    # ----- debugging --------------------------------------------------------

    async def describe(self) -> str:
        """List the board's BLE services and characteristics (for curious students)."""
        client = await self._ensure_connected()
        lines = []
        for service in client.services:
            lines.append(f"Service {service.uuid}  ({service.description})")
            for char in service.characteristics:
                lines.append(
                    f"    Characteristic {char.uuid}  [{', '.join(char.properties)}]  ({char.description})"
                )
        return "\n".join(lines)
