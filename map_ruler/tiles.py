"""Satellite / map tile underlay for plot (Esri World Imagery default)."""

from __future__ import annotations

import io
import math
import urllib.request
from typing import Any

from map_ruler.geocode import USER_AGENT
from map_ruler.geometry import meters_per_deg

# Free tile endpoints (no API key). Esri imagery is common for satellite underlay.
TILE_SOURCES = {
    "esri": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "osm": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
}


class TileError(RuntimeError):
    pass


def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat_deg)
    n = 2.0**zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def num2deg(xtile: int, ytile: int, zoom: int) -> tuple[float, float]:
    """NW corner of tile as (lat, lon)."""
    n = 2.0**zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def _fetch_tile_bytes(url: str, *, timeout: float = 15.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def choose_zoom(
    *,
    lat: float,
    radius_m: float,
    target_px: int = 800,
) -> int:
    """Pick zoom so ~2*radius_m spans roughly target_px."""
    # meters per pixel at equator ≈ 156543.03 * cos(lat) / 2^z
    m_per_px_wanted = (2 * radius_m) / max(200, target_px)
    cos_lat = max(0.2, math.cos(math.radians(lat)))
    # m_per_px = 156543.03 * cos / 2^z  =>  2^z = 156543.03 * cos / m_per_px
    z = math.log2(156543.03 * cos_lat / max(0.05, m_per_px_wanted))
    return int(max(15, min(20, round(z))))


def fetch_underlay(
    *,
    pin_lat: float,
    pin_lon: float,
    half_span_m: float = 80.0,
    source: str = "esri",
    zoom: int | None = None,
    max_tiles: int = 36,
) -> dict[str, Any]:
    """Fetch and stitch tiles; return array + extent in local EN meters.

    Returns dict:
      image: HxWx3 or HxWx4 ndarray
      extent: [e_min, e_max, n_min, n_max] for imshow origin='upper' careful
      zoom, source, tile_count
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError as e:
        raise TileError(
            "tile underlay needs Pillow (+ numpy via matplotlib stack): pip install Pillow"
        ) from e

    tpl = TILE_SOURCES.get(source)
    if not tpl:
        raise TileError(f"unknown tile source: {source}; choose {list(TILE_SOURCES)}")

    z = zoom if zoom is not None else choose_zoom(lat=pin_lat, radius_m=half_span_m)
    m_lat, m_lon = meters_per_deg(pin_lat)

    # Corner lat/lon of desired EN box
    dlat = half_span_m / m_lat
    dlon = half_span_m / m_lon
    lat_n, lat_s = pin_lat + dlat, pin_lat - dlat
    lon_w, lon_e = pin_lon - dlon, pin_lon + dlon

    x_min, y_max = deg2num(lat_s, lon_w, z)  # south-west-ish: careful y increases south
    x_max, y_min = deg2num(lat_n, lon_e, z)
    # y_min is north (smaller y), y_max is south
    x0, x1 = min(x_min, x_max), max(x_min, x_max)
    y0, y1 = min(y_min, y_max), max(y_min, y_max)

    nx = x1 - x0 + 1
    ny = y1 - y0 + 1
    if nx * ny > max_tiles:
        # zoom out once
        z = max(14, z - 1)
        x_min, y_max = deg2num(lat_s, lon_w, z)
        x_max, y_min = deg2num(lat_n, lon_e, z)
        x0, x1 = min(x_min, x_max), max(x_min, x_max)
        y0, y1 = min(y_min, y_max), max(y_min, y_max)
        nx = x1 - x0 + 1
        ny = y1 - y0 + 1
        if nx * ny > max_tiles:
            raise TileError(f"too many tiles {nx}x{ny} at z={z}; shrink radius")

    tile_size = 256
    mosaic = Image.new("RGB", (nx * tile_size, ny * tile_size))
    fetched = 0
    for ix, x in enumerate(range(x0, x1 + 1)):
        for iy, y in enumerate(range(y0, y1 + 1)):
            url = tpl.format(z=z, x=x, y=y)
            try:
                data = _fetch_tile_bytes(url)
                tile = Image.open(io.BytesIO(data)).convert("RGB")
                mosaic.paste(tile, (ix * tile_size, iy * tile_size))
                fetched += 1
            except Exception:
                # leave black on miss
                pass

    if fetched == 0:
        raise TileError("no tiles fetched — network or blocked endpoint")

    arr = np.asarray(mosaic)

    # Geographic bounds of mosaic: NW of (x0,y0) to SE of (x1+1, y1+1)
    lat_nw, lon_nw = num2deg(x0, y0, z)
    lat_se, lon_se = num2deg(x1 + 1, y1 + 1, z)

    def to_en(la: float, lo: float) -> tuple[float, float]:
        e = (lo - pin_lon) * m_lon
        n = (la - pin_lat) * m_lat
        return e, n

    e_w, n_n = to_en(lat_nw, lon_nw)
    e_e, n_s = to_en(lat_se, lon_se)
    # imshow extent: left, right, bottom, top
    extent = [e_w, e_e, n_s, n_n]

    return {
        "image": arr,
        "extent": extent,
        "zoom": z,
        "source": source,
        "tile_count": fetched,
    }
