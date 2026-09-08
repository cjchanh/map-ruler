"""Offline plot smoke (matplotlib + synthetic receipt)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    import matplotlib  # noqa: F401
except ImportError:
    matplotlib = None


@unittest.skipUnless(matplotlib is not None, "matplotlib extra not installed")
class TestPlotOffline(unittest.TestCase):
    def test_plot_receipt_png(self) -> None:
        from map_ruler.plot import plot_from_receipt

        receipt = {
            "status": "CLEAN",
            "geocode": {"lat": 43.6626213, "lon": -79.3910161, "display_name": "t"},
            "query": {"address": "test", "feature": "roof"},
            "candidates": [
                {
                    "id": "way/1",
                    "footprint_sqft": 1656,
                    "offset_E_m": -10,
                    "offset_N_m": -6,
                    "bbox_ft": {"width": 60, "height": 50},
                }
            ],
            "primary": {
                "id": "way/1",
                "footprint_sqft": 1656,
                "offset_E_m": -10,
                "offset_N_m": -6,
            },
        }
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "t.png"
            path = plot_from_receipt(receipt, out_path=out)
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
