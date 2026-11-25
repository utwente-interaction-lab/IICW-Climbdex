"""Map holds on the wall to LED positions, using the Climbdex SQLite database.

The board only understands *LED positions* (0, 1, 2, ...). The database knows how
those positions relate to physical holes (x/y in inches) and to climbs. Download the
database first with ``bin/sync_db.sh kilter`` (or ``bin/win/sync_db.sh kilter``).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .protocol import Color

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "kilter" / "db.sqlite3"


@dataclass(frozen=True)
class Hold:
    placement_id: int
    """Id used in climb ``frames`` strings (``p<placement_id>r<role_id>``)."""
    position: int
    """LED position: the number you send to the board."""
    x: int
    """Horizontal position on the wall, in inches."""
    y: int
    """Vertical position on the wall, in inches (bigger is higher)."""


@dataclass(frozen=True)
class Climb:
    uuid: str
    name: str
    frames: str
    angle_hint: Optional[int] = None


class Wall:
    """One board configuration (layout + size) loaded from the database.

    Example (Kilter Homewall, 7x10 Mainline LED kit)::

        wall = Wall(layout_id=8, size_id=18)
        wall.holds[:3]
        wall.frames_to_leds("p4119r45p4139r45")
    """

    def __init__(self, layout_id: int, size_id: int, db_path: Path | str = DEFAULT_DB_PATH):
        self.layout_id = int(layout_id)
        self.size_id = int(size_id)
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Database not found at {self.db_path}. Run bin/sync_db.sh kilter first."
            )
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT placements.id, leds.position, holes.x, holes.y
                FROM placements
                JOIN holes ON placements.hole_id = holes.id
                JOIN leds ON leds.hole_id = holes.id
                WHERE placements.layout_id = ? AND leds.product_size_id = ?
                ORDER BY leds.position
                """,
                (self.layout_id, self.size_id),
            ).fetchall()
            role_rows = conn.execute(
                """
                SELECT placement_roles.id, placement_roles.name, placement_roles.led_color
                FROM placement_roles
                JOIN layouts ON layouts.product_id = placement_roles.product_id
                WHERE layouts.id = ?
                """,
                (self.layout_id,),
            ).fetchall()
        if not rows:
            raise ValueError(
                f"No LEDs found for layout {layout_id} / size {size_id}. "
                "Check the ids with list_configurations()."
            )
        self.holds: list[Hold] = [Hold(*row) for row in rows]
        self._by_placement = {h.placement_id: h for h in self.holds}
        self.role_colors: dict[int, str] = {role_id: color for role_id, _, color in role_rows}
        self.role_names: dict[int, str] = {role_id: name for role_id, name, _ in role_rows}

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    @property
    def positions(self) -> list[int]:
        """All LED positions on this wall (sorted, no duplicates)."""
        return sorted({h.position for h in self.holds})

    def unique_holds(self) -> list[Hold]:
        """One hold per LED position (a hole can have several placements)."""
        seen: dict[int, Hold] = {}
        for hold in self.holds:
            seen.setdefault(hold.position, hold)
        return [seen[p] for p in sorted(seen)]

    def bounds(self) -> tuple[int, int, int, int]:
        """``(min_x, max_x, min_y, max_y)`` of all holds, in inches."""
        xs = [h.x for h in self.holds]
        ys = [h.y for h in self.holds]
        return min(xs), max(xs), min(ys), max(ys)

    def nearest(self, x: float, y: float) -> Hold:
        """The hold closest to point ``(x, y)``."""
        return min(self.unique_holds(), key=lambda h: (h.x - x) ** 2 + (h.y - y) ** 2)

    def frames_to_leds(self, frames: str) -> dict[int, str]:
        """Turn a climb ``frames`` string (``p1145r12p1146r13...``) into ``{position: colour}``."""
        leds: dict[int, str] = {}
        for placement, role in re.findall(r"p(\d+)r(\d+)", frames):
            hold = self._by_placement.get(int(placement))
            if hold is None:
                continue  # hold not present on this size of wall
            leds[hold.position] = self.role_colors.get(int(role), "FFFFFF")
        return leds

    def find_climbs(self, name: str = "", limit: int = 20) -> list[Climb]:
        """Search listed climbs on this layout by (part of) their name."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT uuid, name, frames, angle
                FROM climbs
                WHERE layout_id = ? AND is_listed = 1 AND is_draft = 0
                AND frames_count = 1 AND name LIKE ?
                ORDER BY name
                LIMIT ?
                """,
                (self.layout_id, f"%{name}%", limit),
            ).fetchall()
        return [Climb(*row) for row in rows]

    def climb_leds(self, climb: Climb | str) -> dict[int, str]:
        """LEDs for a climb (a :class:`Climb`, or an exact climb name)."""
        if isinstance(climb, str):
            matches = [c for c in self.find_climbs(climb, limit=50) if c.name == climb]
            if not matches:
                raise LookupError(f"No climb named {climb!r} on layout {self.layout_id}")
            climb = matches[0]
        return self.frames_to_leds(climb.frames)


def list_configurations(db_path: Path | str = DEFAULT_DB_PATH) -> list[tuple]:
    """List ``(layout_id, layout_name, size_id, size_name, size_description, led_count)``."""
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            """
            SELECT DISTINCT layouts.id, layouts.name, product_sizes.id, product_sizes.name,
                   product_sizes.description,
                   (SELECT COUNT(*) FROM leds WHERE leds.product_size_id = product_sizes.id)
            FROM layouts
            JOIN product_sizes ON product_sizes.product_id = layouts.product_id
            WHERE layouts.is_listed = 1
            ORDER BY layouts.id, product_sizes.id
            """
        ).fetchall()


def fill(positions, color: Color) -> dict[int, Color]:
    """Convenience: ``{position: color}`` for every position given."""
    return {p: color for p in positions}
