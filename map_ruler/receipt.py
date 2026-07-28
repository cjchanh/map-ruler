"""Seal measure-testify receipts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from map_ruler import SCHEMA_VERSION


DISCLAIMER = (
    "Exterior footprint / polyline from map vectors or operator vertices. "
    "NOT a cadastral survey. NOT guaranteed interior living area (GLA). "
    "Roof print ≠ heated GLA. Multi-structure lots require structure selection. "
    "Scale chain documents method; field laser/tape upgrades authority."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_dumps(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def seal(receipt: dict[str, Any]) -> dict[str, Any]:
    """Add receipt_sha256 over all fields except receipt_sha256."""
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    digest = hashlib.sha256(canonical_dumps(body).encode("utf-8")).hexdigest()
    out = dict(receipt)
    out["receipt_sha256"] = digest
    return out


def maps_links(lat: float, lon: float, *, address: str | None = None) -> dict[str, str]:
    place = (
        f"https://www.google.com/maps/place/{urllib_quote(address)}"
        if address
        else f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    )
    return {
        "google_satellite": f"https://www.google.com/maps/@{lat},{lon},48m/data=!3m1!1e3",
        "google_place": place,
        "osm": f"https://www.openstreetmap.org/#map=19/{lat}/{lon}",
        "earth": f"https://earth.google.com/web/@{lat},{lon},20a,35d,35y,0h,0t,0r",
    }


def urllib_quote(s: str) -> str:
    import urllib.parse

    return urllib.parse.quote(s)


def base_receipt(
    *,
    status: str,
    query: dict[str, Any],
    geocode: dict[str, Any] | None,
    scale_chain: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    primary: dict[str, Any] | None,
    method: str,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lat = (geocode or {}).get("lat")
    lon = (geocode or {}).get("lon")
    maps = maps_links(lat, lon, address=query.get("address")) if lat is not None and lon is not None else {}
    rec: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "generated_at_utc": utc_now(),
        "query": query,
        "geocode": geocode or {},
        "scale_chain": scale_chain,
        "candidates": candidates,
        "primary": primary,
        "method": method,
        "disclaimer": DISCLAIMER,
        "maps": maps,
    }
    if error:
        rec["error"] = error
    return seal(rec)
