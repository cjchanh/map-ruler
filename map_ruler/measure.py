"""Core measure pipeline: geocode → footprints / vertices → scale → receipt."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

from map_ruler.footprints import FootprintError, fetch_buildings_overpass
from map_ruler.geocode import GeocodeError, geocode_address
from map_ruler.geometry import (
    bbox_ft,
    centroid,
    edge_lengths_ft,
    gla_band_from_footprint,
    m2_to_sqft,
    m_to_ft,
    path_length_m,
    polygon_sha256,
    ring_area_m2,
    to_xy,
)
from map_ruler.receipt import base_receipt
from map_ruler.scale import (
    apply_linear_scale,
    build_scale_chain,
    combined_uncertainty_pct,
    ground_segment_calibrator,
    parse_segment,
)
from map_ruler.vertices import VerticesError, load_vertices

METHOD = (
    "OSM building ways (often source=microsoft/BuildingFootprints) within radius; "
    "or operator/agent --vertices polyline/polygon; "
    "local equirectangular shoelace/path length; scale_chain calibrators; "
    "optional two-point ground scale; rings stored as coords_latlon for plot."
)


def measure(
    *,
    address: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    feature: str = "roof",
    radius_m: float = 60.0,
    calibrators: Sequence[str] = ("basemap",),
    max_candidates: int = 12,
    vertices_path: str | Path | None = None,
    include_building_context: bool = True,
    scale_segment: str | None = None,
    scale_length_ft: float | None = None,
    include_rings: bool = True,
    parcel_layer: str | None = None,
) -> dict[str, Any]:
    """Run measure-testify. Returns sealed receipt dict."""
    feature = (feature or "roof").lower().strip()
    if feature not in {"roof", "fence", "driveway", "building", "parcel"}:
        return base_receipt(
            status="ERROR",
            query=_query(
                address, lat, lon, feature, radius_m, calibrators, vertices_path,
                scale_segment, scale_length_ft, parcel_layer,
            ),
            geocode=None,
            scale_chain=[],
            candidates=[],
            primary=None,
            method=METHOD,
            error={"kind": "VALIDATION", "message": f"unsupported feature: {feature}"},
        )

    query = _query(
        address, lat, lon, feature, radius_m, calibrators, vertices_path,
        scale_segment, scale_length_ft, parcel_layer,
    )

    try:
        geocode = _resolve_geocode(address=address, lat=lat, lon=lon)
    except GeocodeError as e:
        return base_receipt(
            status="ERROR",
            query=query,
            geocode=None,
            scale_chain=[],
            candidates=[],
            primary=None,
            method=METHOD,
            error={"kind": "GEOCODE", "message": str(e)},
        )

    pin_lat = geocode["lat"]
    pin_lon = geocode["lon"]

    try:
        chain = build_scale_chain(list(calibrators), lat=pin_lat)
    except ValueError as e:
        return base_receipt(
            status="ERROR",
            query=query,
            geocode=geocode,
            scale_chain=[],
            candidates=[],
            primary=None,
            method=METHOD,
            error={"kind": "VALIDATION", "message": str(e)},
        )

    linear_factor = 1.0
    if scale_segment:
        try:
            p1, p2 = parse_segment(scale_segment)
            true_ft = (
                scale_length_ft
                if scale_length_ft is not None
                else m_to_ft(sum((4.42, 5.03)) / 2.0)  # sedan mid ≈ 15.5 ft
            )
            # m_to_ft of mid meters: 4.725 * 3.28084 ≈ 15.5
            if scale_length_ft is None:
                true_ft = 15.5
            gcal, linear_factor = ground_segment_calibrator(
                p1, p2, true_length_ft=true_ft, pin_lat=pin_lat, pin_lon=pin_lon
            )
            chain = list(chain) + [gcal]
        except ValueError as e:
            return base_receipt(
                status="ERROR",
                query=query,
                geocode=geocode,
                scale_chain=[c.to_dict() for c in chain],
                candidates=[],
                primary=None,
                method=METHOD,
                error={"kind": "SCALE_SEGMENT", "message": str(e)},
            )

    scale_dicts = [c.to_dict() for c in chain]
    unc = combined_uncertainty_pct(chain)

    # Parcel-only (or parcel primary) path
    if feature == "parcel" or parcel_layer:
        parcel_block = None
        parcel_err = None
        layer_key = parcel_layer or "ontario_demo"
        try:
            from map_ruler.parcel import ParcelError, query_parcel_at_point, resolve_layer_url

            layer_url, layer_note = resolve_layer_url(layer_key)
            parcel_block = query_parcel_at_point(
                pin_lat, pin_lon, layer_query_url=layer_url, distance_m=max(15.0, radius_m / 2)
            )
            if parcel_block is not None:
                parcel_block["layer_note"] = layer_note
                parcel_block["id"] = "parcel:primary"
                parcel_block["kind"] = "parcel"
                parcel_block["combined_uncertainty_pct"] = unc
                parcel_block["linear_scale_factor"] = round(linear_factor, 6)
                # apply linear scale to area if present
                if parcel_block.get("footprint_m2") is not None and linear_factor != 1.0:
                    from map_ruler.scale import apply_linear_scale
                    from map_ruler.geometry import m2_to_sqft

                    _, am = apply_linear_scale(
                        length_m=None,
                        area_m2=parcel_block["footprint_m2"],
                        factor=linear_factor,
                    )
                    parcel_block["footprint_m2"] = round(am or 0, 2)
                    parcel_block["footprint_sqft"] = round(m2_to_sqft(am or 0), 1)
        except Exception as e:  # noqa: BLE001
            parcel_err = str(e)

        if feature == "parcel":
            if parcel_block is None:
                return base_receipt(
                    status="ABSTAIN" if not parcel_err else "ERROR",
                    query=query,
                    geocode=geocode,
                    scale_chain=scale_dicts,
                    candidates=[],
                    primary=None,
                    method=METHOD + f" parcel_layer={layer_key}.",
                    error={
                        "kind": "PARCEL",
                        "message": parcel_err
                        or f"no parcel feature at pin for layer {layer_key}",
                    },
                )
            # optional building context
            context: list[dict[str, Any]] = []
            if include_building_context:
                try:
                    buildings = fetch_buildings_overpass(pin_lat, pin_lon, radius_m=radius_m)
                    context = _score_buildings(
                        buildings,
                        pin_lat,
                        pin_lon,
                        linear_factor=linear_factor,
                        include_rings=include_rings,
                    )[:max_candidates]
                except FootprintError:
                    context = []
            return base_receipt(
                status="CLEAN",
                query=query,
                geocode=geocode,
                scale_chain=scale_dicts,
                candidates=context,
                primary=parcel_block,
                method=METHOD
                + f" parcel_layer={layer_key} linear_scale_factor={linear_factor:.4f} "
                f"combined_uncertainty_pct={unc}.",
            )
        # non-parcel feature with optional parcel sidecar — stash on query for receipt consumers
        if parcel_block is not None:
            query = dict(query)
            query["parcel_sidecar"] = {
                "footprint_sqft": parcel_block.get("footprint_sqft"),
                "footprint_m2": parcel_block.get("footprint_m2"),
                "attributes": {
                    k: parcel_block.get("attributes", {}).get(k)
                    for k in (
                        "PARCELID",
                        "ADDRESS_NUMBER",
                        "LINEAR_NAME_FULL",
                        "FEATURE_TYPE",
                        "PLAN_NAME",
                    )
                    if parcel_block.get("attributes")
                },
                "source_url": parcel_block.get("source_url"),
            }
        elif parcel_err:
            query = dict(query)
            query["parcel_sidecar_error"] = parcel_err

    # Operator/agent vertex path
    if vertices_path is not None:
        try:
            coords = load_vertices(vertices_path)
        except VerticesError as e:
            return base_receipt(
                status="ERROR",
                query=query,
                geocode=geocode,
                scale_chain=scale_dicts,
                candidates=[],
                primary=None,
                method=METHOD,
                error={"kind": "VERTICES", "message": str(e)},
            )
        primary = _measure_vertices(
            coords,
            pin_lat=pin_lat,
            pin_lon=pin_lon,
            feature=feature,
            unc=unc,
            source_path=str(vertices_path),
            linear_factor=linear_factor,
            include_rings=include_rings,
        )
        context: list[dict[str, Any]] = []
        if include_building_context and feature in {"fence", "driveway"}:
            try:
                buildings = fetch_buildings_overpass(pin_lat, pin_lon, radius_m=radius_m)
                context = _score_buildings(
                    buildings, pin_lat, pin_lon,
                    linear_factor=linear_factor,
                    include_rings=include_rings,
                )[:max_candidates]
            except FootprintError:
                context = []
        return base_receipt(
            status="CLEAN",
            query=query,
            geocode=geocode,
            scale_chain=scale_dicts,
            candidates=context,
            primary=primary,
            method=METHOD
            + f" vertex_mode=1 linear_scale_factor={linear_factor:.4f} "
            f"combined_uncertainty_pct={unc}.",
        )

    if feature in {"fence", "driveway"}:
        try:
            buildings = fetch_buildings_overpass(pin_lat, pin_lon, radius_m=radius_m)
        except FootprintError:
            buildings = []
        candidates = _score_buildings(
            buildings, pin_lat, pin_lon,
            linear_factor=linear_factor,
            include_rings=include_rings,
        )[:max_candidates]
        return base_receipt(
            status="PARTIAL",
            query=query,
            geocode=geocode,
            scale_chain=scale_dicts,
            candidates=candidates,
            primary=candidates[0] if candidates else None,
            method=METHOD
            + f" Feature={feature}: pass --vertices for length/area. "
            f"linear_scale_factor={linear_factor:.4f} combined_uncertainty_pct={unc}.",
            error={
                "kind": "FEATURE_PARTIAL",
                "message": (
                    f"{feature} requires --vertices (GeoJSON LineString/Polygon or "
                    "[[lat,lon],...]). Building context candidates included."
                ),
            },
        )

    try:
        buildings = fetch_buildings_overpass(pin_lat, pin_lon, radius_m=radius_m)
    except FootprintError as e:
        return base_receipt(
            status="ERROR",
            query=query,
            geocode=geocode,
            scale_chain=scale_dicts,
            candidates=[],
            primary=None,
            method=METHOD,
            error={"kind": "FOOTPRINT", "message": str(e)},
        )

    if not buildings:
        return base_receipt(
            status="ABSTAIN",
            query=query,
            geocode=geocode,
            scale_chain=scale_dicts,
            candidates=[],
            primary=None,
            method=METHOD,
            error={
                "kind": "NO_BUILDINGS",
                "message": f"no OSM buildings within {radius_m}m of pin",
            },
        )

    candidates = _score_buildings(
        buildings, pin_lat, pin_lon,
        linear_factor=linear_factor,
        include_rings=include_rings,
    )[:max_candidates]
    primary = dict(candidates[0])
    primary["combined_uncertainty_pct"] = unc
    primary["linear_scale_factor"] = round(linear_factor, 6)

    status = "CLEAN"
    if len(candidates) >= 2 and candidates[1]["dist_m_from_pin"] < 20.0:
        status = "PARTIAL"
        primary["selection_note"] = (
            "Multiple footprints within 20m of pin — primary is closest only; "
            "confirm rear cottage vs main house on satellite, or pass --vertices."
        )

    return base_receipt(
        status=status,
        query=query,
        geocode=geocode,
        scale_chain=scale_dicts,
        candidates=candidates,
        primary=primary,
        method=METHOD
        + f" linear_scale_factor={linear_factor:.4f} combined_uncertainty_pct={unc}.",
    )


def _measure_vertices(
    coords: list[tuple[float, float]],
    *,
    pin_lat: float,
    pin_lon: float,
    feature: str,
    unc: float,
    source_path: str,
    linear_factor: float = 1.0,
    include_rings: bool = True,
) -> dict[str, Any]:
    closed = len(coords) >= 4 and coords[0] == coords[-1]
    want_area = feature in {"roof", "building", "parcel"} or closed
    work = list(coords)

    length_m = path_length_m(work, origin_lat=pin_lat, origin_lon=pin_lon)
    area_m2 = 0.0
    if want_area and len(work) >= 3:
        area_m2 = ring_area_m2(work, origin_lat=pin_lat, origin_lon=pin_lon)
    elif feature in {"fence", "driveway"} and len(work) >= 3 and closed:
        area_m2 = ring_area_m2(work, origin_lat=pin_lat, origin_lon=pin_lon)

    length_m, area_m2_s = apply_linear_scale(
        length_m=length_m,
        area_m2=area_m2 if area_m2 else None,
        factor=linear_factor,
    )
    assert length_m is not None
    area_m2 = area_m2_s or 0.0
    length_ft = m_to_ft(length_m)
    area_sqft = m2_to_sqft(area_m2) if area_m2 else 0.0

    clat, clon = centroid(work)
    e, n = to_xy(clat, clon, origin_lat=pin_lat, origin_lon=pin_lon)
    # scale offsets for consistency when factor applied to geometry display
    e, n = e * linear_factor, n * linear_factor
    w_ft, h_ft = bbox_ft(work, origin_lat=pin_lat, origin_lon=pin_lon)
    w_ft, h_ft = w_ft * linear_factor, h_ft * linear_factor
    edges = [x * linear_factor for x in edge_lengths_ft(work, origin_lat=pin_lat, origin_lon=pin_lon)]

    out: dict[str, Any] = {
        "id": f"vertices:{feature}",
        "source": f"operator_vertices:{source_path}",
        "kind": "polyline" if feature in {"fence", "driveway"} and not closed else "polygon",
        "vertex_count": len(work),
        "closed_ring": closed or (want_area and len(work) >= 3),
        "length_m": round(length_m, 3),
        "length_ft": round(length_ft, 2),
        "footprint_m2": round(area_m2, 2) if area_m2 else None,
        "footprint_sqft": round(area_sqft, 1) if area_sqft else None,
        "dist_m_from_pin": round(math.hypot(e, n), 2),
        "offset_E_m": round(e, 2),
        "offset_N_m": round(n, 2),
        "bbox_ft": {"width": round(w_ft, 1), "height": round(h_ft, 1)},
        "edge_lengths_ft": [round(x, 1) for x in edges],
        "polygon_sha256": polygon_sha256(work),
        "combined_uncertainty_pct": unc,
        "linear_scale_factor": round(linear_factor, 6),
        "osm_url": None,
    }
    if include_rings:
        out["coords_latlon"] = [[round(la, 7), round(lo, 7)] for la, lo in work]
    if area_sqft:
        out["gla_band_sqft"] = gla_band_from_footprint(area_sqft)
    return out


def _query(
    address: str | None,
    lat: float | None,
    lon: float | None,
    feature: str,
    radius_m: float,
    calibrators: Sequence[str],
    vertices_path: str | Path | None,
    scale_segment: str | None = None,
    scale_length_ft: float | None = None,
    parcel_layer: str | None = None,
) -> dict[str, Any]:
    return {
        "address": address,
        "lat": lat,
        "lon": lon,
        "feature": feature,
        "radius_m": radius_m,
        "calibrators": list(calibrators),
        "vertices_path": str(vertices_path) if vertices_path else None,
        "scale_segment": scale_segment,
        "scale_length_ft": scale_length_ft,
        "parcel_layer": parcel_layer,
    }


def _resolve_geocode(
    *,
    address: str | None,
    lat: float | None,
    lon: float | None,
) -> dict[str, Any]:
    if lat is not None and lon is not None:
        return {
            "lat": float(lat),
            "lon": float(lon),
            "display_name": address or f"{lat},{lon}",
            "source": "operator_coords",
        }
    if address:
        return geocode_address(address)
    raise GeocodeError("provide --address or --lat/--lon")


def _score_buildings(
    buildings: list[dict[str, Any]],
    pin_lat: float,
    pin_lon: float,
    *,
    linear_factor: float = 1.0,
    include_rings: bool = True,
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for b in buildings:
        coords = b["coords"]
        m2 = ring_area_m2(coords, origin_lat=pin_lat, origin_lon=pin_lon)
        _, m2_s = apply_linear_scale(length_m=None, area_m2=m2, factor=linear_factor)
        assert m2_s is not None
        m2 = m2_s
        sqft = m2_to_sqft(m2)
        clat, clon = centroid(coords)
        e, n = to_xy(clat, clon, origin_lat=pin_lat, origin_lon=pin_lon)
        dist = math.hypot(e, n)
        w_ft, h_ft = bbox_ft(coords, origin_lat=pin_lat, origin_lon=pin_lon)
        w_ft, h_ft = w_ft * linear_factor, h_ft * linear_factor
        edges = [
            x * linear_factor
            for x in edge_lengths_ft(coords, origin_lat=pin_lat, origin_lon=pin_lon)
        ]
        osm_id = b.get("osm_id")
        row: dict[str, Any] = {
            "id": b["id"],
            "source": b.get("source") or "openstreetmap",
            "footprint_m2": round(m2, 2),
            "footprint_sqft": round(sqft, 1),
            "dist_m_from_pin": round(dist, 2),
            "offset_E_m": round(e, 2),
            "offset_N_m": round(n, 2),
            "bbox_ft": {"width": round(w_ft, 1), "height": round(h_ft, 1)},
            "edge_lengths_ft": [round(x, 1) for x in edges],
            "gla_band_sqft": gla_band_from_footprint(sqft),
            "polygon_sha256": polygon_sha256(coords),
            "linear_scale_factor": round(linear_factor, 6),
            "osm_url": f"https://www.openstreetmap.org/way/{osm_id}" if osm_id else None,
        }
        if include_rings:
            row["coords_latlon"] = [[round(la, 7), round(lo, 7)] for la, lo in coords]
        scored.append(row)
    scored.sort(key=lambda r: r["dist_m_from_pin"])
    return scored
