"""Vertex load + polyline measure tests (offline)."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from map_ruler.geometry import m_to_ft, path_length_m, ring_area_m2
from map_ruler.measure import measure
from map_ruler.vertices import VerticesError, load_vertices, parse_vertices


class TestVerticesParse(unittest.TestCase):
    def test_latlon_list(self) -> None:
        pts = parse_vertices([[38.1, -104.1], [38.1, -104.0], [38.2, -104.0]])
        self.assertEqual(len(pts), 3)
        self.assertAlmostEqual(pts[0][0], 38.1)

    def test_geojson_linestring_lonlat(self) -> None:
        raw = {
            "type": "LineString",
            "coordinates": [[-104.1, 38.1], [-104.0, 38.1], [-104.0, 38.2]],
        }
        pts = parse_vertices(raw)
        self.assertAlmostEqual(pts[0][0], 38.1)
        self.assertAlmostEqual(pts[0][1], -104.1)

    def test_too_few(self) -> None:
        with self.assertRaises(VerticesError):
            parse_vertices([[38.0, -104.0]])


class TestPathLength(unittest.TestCase):
    def test_100m_east(self) -> None:
        lat0, lon0 = 43.6626213, -79.3910161
        dlon = 100.0 / (111320.0 * math.cos(math.radians(lat0)))
        coords = [(lat0, lon0), (lat0, lon0 + dlon)]
        m = path_length_m(coords, origin_lat=lat0, origin_lon=lon0)
        self.assertAlmostEqual(m, 100.0, delta=0.5)
        self.assertAlmostEqual(m_to_ft(m), 328.08, delta=2.0)


class TestMeasureVerticesOffline(unittest.TestCase):
    def test_fence_with_vertices_no_network_for_length(self) -> None:
        # Use operator coords so no Nominatim; --no building context
        lat0, lon0 = 43.6626213, -79.3910161
        dlat = 20.0 / 111320.0
        dlon = 30.0 / (111320.0 * math.cos(math.radians(lat0)))
        # open L-shape fence
        verts = [
            [lat0, lon0],
            [lat0, lon0 + dlon],
            [lat0 + dlat, lon0 + dlon],
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fence.json"
            path.write_text(json.dumps(verts), encoding="utf-8")
            rec = measure(
                lat=lat0,
                lon=lon0,
                feature="fence",
                vertices_path=path,
                include_building_context=False,
                calibrators=["basemap"],
            )
        self.assertEqual(rec["status"], "CLEAN")
        primary = rec["primary"]
        self.assertIsNotNone(primary)
        assert primary is not None
        # 30m + 20m = 50m ≈ 164 ft
        self.assertAlmostEqual(primary["length_m"], 50.0, delta=1.0)
        self.assertAlmostEqual(primary["length_ft"], m_to_ft(50.0), delta=3.0)
        self.assertIn("receipt_sha256", rec)

    def test_closed_courtyard_area(self) -> None:
        lat0, lon0 = 38.85, -104.87
        dlat = 10.0 / 111320.0
        dlon = 10.0 / (111320.0 * math.cos(math.radians(lat0)))
        ring = [
            [lat0, lon0],
            [lat0, lon0 + dlon],
            [lat0 + dlat, lon0 + dlon],
            [lat0 + dlat, lon0],
            [lat0, lon0],  # closed
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "yard.json"
            path.write_text(json.dumps({"type": "Polygon", "coordinates": [
                [[p[1], p[0]] for p in ring]  # lonlat for GeoJSON
            ]}), encoding="utf-8")
            # fix: GeoJSON polygon needs lon,lat - I built from lat,lon ring
            geo_ring = [[lon0, lat0], [lon0 + dlon, lat0], [lon0 + dlon, lat0 + dlat], [lon0, lat0 + dlat], [lon0, lat0]]
            path.write_text(
                json.dumps({"type": "Polygon", "coordinates": [geo_ring]}),
                encoding="utf-8",
            )
            rec = measure(
                lat=lat0,
                lon=lon0,
                feature="fence",
                vertices_path=path,
                include_building_context=False,
            )
        self.assertEqual(rec["status"], "CLEAN")
        primary = rec["primary"]
        assert primary is not None
        # ~100 m²
        self.assertIsNotNone(primary.get("footprint_m2"))
        self.assertAlmostEqual(primary["footprint_m2"], 100.0, delta=5.0)


if __name__ == "__main__":
    unittest.main()
