# Controlling the board's lights

> **Experimental.** Everything here uses a reverse-engineered Bluetooth protocol.
> It has been used on the IICW Kilter board, but it's not an official API, and a firmware
> update could break it. Treat it as a playground, not production software.

You can light the LEDs on an Aurora-style board (Kilter, Tension, ...) in three ways:

| Way | Good for | Where |
|-----|----------|-------|
| **Python library** (`boardlights`) | programming your own ideas: games, animations, generated climbs | [`boardlights/`](../boardlights) |
| **Jupyter notebooks** | learning step by step | [`examples/`](../examples) |
| **Web UI: "Draw on Wall"** | tapping holds on a picture and seeing them light up | Climbdex start page → *Draw on Wall* |

## Before you start

* **One connection at a time.** The board accepts only one Bluetooth connection. Close the
  Kilter/Tension app (on every phone nearby) or disconnect other laptops first.
* **Bluetooth range** is a few metres. Stand near the wall.
* **The database** maps holds to LEDs. Download it once:
  `bin/sync_db.sh kilter` (Windows: `bin/win/sync_db.sh kilter`).
* **Which wall?** The examples default to the *Kilter Homewall* layout (`layout 8`) with the
  *7x10 Mainline LED kit* (`size 18`, 165 LEDs). If your board is different, run
  `python -m boardlights configs` and pick the matching ids.

## Python library

### Install

```
python -m pip install -r requirements.txt -r requirements-lights.txt
```

`requirements-lights.txt` adds [`bleak`](https://github.com/hbldh/bleak) (cross-platform
Bluetooth) and Jupyter. The web server itself doesn't need them.

### Command line

Run from the repository root:

```
python -m boardlights scan                     # find boards nearby
python -m boardlights scan --all               # every Bluetooth device, if your board isn't listed
python -m boardlights light 0 FF0000 1 00FF00  # LED 0 red, LED 1 green
python -m boardlights climb "Swiss Chard"      # light a climb from the database
python -m boardlights rainbow --seconds 20     # demo animation
python -m boardlights clear                    # all off
python -m boardlights describe                 # list the board's Bluetooth services
```

Add `--address XX:XX:XX:XX:XX:XX` to pick a specific board, or `--name IICW` to pick
the first board whose name contains that text.

### In your own code

All Bluetooth calls are `async`. In Jupyter you can `await` directly; in a script use
`asyncio.run(...)`.

```python
import asyncio
from boardlights import Board, Wall

async def main():
    wall = Wall(layout_id=8, size_id=18)

    async with await Board.connect() as board:        # closest board; disconnects at the end
        await board.show({0: "FF0000", 1: (0, 255, 0)})   # {led_position: colour}
        await asyncio.sleep(2)

        top_row = max(h.y for h in wall.holds)
        await board.show({h.position: "00FFFF" for h in wall.holds if h.y == top_row})
        await asyncio.sleep(2)

        await board.show(wall.climb_leds("Swiss Chard"))

asyncio.run(main())
```

The main pieces:

| | |
|---|---|
| `await scan()` | list nearby boards |
| `await Board.connect(address=None, name_contains=None)` | connect (closest board by default) |
| `await board.show({position: colour})` | light exactly these LEDs; **all others turn off** |
| `await board.clear()` | all LEDs off |
| `await board.animate(frame_fn, duration, fps)` | call `frame_fn(t)` repeatedly and show the result |
| `await board.disconnect()` | let others connect again |
| `Wall(layout_id, size_id)` | holds of one board configuration, from the database |
| `wall.holds` / `wall.unique_holds()` | `Hold(placement_id, position, x, y)`; x/y in inches |
| `wall.nearest(x, y)` | hold closest to a point |
| `wall.find_climbs("name")`, `wall.climb_leds(climb)` | search climbs and turn them into LEDs |

Colours can be `"FF0000"`, `"#ff0000"` or `(255, 0, 0)`.

### Notebooks

Start Jupyter from the repo root (`jupyter lab`) and open:

1. [`examples/01_getting_started.ipynb`](../examples/01_getting_started.ipynb): scan, connect, light LEDs, colours
2. [`examples/02_climbs_and_holds.ipynb`](../examples/02_climbs_and_holds.ipynb): hold coordinates, a text map of the wall, real climbs, setting your own problem
3. [`examples/03_animations.ipynb`](../examples/03_animations.ipynb): rainbow, sweeps, sparkle, a reaction-time game, and ideas for more

## Web UI: "Draw on Wall" (experimental)

On the Climbdex start page, pick your board, layout and size, then click **Draw on Wall**.
Tap holds to cycle their colour (start → hand → finish → foot → off), then:

* **Send to wall** connects (first time: the browser shows a device picker) and lights your drawing.
* **Live** sends after every tap, so you can draw directly on the wall.
* **Turn wall off**, **Reset drawing** and **Disconnect** do what they say.

Limits:

* Needs **Web Bluetooth**: Chrome or Edge on desktop or Android. Firefox and all iOS
  browsers don't support it.
* Web Bluetooth only works on `https://` or `http://localhost`. If you open the server via
  your laptop's IP address from a phone, it won't work without HTTPS.
* Fast tapping in Live mode is batched: the wall shows your latest drawing once the
  previous send has finished.

## Things to know (and limits)

* **Speed.** BLE sends 20 bytes at a time, and one LED takes 3 bytes. A frame with all
  165 LEDs (~500 bytes) takes a noticeable fraction of a second, so animations get a few
  frames per second. Lighting fewer LEDs is faster.
* **Colours are coarse.** Each LED colour is stored in one byte (3 bits red, 3 green,
  2 blue): 256 colours in total. Dim colours like `200000` may look the same as off.
* **Protocol version.** Only the newer "API level 3" format is implemented (board names
  ending in `@3`, like `Kilter Board#751814@3`). Older boards use a different format and
  won't work.
* **Don't rename the board.** The official app may use the board's Bluetooth name
  (including the `@3` suffix) to decide how to talk to it.
* **Troubleshooting.** If you can't connect: close the official app, move closer, toggle
  your computer's Bluetooth, or power-cycle the board. If `scan` finds nothing, try
  `scan --all`.

## How it works

The protocol was reverse-engineered by Philipp Bazun
([write-up](https://web.archive.org/web/20240203155713/https://www.bazun.me/blog/kiterboard/)).
[`boardlights/protocol.py`](../boardlights/protocol.py) is a short, commented
implementation. It produces exactly the same bytes as the web app's
[`bluetooth.js`](../climbdex/static/js/bluetooth.js), and the tests check that.

Run the tests (no board needed) with:

```
python -m unittest discover tests
```
