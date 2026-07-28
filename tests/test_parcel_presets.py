"""Offline parcel preset resolution tests."""

from __future__ import annotations

import unittest

from map_ruler.parcel import ParcelError, resolve_layer_url


class TestParcelPresets(unittest.TestCase):
    def test_toronto_preset(self) -> None:
        url, note = resolve_layer_url("toronto")
        self.assertIn("gis.toronto.ca", url)
        self.assertIn("query", url)
        self.assertTrue(note)

    def test_ontario_demo_alias(self) -> None:
        url, _ = resolve_layer_url("ontario_demo")
        self.assertIn("cot_geospatial27", url)

    def test_custom_url(self) -> None:
        u = "https://example.com/arcgis/rest/services/x/MapServer/0/query"
        url, note = resolve_layer_url(u)
        self.assertEqual(url, u)
        self.assertIn("operator", note)

    def test_unknown(self) -> None:
        with self.assertRaises(ParcelError):
            resolve_layer_url("not-a-preset")


if __name__ == "__main__":
    unittest.main()
