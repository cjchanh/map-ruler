"""Load operator/agent vertex paths (GeoJSON or simple JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class VerticesError(ValueError):
    pass


def load_vertices(path: str | Path) -> list[tuple[float, float]]:
    """Load coordinates as [(lat, lon), ...].

    Accepted shapes:
    - GeoJSON FeatureCollection / Feature / Geometry (LineString or Polygon)
    - {"type":"LineString","coordinates":[[lon,lat],...]}  (GeoJSON order)
    - {"coordinates":[[lat,lon],...], "order":"latlon"}   (explicit)
    - [[lat, lon], ...]                                    (latlon list)
    - [[lon, lat], ...] with top-level "order":"lonlat"
    """
    p = Path(path)
    if not p.is_file():
        raise VerticesError(f"vertices file not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise VerticesError(f"invalid JSON: {e}") from e
    return parse_vertices(raw)


def parse_vertices(raw: Any) -> list[tuple[float, float]]:
    if isinstance(raw, list):
        return _pairs(raw, order="latlon")

    if not isinstance(raw, dict):
        raise VerticesError("vertices must be a list or JSON object")

    order = (raw.get("order") or "").lower() or None

    # GeoJSON-ish
    if raw.get("type") == "FeatureCollection":
        feats = raw.get("features") or []
        if not feats:
            raise VerticesError("empty FeatureCollection")
        return parse_vertices(feats[0])

    if raw.get("type") == "Feature":
        geom = raw.get("geometry")
        if not geom:
            raise VerticesError("Feature missing geometry")
        return parse_vertices(geom)

    gtype = raw.get("type")
    if gtype == "LineString":
        return _pairs(raw.get("coordinates") or [], order=order or "lonlat")
    if gtype == "Polygon":
        rings = raw.get("coordinates") or []
        if not rings:
            raise VerticesError("empty Polygon")
        # exterior ring only; GeoJSON closes ring — keep as-is for area
        return _pairs(rings[0], order=order or "lonlat")

    if "coordinates" in raw:
        return _pairs(raw["coordinates"], order=order or "latlon")

    raise VerticesError(
        "unrecognized vertices shape — use LineString/Polygon GeoJSON "
        "or [[lat,lon],...] list"
    )


def _pairs(
    seq: list[Any],
    *,
    order: str,
) -> list[tuple[float, float]]:
    if len(seq) < 2:
        raise VerticesError("need at least 2 coordinates")
    out: list[tuple[float, float]] = []
    for i, item in enumerate(seq):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            raise VerticesError(f"bad coordinate at index {i}: {item!r}")
        a, b = float(item[0]), float(item[1])
        if order == "lonlat":
            lon, lat = a, b
        else:
            lat, lon = a, b
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise VerticesError(
                f"out-of-range lat/lon at index {i}: ({lat}, {lon}) — "
                "check order=latlon vs lonlat"
            )
        out.append((lat, lon))
    return out
