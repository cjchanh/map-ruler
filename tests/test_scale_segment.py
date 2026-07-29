"""Ground segment scale + rings in receipt (offline)."""

from __future__ import annotations

import math
import unittest

from map_ruler.geometry import m_to_ft, path_length_m
from map_ruler.measure import measure
from map_ruler.scale import (
    apply_linear_scale,
    ground_segment_calibrator,
    parse_segment,
)


class TestScaleSegment(unittest.TestCase):
    def test_parse(self) -> None:
        p1, p2 = parse_segment("43.66,-79.39,43.66,-79.389")
        self.assertAlmostEqual(p1[0], 43.66)
        self.assertAlmostEqual(p2[1], -79.389)

    def test_parse_bad(self) -> None:
        with self.assertRaises(ValueError):
            parse_segment("1,2,3")

    def test_ground_factor_identity_ish(self) -> None:
        lat0, lon0 = 43.6626213, -79.3910161
        # 15.5 ft east
        true_ft = 15.5
        true_m = true_ft * 0.3048
        dlon = true_m / (111320.0 * math.cos(math.radians(lat0)))
        p1 = (lat0, lon0)
        p2 = (lat0, lon0 + dlon)
        cal, factor = ground_segment_calibrator(
            p1, p2, true_length_ft=true_ft, pin_lat=lat0, pin_lon=lon0
        )
        self.assertAlmostEqual(factor, 1.0, delta=0.02)
        self.assertEqual(cal.kind, "ground_segment")

    def test_apply_scale(self) -> None:
        lm, am = apply_linear_scale(length_m=10.0, area_m2=100.0, factor=1.1)
        self.assertAlmostEqual(lm or 0, 11.0)
        self.assertAlmostEqual(am or 0, 121.0)

    def test_measure_with_segment_offline(self) -> None:
        lat0, lon0 = 43.6626213, -79.3910161
        true_ft = 15.5
        true_m = true_ft * 0.3048
        dlon = true_m / (111320.0 * math.cos(math.radians(lat0)))
        seg = f"{lat0},{lon0},{lat0},{lon0 + dlon}"
        # fence vertices 50m L-shape, no network
        dlat = 20.0 / 111320.0
        dlon2 = 30.0 / (111320.0 * math.cos(math.radians(lat0)))
        import json
        import tempfile
        from pathlib import Path

        verts = [
            [lat0, lon0],
            [lat0, lon0 + dlon2],
            [lat0 + dlat, lon0 + dlon2],
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "f.json"
            path.write_text(json.dumps(verts), encoding="utf-8")
            rec = measure(
                lat=lat0,
                lon=lon0,
                feature="fence",
                vertices_path=path,
                include_building_context=False,
                scale_segment=seg,
                scale_length_ft=15.5,
                include_rings=True,
            )
        self.assertEqual(rec["status"], "CLEAN")
        primary = rec["primary"]
        assert primary is not None
        self.assertIn("coords_latlon", primary)
        self.assertEqual(len(primary["coords_latlon"]), 3)
        kinds = [c["kind"] for c in rec["scale_chain"]]
        self.assertIn("ground_segment", kinds)
        # ~50m with factor ~1
        self.assertAlmostEqual(primary["length_m"], 50.0, delta=1.5)


if __name__ == "__main__":
    unittest.main()
