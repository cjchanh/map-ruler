"""Geocoding via OpenStreetMap Nominatim (read-only, polite UA)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "map-ruler/0.1 (CDS measure-testify; local operator tool)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"


class GeocodeError(RuntimeError):
    pass


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
    req = urllib.request.Request(
        f"{NOMINATIM}?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
