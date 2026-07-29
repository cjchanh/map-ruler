"""Unit tests for geometry + scale (offline)."""

from __future__ import annotations

import math
import unittest

from map_ruler.geometry import (
    bbox_ft,
    gla_band_from_footprint,
    m2_to_sqft,
    polygon_sha256,
    ring_area_m2,
)
from map_ruler.scale import build_scale_chain, combined_uncertainty_pct


class TestGeometry(unittest.TestCase):
    def test_100m_square_near_colorado_springs(self) -> None:
        # ~100m square at ~43.66°N
        lat0, lon0 = 43.6626213, -79.3910161
        # 100m north ≈ 100/111320 deg
        dlat = 100.0 / 111320.0
        dlon = 100.0 / (111320.0 * math.cos(math.radians(lat0)))
        ring = [
            (lat0, lon0),
            (lat0, lon0 + dlon),
            (lat0 + dlat, lon0 + dlon),
            (lat0 + dlat, lon0),
        ]
        m2 = ring_area_m2(ring, origin_lat=lat0, origin_lon=lon0)
        self.assertAlmostEqual(m2, 10000.0, delta=50.0)  # ~1% tolerance
        sqft = m2_to_sqft(m2)
        self.assertAlmostEqual(sqft, 107639.0, delta=600.0)

    def test_polygon_hash_stable(self) -> None:
        a = [(38.1, -104.1), (38.1, -104.0), (38.2, -104.0)]
        b = [(38.1, -104.1), (38.1, -104.0), (38.2, -104.0)]
        self.assertEqual(polygon_sha256(a), polygon_sha256(b))

    def test_gla_band(self) -> None:
        band = gla_band_from_footprint(1656.0)
        self.assertEqual(band["low"], round(1656 * 0.85, 1))
        self.assertEqual(band["high"], round(1656 * 0.95, 1))

    def test_bbox(self) -> None:
        lat0, lon0 = 38.0, -104.0
        dlat = 10.0 / 111320.0
        dlon = 20.0 / (111320.0 * math.cos(math.radians(lat0)))
        ring = [(lat0, lon0), (lat0, lon0 + dlon), (lat0 + dlat, lon0 + dlon), (lat0 + dlat, lon0)]
        w, h = bbox_ft(ring, origin_lat=lat0, origin_lon=lon0)
        self.assertAlmostEqual(w, 20 * 3.28084, delta=0.5)
        self.assertAlmostEqual(h, 10 * 3.28084, delta=0.5)


class TestScale(unittest.TestCase):
    def test_basemap_always_present(self) -> None:
        chain = build_scale_chain(["car_sedan"], lat=38.85)
        kinds = [c.kind for c in chain]
        self.assertEqual(kinds[0], "basemap")
        self.assertIn("car_sedan", kinds)

    def test_combined_uncertainty_is_max(self) -> None:
        chain = build_scale_chain(["basemap", "car_sedan"], lat=38.85)
        self.assertEqual(
            combined_uncertainty_pct(chain),
            max(c.uncertainty_pct for c in chain),
        )

    def test_unknown_calibrator(self) -> None:
        with self.assertRaises(ValueError):
            build_scale_chain(["basemap", "unicorn"], lat=38.0)


if __name__ == "__main__":
    unittest.main()
