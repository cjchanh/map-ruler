"""Fetch building footprints near a pin (OSM Overpass + OSM API fallback)."""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from map_ruler.geocode import USER_AGENT

# Ordered mirrors — rotate on failure / timeout.
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
)
OSM_API = "https://api.openstreetmap.org/api/0.6"


class FootprintError(RuntimeError):
    pass


def _http_json(url: str, *, data: bytes | None = None, timeout: float = 60.0) -> Any:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _bbox_from_radius(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """south, west, north, east for Overpass bbox."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def fetch_buildings_overpass(
    lat: float,
    lon: float,
    *,
    radius_m: float = 60.0,
    timeout: float = 55.0,
    max_attempts_per_mirror: int = 3,
) -> list[dict[str, Any]]:
    """Return list of {id, tags, coords:[(lat,lon),...]} for building ways.

    Hardened: multi-mirror, exponential backoff, bbox query (more cache-friendly
    than around()), longer HTTP timeout than server [timeout].
    """
    south, west, north, east = _bbox_from_radius(lat, lon, radius_m)
    # Prefer bbox; filter by distance client-side if needed (we already score by pin).
    server_timeout = max(15, int(timeout) - 5)
    query = f"""
    [out:json][timeout:{server_timeout}];
    (
      way["building"]({south},{west},{north},{east});
    );
    out body geom;
    """
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    errors: list[str] = []
    http_timeout = timeout + 20.0

    for mi, ep in enumerate(OVERPASS_ENDPOINTS):
        for attempt in range(max_attempts_per_mirror):
            try:
                payload = _http_json(ep, data=body, timeout=http_timeout)
                buildings = _parse_overpass_elements(payload)
                # Keep only those with centroid within radius_m * 1.15 (bbox is square)
                return _filter_by_radius(buildings, lat, lon, radius_m * 1.15)
            except Exception as e:  # noqa: BLE001
                msg = f"{ep} attempt {attempt + 1}: {type(e).__name__}: {e}"
                errors.append(msg)
                # Exponential backoff with mirror index jitter
                time.sleep(min(12.0, (1.5**attempt) + 0.25 * mi))

    # Last-resort: smaller radius + around() on first two mirrors only
    if radius_m > 30:
        try:
            return fetch_buildings_overpass(
                lat,
                lon,
                radius_m=min(40.0, radius_m * 0.7),
                timeout=timeout + 15,
                max_attempts_per_mirror=2,
            )
        except FootprintError as e:
            errors.append(f"reduced-radius fallback: {e}")

    raise FootprintError(
        "Overpass failed after multi-mirror retries. "
        + " | ".join(errors[-6:])
    )


def _filter_by_radius(
    buildings: list[dict[str, Any]],
    lat: float,
    lon: float,
    radius_m: float,
) -> list[dict[str, Any]]:
    from map_ruler.geometry import centroid, to_xy

    out: list[dict[str, Any]] = []
    for b in buildings:
        clat, clon = centroid(b["coords"])
        e, n = to_xy(clat, clon, origin_lat=lat, origin_lon=lon)
        if math.hypot(e, n) <= radius_m:
            out.append(b)
    return out


def _parse_overpass_elements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for el in payload.get("elements") or []:
        if el.get("type") != "way":
            continue
        geom = el.get("geometry") or []
        coords = [(float(g["lat"]), float(g["lon"])) for g in geom if "lat" in g]
        if len(coords) < 3:
            continue
        tags = el.get("tags") or {}
        out.append(
            {
                "id": f"way/{el['id']}",
                "osm_id": el["id"],
                "tags": tags,
                "coords": coords,
                "source": tags.get("source") or "openstreetmap",
            }
        )
    return out


def fetch_way_full(osm_id: int, *, timeout: float = 25.0) -> dict[str, Any]:
    """Fallback: OSM API full way + nodes."""
    url = f"{OSM_API}/way/{osm_id}/full.json"
    last: Exception | None = None
    for attempt in range(3):
        try:
            payload = _http_json(url, timeout=timeout)
            break
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.0 * (attempt + 1))
    else:
        raise FootprintError(f"OSM API failed for way/{osm_id}: {last}") from last

    nodes = {
        el["id"]: (float(el["lat"]), float(el["lon"]))
        for el in payload.get("elements") or []
        if el.get("type") == "node"
    }
    way = next(el for el in payload["elements"] if el.get("type") == "way")
    coords = [nodes[nid] for nid in way["nodes"] if nid in nodes]
    tags = way.get("tags") or {}
    return {
        "id": f"way/{osm_id}",
        "osm_id": osm_id,
        "tags": tags,
        "coords": coords,
        "source": tags.get("source") or "openstreetmap",
    }
