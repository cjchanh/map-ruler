"""Offline throttle tests for the Nominatim rate limit (no network).

Monkeypatches ``time.monotonic`` / ``time.sleep`` in the geocode module and
replaces ``urlopen`` so the throttle logic is exercised deterministically.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

import map_ruler.footprints as footprints
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
        # First call at t=100.0 records; second at t=100.2 sleeps 0.8 s and
        # then re-reads the clock (101.05: an overshoot) so the real send time,
        # not the planned wake time, becomes the new reference.
        self._geocode_twice([100.0, 100.2, 101.05])
        self.assertEqual(len(self.sleeps), 1)
        self.assertAlmostEqual(self.sleeps[0], 0.8, places=6)
        self.assertAlmostEqual(geocode._last_request_monotonic, 101.05, places=6)

    def test_call_after_interval_does_not_sleep(self) -> None:
        self._geocode_twice([100.0, 105.0])
        self.assertEqual(self.sleeps, [])

    def test_geocode_sends_identifying_user_agent(self) -> None:
        seen: list[object] = []

        def capture(req: object, timeout: float | None = None) -> _FakeResponse:
            seen.append(req)
            return _FakeResponse(self.payload)

        with mock.patch.object(
            geocode.urllib.request, "urlopen", side_effect=capture
        ), mock.patch.object(geocode.time, "monotonic", return_value=100.0), mock.patch.object(
            geocode.time, "sleep"
        ):
            geocode.geocode_address("1 Test St")
        self.assertEqual(len(seen), 1)
        ua = seen[0].get_header("User-agent")  # type: ignore[attr-defined]
        self.assertIsNotNone(ua)
        self.assertIn("map-ruler", ua)
        self.assertIn("https://github.com/cjchanh/map-ruler", ua)

    def test_overpass_client_sends_user_agent_and_throttles(self) -> None:
        seen: list[object] = []

        def capture(req: object, timeout: float | None = None) -> _FakeResponse:
            seen.append(req)
            return _FakeResponse({"elements": []})

        with mock.patch.object(
            geocode.urllib.request, "urlopen", side_effect=capture
        ), mock.patch.object(
            geocode.time, "monotonic", side_effect=[100.0, 100.2, 101.05]
        ), mock.patch.object(geocode.time, "sleep", side_effect=self.sleeps.append):
            footprints._http_json("https://overpass-api.de/api/interpreter")
            footprints._http_json("https://overpass-api.de/api/interpreter")
        self.assertEqual(len(seen), 2)
        ua = seen[0].get_header("User-agent")  # type: ignore[attr-defined]
        self.assertIsNotNone(ua)
        self.assertIn("map-ruler", ua)
        self.assertIn("https://github.com/cjchanh/map-ruler", ua)
        self.assertEqual(len(self.sleeps), 1)
        self.assertAlmostEqual(self.sleeps[0], 0.8, places=6)


if __name__ == "__main__":
    unittest.main()
