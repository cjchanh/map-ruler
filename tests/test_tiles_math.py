"""Offline tile math tests (no network)."""

from __future__ import annotations

import unittest

from map_ruler.tiles import choose_zoom, deg2num, num2deg


class TestTileMath(unittest.TestCase):
    def test_roundtrip_tile(self) -> None:
        lat, lon = 43.6626213, -79.3910161
        z = 18
        x, y = deg2num(lat, lon, z)
        lat2, lon2 = num2deg(x, y, z)
        # NW corner of containing tile — within one tile of point
        self.assertLess(abs(lat - lat2), 0.01)
        self.assertLess(abs(lon - lon2), 0.01)

    def test_zoom_reasonable(self) -> None:
        z = choose_zoom(lat=43.66, radius_m=60)
        self.assertGreaterEqual(z, 15)
        self.assertLessEqual(z, 20)


if __name__ == "__main__":
    unittest.main()
