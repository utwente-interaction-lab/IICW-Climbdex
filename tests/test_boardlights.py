"""Tests for boardlights that need no Bluetooth hardware.

Run with:  python -m unittest discover tests
"""

import json
import random
import shutil
import subprocess
import unittest
from pathlib import Path

from boardlights import protocol
from boardlights.wall import DEFAULT_DB_PATH, Wall

ROOT = Path(__file__).resolve().parent.parent
BLUETOOTH_JS = ROOT / "climbdex" / "static" / "js" / "bluetooth.js"


class ProtocolTest(unittest.TestCase):
    def test_single_led_matches_captured_packet(self):
        # Captured from a real send to the IICW board: LED 5, purple.
        self.assertEqual(list(protocol.build_frame({5: "800080"})), [1, 4, 36, 2, 84, 5, 0, 130, 3])

    def test_color_formats(self):
        self.assertEqual(protocol.encode_color("#ff0000"), protocol.encode_color((255, 0, 0)))
        self.assertEqual(protocol.encode_color("FFFFFF"), 0xFF)
        self.assertEqual(protocol.encode_color("000000"), 0)
        with self.assertRaises(ValueError):
            protocol.encode_color("red")

    def test_empty_frame(self):
        self.assertEqual(list(protocol.build_frame({})), [1, 1, protocol.checksum([84]), 2, 84, 3])

    def test_large_frame_is_split_into_messages(self):
        data = protocol.build_frame({i: "FF0000" for i in range(200)})
        # 84 LEDs fit per message -> 3 messages: FIRST, MIDDLE, LAST
        types = []
        i = 0
        while i < len(data):
            self.assertEqual(data[i], 1)
            length = data[i + 1]
            types.append(data[i + 4])
            self.assertEqual(data[i + 4 + length], 3)
            i += length + 5
        self.assertEqual(types, [protocol.PACKET_FIRST, protocol.PACKET_MIDDLE, protocol.PACKET_LAST])
        self.assertTrue(all(len(c) <= 20 for c in protocol.split_chunks(data)))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MatchesJavaScriptTest(unittest.TestCase):
    """The Python encoder must produce the same bytes as the web app's bluetooth.js."""

    def test_random_frames(self):
        rng = random.Random(42)
        for n in (1, 10, 84, 85, 165, 400):
            positions = rng.sample(range(600), n)
            leds = {p: f"{rng.randrange(1 << 24):06X}" for p in positions}
            # bluetooth.js works on a frames string + lookup tables; build trivial ones.
            frames = "".join(f"p{p}r{p}" for p in leds)
            placement_positions = {str(p): p for p in leds}
            colors = {str(p): c for p, c in leds.items()}
            script = (
                BLUETOOTH_JS.read_text(encoding="utf-8")
                + f"\nprocess.stdout.write(JSON.stringify(Array.from(getBluetoothPacket("
                f"{json.dumps(frames)}, {json.dumps(placement_positions)}, {json.dumps(colors)}))));"
            )
            js = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(js.stdout), list(protocol.build_frame(leds)), f"n={n}")


@unittest.skipUnless(DEFAULT_DB_PATH.exists(), "kilter database not downloaded")
class WallTest(unittest.TestCase):
    def setUp(self):
        self.wall = Wall(layout_id=8, size_id=18)

    def test_homewall_7x10_mainline_has_165_leds(self):
        self.assertEqual(len(self.wall.positions), 165)

    def test_frames_to_leds(self):
        leds = self.wall.frames_to_leds("p4117r42p4118r45p999999r42")
        self.assertEqual(leds, {0: "00FF00", 1: "FFA500"})  # unknown placement ignored

    def test_find_climbs(self):
        climbs = self.wall.find_climbs(limit=3)
        self.assertTrue(climbs)
        self.assertTrue(self.wall.climb_leds(climbs[0]))


if __name__ == "__main__":
    unittest.main()
