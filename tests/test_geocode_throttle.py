"""Offline throttle tests for the Nominatim rate limit (no network).

Monkeypatches ``time.monotonic`` / ``time.sleep`` in the geocode module and
replaces ``urlopen`` so the throttle logic is exercised deterministically.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

import map_ruler.geocode as geocode


class _FakeResponse:
    def __init__(self, payload: list) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


class TestNominatimThrottle(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_last = geocode._last_request_monotonic
        geocode._last_request_monotonic = None
        self.payload = [
            {"lat": "43.6626", "lon": "-79.3910", "display_name": "t"}
        ]
        self.sleeps: list[float] = []

    def tearDown(self) -> None:
        geocode._last_request_monotonic = self._prev_last

    def _geocode_twice(self, monotonic_values: list[float]) -> None:
        with mock.patch.object(
            geocode.urllib.request,
            "urlopen",
            return_value=_FakeResponse(self.payload),
        ), mock.patch.object(
            geocode.time, "monotonic", side_effect=monotonic_values
        ), mock.patch.object(
            geocode.time, "sleep", side_effect=self.sleeps.append
        ):
            geocode.geocode_address("1 Test St")
            geocode.geocode_address("1 Test St")

    def test_second_call_within_interval_sleeps_remainder(self) -> None:
        # First call at t=100.0 records; second at t=100.2 sleeps 0.8 s.
        self._geocode_twice([100.0, 100.2])
        self.assertEqual(len(self.sleeps), 1)
        self.assertAlmostEqual(self.sleeps[0], 0.8, places=6)

    def test_call_after_interval_does_not_sleep(self) -> None:
        self._geocode_twice([100.0, 105.0])
        self.assertEqual(self.sleeps, [])


if __name__ == "__main__":
    unittest.main()
