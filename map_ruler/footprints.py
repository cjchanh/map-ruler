"""Fetch building footprints near a pin (OSM Overpass + OSM API fallback)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from map_ruler.geocode import USER_AGENT

OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
OSM_API = "https://api.openstreetmap.org/api/0.6"


class FootprintError(RuntimeError):
    pass


def _http_json(url: str, *, data: bytes | None = None, timeout: float = 45.0) -> Any:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_buildings_overpass(
    lat: float,
    lon: float,
    *,
    radius_m: float = 60.0,
    timeout: float = 40.0,
) -> list[dict[str, Any]]:
    """Return list of {id, tags, coords:[(lat,lon),...]} for building ways."""
    query = f"""
    [out:json][timeout:{int(timeout)}];
    (
      way["building"](around:{radius_m},{lat},{lon});
    );
    out body geom;
    """
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    last_err: Exception | None = None
    for ep in OVERPASS_ENDPOINTS:
        for attempt in range(2):
            try:
                payload = _http_json(ep, data=body, timeout=timeout + 10)
                return _parse_overpass_elements(payload)
            except Exception as e:  # noqa: BLE001 — retry across mirrors
                last_err = e
                time.sleep(1.0 * (attempt + 1))
    raise FootprintError(f"Overpass failed: {last_err}")


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


def fetch_way_full(osm_id: int, *, timeout: float = 20.0) -> dict[str, Any]:
    """Fallback: OSM API full way + nodes."""
    url = f"{OSM_API}/way/{osm_id}/full.json"
    try:
        payload = _http_json(url, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise FootprintError(f"OSM API HTTP {e.code} for way/{osm_id}") from e
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
