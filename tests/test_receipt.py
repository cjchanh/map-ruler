"""Receipt seal tests (offline)."""

from __future__ import annotations

import unittest

from map_ruler.receipt import base_receipt, seal


class TestReceipt(unittest.TestCase):
    def test_seal_stable(self) -> None:
        r = {
            "schema_version": "measure-testify/receipt/v1",
            "status": "CLEAN",
            "a": 1,
        }
        s1 = seal(r)
        s2 = seal({k: v for k, v in s1.items() if k != "receipt_sha256"})
        self.assertEqual(s1["receipt_sha256"], s2["receipt_sha256"])
        self.assertEqual(len(s1["receipt_sha256"]), 64)

    def test_base_receipt_fields(self) -> None:
        rec = base_receipt(
            status="CLEAN",
            query={"feature": "roof", "address": "x", "lat": None, "lon": None, "radius_m": 60, "calibrators": ["basemap"]},
            geocode={"lat": 38.85, "lon": -104.87, "display_name": "t", "source": "t"},
            scale_chain=[{"id": "basemap_local_en", "kind": "basemap", "meters_per_unit": 1.0, "uncertainty_pct": 2.0, "notes": "n"}],
            candidates=[],
            primary=None,
            method="test",
        )
        self.assertEqual(rec["schema_version"], "measure-testify/receipt/v1")
        self.assertIn("receipt_sha256", rec)
        self.assertIn("disclaimer", rec)
        self.assertIn("google_satellite", rec["maps"])


if __name__ == "__main__":
    unittest.main()
