"""Local equirectangular geometry — no external GIS deps."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Iterable, Sequence

# Earth approximation used only for local meter conversion around a pin.
_M_PER_DEG_LAT = 111_320.0


def meters_per_deg(lat: float) -> tuple[float, float]:
    """Return (m_per_deg_lat, m_per_deg_lon) at latitude."""
    m_lat = _M_PER_DEG_LAT
    m_lon = _M_PER_DEG_LAT * math.cos(math.radians(lat))
    return m_lat, m_lon


def to_xy(
    lat: float,
    lon: float,
    *,
    origin_lat: float,
    origin_lon: float,
) -> tuple[float, float]:
    """Project (lat, lon) to local meters east/north of origin."""
    m_lat, m_lon = meters_per_deg(origin_lat)
    e = (lon - origin_lon) * m_lon
    n = (lat - origin_lat) * m_lat
    return e, n


def close_ring(
    coords: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    if not coords:
        return []
    out = list(coords)
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def ring_area_m2(
    coords: Sequence[tuple[float, float]],
    *,
    origin_lat: float,
    origin_lon: float,
) -> float:
    """Shoelace area in m² for a lat/lon ring."""
    ring = close_ring(coords)
    if len(ring) < 4:
        return 0.0
    xy = [to_xy(la, lo, origin_lat=origin_lat, origin_lon=origin_lon) for la, lo in ring]
    acc = 0.0
    for i in range(len(xy) - 1):
        x1, y1 = xy[i]
        x2, y2 = xy[i + 1]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0


def m2_to_sqft(m2: float) -> float:
    return m2 * 10.76391041671


def edge_lengths_ft(
    coords: Sequence[tuple[float, float]],
    *,
    origin_lat: float,
    origin_lon: float,
) -> list[float]:
    ring = close_ring(coords)
    if len(ring) < 2:
        return []
    lengths: list[float] = []
    for i in range(len(ring) - 1):
        x1, y1 = to_xy(ring[i][0], ring[i][1], origin_lat=origin_lat, origin_lon=origin_lon)
        x2, y2 = to_xy(
            ring[i + 1][0],
            ring[i + 1][1],
            origin_lat=origin_lat,
            origin_lon=origin_lon,
        )
        lengths.append(math.hypot(x2 - x1, y2 - y1) * 3.280839895)
    return lengths


def bbox_ft(
    coords: Sequence[tuple[float, float]],
    *,
    origin_lat: float,
    origin_lon: float,
) -> tuple[float, float]:
    """Axis-aligned bounding box width × height in feet (local EN)."""
    if not coords:
        return 0.0, 0.0
    xy = [to_xy(la, lo, origin_lat=origin_lat, origin_lon=origin_lon) for la, lo in coords]
    xs = [p[0] for p in xy]
    ys = [p[1] for p in xy]
    w = (max(xs) - min(xs)) * 3.280839895
    h = (max(ys) - min(ys)) * 3.280839895
    return w, h


def centroid(
    coords: Sequence[tuple[float, float]],
) -> tuple[float, float]:
    if not coords:
        return 0.0, 0.0
    # Drop closing duplicate if present
    pts = list(coords)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    lat = sum(p[0] for p in pts) / len(pts)
    lon = sum(p[1] for p in pts) / len(pts)
    return lat, lon


def polygon_sha256(coords: Iterable[tuple[float, float]]) -> str:
    """Content hash of rounded coordinates (stable across float noise)."""
    rounded = [[round(la, 7), round(lo, 7)] for la, lo in coords]
    payload = json.dumps(rounded, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def gla_band_from_footprint(
    footprint_sqft: float,
    *,
    factor_low: float = 0.85,
    factor_high: float = 0.95,
) -> dict[str, float]:
    """Heuristic interior GLA band from exterior roof-print (1-story)."""
    return {
        "low": round(footprint_sqft * factor_low, 1),
        "high": round(footprint_sqft * factor_high, 1),
        "factor_low": factor_low,
        "factor_high": factor_high,
    }


def path_length_m(
    coords: Sequence[tuple[float, float]],
    *,
    origin_lat: float,
    origin_lon: float,
) -> float:
    """Open polyline length in meters (does not close the ring)."""
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for i in range(len(coords) - 1):
        x1, y1 = to_xy(coords[i][0], coords[i][1], origin_lat=origin_lat, origin_lon=origin_lon)
        x2, y2 = to_xy(
            coords[i + 1][0],
            coords[i + 1][1],
            origin_lat=origin_lat,
            origin_lon=origin_lon,
        )
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def m_to_ft(m: float) -> float:
    return m * 3.280839895
