"""Geocoding via OpenStreetMap Nominatim (read-only, polite UA)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

CONTACT_URL = "https://github.com/cjchanh/map-ruler"
USER_AGENT = f"map-ruler/0.6.0 (+{CONTACT_URL})"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
NOMINATIM_MIN_INTERVAL_S = 1.0

_last_request_monotonic: float | None = None


class GeocodeError(RuntimeError):
    pass


def _respect_rate_limit() -> None:
    """Hold to at most one outbound request per second (Nominatim usage policy)."""
    global _last_request_monotonic
    now = time.monotonic()
    if _last_request_monotonic is not None:
        remaining = NOMINATIM_MIN_INTERVAL_S - (now - _last_request_monotonic)
        if remaining > 0:
            time.sleep(remaining)
            # Re-read the clock: sleep() may overshoot, and stamping the
            # planned wake time instead of the real one lets the next call
            # start less than one second after this request actually went out.
            now = time.monotonic()
    _last_request_monotonic = now


def open_url(
    url: str,
    *,
    data: bytes | None = None,
    timeout: float = 25.0,
) -> Any:
    """Open a URL with the project User-Agent, throttled to 1 request/second."""
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": USER_AGENT},
    )
    _respect_rate_limit()
    return urllib.request.urlopen(req, timeout=timeout)


def geocode_address(address: str, *, timeout: float = 25.0) -> dict[str, Any]:
    """Resolve an address to lat/lon + display_name."""
    if not address or not address.strip():
        raise GeocodeError("empty address")
    params = urllib.parse.urlencode(
        {
            "q": address.strip(),
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
        }
    )
    try:
        with open_url(f"{NOMINATIM}?{params}", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise GeocodeError(f"Nominatim HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise GeocodeError(f"Nominatim unreachable: {e.reason}") from e
    except TimeoutError as e:
        raise GeocodeError("Nominatim timeout") from e

    if not data:
        raise GeocodeError(f"no results for address: {address!r}")
    hit = data[0]
    return {
        "lat": float(hit["lat"]),
        "lon": float(hit["lon"]),
        "display_name": hit.get("display_name") or address,
        "source": "nominatim.openstreetmap.org",
        "osm_type": hit.get("osm_type"),
        "osm_id": hit.get("osm_id"),
    }
