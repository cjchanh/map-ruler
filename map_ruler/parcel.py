"""Optional parcel pull via ArcGIS FeatureServer / MapServer query.

Generic: any layer that supports query geometry=point.
Presets are best-effort public endpoints (may move); always overridable with --parcel-url.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from map_ruler.geocode import USER_AGENT
from map_ruler.geometry import (
    m2_to_sqft,
    polygon_sha256,
    ring_area_m2,
    to_xy,
)

# Best-effort public layers. Not guaranteed forever — verify at runtime.
PRESET_LAYERS: dict[str, dict[str, str]] = {
    # City of Toronto — Property Boundary (cot_geospatial27 / MapServer layer 36)
    "toronto": {
        "url": (
            "https://gis.toronto.ca/arcgis/rest/services/"
            "cot_geospatial27/MapServer/36/query"
        ),
        "note": "City of Toronto Property Boundary (public open GIS)",
    },
    "ontario_demo": {
        "url": (
            "https://gis.toronto.ca/arcgis/rest/services/"
            "cot_geospatial27/MapServer/36/query"
        ),
        "note": "Public Ontario/Toronto demo preset — same as toronto",
    },
}


class ParcelError(RuntimeError):
    pass


def query_parcel_at_point(
    lat: float,
    lon: float,
    *,
    layer_query_url: str,
    distance_m: float = 15.0,
    timeout: float = 30.0,
    out_fields: str = "*",
) -> dict[str, Any] | None:
    """Query ArcGIS layer for a parcel intersecting a small buffer around pin.

    layer_query_url should end with /query (FeatureServer/N/query or MapServer/N/query).
    Returns first feature as {attributes, coords_latlon, area_m2, ...} or None.
    """
    if not layer_query_url.rstrip("/").endswith("query"):
        layer_query_url = layer_query_url.rstrip("/") + "/query"

    # geometry as lon,lat (Esri)
    geom = json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}})
    params = {
        "f": "json",
        "geometry": geom,
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": str(distance_m),
        "units": "esriSRUnit_Meter",
        "outFields": out_fields,
        "returnGeometry": "true",
        "outSR": "4326",
    }
    url = layer_query_url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ParcelError(f"parcel HTTP {e.code} for {layer_query_url}") from e
    except Exception as e:  # noqa: BLE001
        raise ParcelError(f"parcel query failed: {e}") from e

    if payload.get("error"):
        raise ParcelError(f"parcel API error: {payload['error']}")

    features = payload.get("features") or []
    if not features:
        return None

    feat = features[0]
    attrs = feat.get("attributes") or {}
    geom_out = feat.get("geometry") or {}
    rings = geom_out.get("rings") or []
    if not rings:
        return {
            "attributes": attrs,
            "coords_latlon": None,
            "footprint_m2": None,
            "footprint_sqft": None,
            "source_url": layer_query_url,
        }

    # First ring: Esri is lon,lat
    ring = rings[0]
    coords = [(float(p[1]), float(p[0])) for p in ring]
    m2 = ring_area_m2(coords, origin_lat=lat, origin_lon=lon)
    return {
        "attributes": attrs,
        "coords_latlon": [[round(a, 7), round(b, 7)] for a, b in coords],
        "footprint_m2": round(m2, 2),
        "footprint_sqft": round(m2_to_sqft(m2), 1),
        "polygon_sha256": polygon_sha256(coords),
        "source_url": layer_query_url,
        "feature_count": len(features),
    }


def resolve_layer_url(preset_or_url: str) -> tuple[str, str]:
    """Return (query_url, note)."""
    key = preset_or_url.strip().lower()
    if key in PRESET_LAYERS:
        p = PRESET_LAYERS[key]
        return p["url"], p.get("note", "")
    if preset_or_url.startswith("http://") or preset_or_url.startswith("https://"):
        return preset_or_url, "operator-supplied URL"
    raise ParcelError(
        f"unknown parcel preset {preset_or_url!r}; "
        f"use one of {list(PRESET_LAYERS)} or a full .../query URL"
    )
