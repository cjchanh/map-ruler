"""Plot measure receipts / building footprints to PNG."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from map_ruler.geometry import to_xy
from map_ruler.measure import measure
from map_ruler.vertices import load_vertices


class PlotError(RuntimeError):
    pass


def _require_matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPoly

        return plt, MplPoly
    except ImportError as e:
        raise PlotError(
            "matplotlib required for plot — pip install matplotlib"
        ) from e


def plot_from_receipt(
    receipt: dict[str, Any],
    *,
    out_path: Path,
    title: str | None = None,
    vertices_path: str | Path | None = None,
    basemap: bool = False,
    basemap_source: str = "esri",
) -> Path:
    """Render a receipt's candidates (+ optional vertices) to PNG."""
    plt, MplPoly = _require_matplotlib()
    geo = receipt.get("geocode") or {}
    pin_lat = geo.get("lat")
    pin_lon = geo.get("lon")
    if pin_lat is None or pin_lon is None:
        raise PlotError("receipt missing geocode lat/lon")

    fig, ax = plt.subplots(figsize=(10, 10), dpi=140)
    colors = [
        "#e74c3c",
        "#3498db",
        "#2ecc71",
        "#9b59b6",
        "#f39c12",
        "#1abc9c",
        "#95a5a6",
        "#e67e22",
    ]

    basemap_note = ""
    if basemap:
        try:
            from map_ruler.tiles import fetch_underlay

            half = float((receipt.get("query") or {}).get("radius_m") or 60.0)
            half = max(40.0, min(120.0, half * 1.2))
            under = fetch_underlay(
                pin_lat=float(pin_lat),
                pin_lon=float(pin_lon),
                half_span_m=half,
                source=basemap_source,
            )
            ax.imshow(
                under["image"],
                extent=under["extent"],
                origin="upper",
                zorder=0,
                alpha=0.95,
            )
            basemap_note = f" · basemap={under['source']} z{under['zoom']} ({under['tile_count']} tiles)"
        except Exception as e:  # noqa: BLE001 — underlay optional
            basemap_note = f" · basemap failed: {e}"

    plotted_any = False

    for i, c in enumerate(receipt.get("candidates") or []):
        color = colors[i % len(colors)]
        ring = c.get("coords_latlon")
        if ring and len(ring) >= 3:
            xy = [
                to_xy(float(p[0]), float(p[1]), origin_lat=float(pin_lat), origin_lon=float(pin_lon))
                for p in ring
            ]
            if xy[0] != xy[-1]:
                xy = xy + [xy[0]]
            poly = MplPoly(
                xy,
                closed=True,
                facecolor=color,
                alpha=0.35 if basemap else 0.4,
                edgecolor="white" if basemap else color,
                linewidth=2.0 if basemap else 1.8,
                label=f"{c.get('id')} · {c.get('footprint_sqft')} ft²",
                zorder=2,
            )
            ax.add_patch(poly)
            e = sum(p[0] for p in xy[:-1]) / max(1, len(xy) - 1)
            n = sum(p[1] for p in xy[:-1]) / max(1, len(xy) - 1)
            ax.text(
                e,
                n,
                f"{c.get('footprint_sqft')}",
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
                color="#111",
            )
            plotted_any = True
            continue
        # Fallback: AABB from offset + bbox_ft (v0.3 receipts without rings)
        e = float(c.get("offset_E_m") or 0)
        n = float(c.get("offset_N_m") or 0)
        bb = c.get("bbox_ft") or {}
        w_m = float(bb.get("width") or 0) * 0.3048
        h_m = float(bb.get("height") or 0) * 0.3048
        if w_m > 0 and h_m > 0:
            half_w, half_h = w_m / 2, h_m / 2
            corners = [
                (e - half_w, n - half_h),
                (e + half_w, n - half_h),
                (e + half_w, n + half_h),
                (e - half_w, n + half_h),
            ]
            poly = MplPoly(
                corners,
                closed=True,
                facecolor=color,
                alpha=0.35,
                edgecolor=color,
                linewidth=1.5,
                label=f"{c.get('id')} · {c.get('footprint_sqft')} ft² (bbox)",
            )
            ax.add_patch(poly)
            ax.text(
                e,
                n,
                f"{c.get('footprint_sqft')}",
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
                color="#111",
            )
            plotted_any = True

    # Primary vertex path if provided or recorded
    vpath = vertices_path or (receipt.get("query") or {}).get("vertices_path")
    if vpath and Path(vpath).is_file():
        try:
            coords = load_vertices(vpath)
            xy = [
                to_xy(la, lo, origin_lat=float(pin_lat), origin_lon=float(pin_lon))
                for la, lo in coords
            ]
            xs = [p[0] for p in xy]
            ys = [p[1] for p in xy]
            ax.plot(xs, ys, "k-o", linewidth=2.5, markersize=5, label="vertices path")
            primary = receipt.get("primary") or {}
            mid = len(xs) // 2
            if xs:
                ax.annotate(
                    f"{primary.get('length_ft', '?')} ft",
                    (xs[mid], ys[mid]),
                    textcoords="offset points",
                    xytext=(6, 6),
                    fontsize=10,
                    fontweight="bold",
                )
            plotted_any = True
        except Exception as e:  # noqa: BLE001
            ax.text(
                0.02,
                0.02,
                f"vertices load failed: {e}",
                transform=ax.transAxes,
                fontsize=8,
                color="red",
            )

    primary = receipt.get("primary") or {}
    # If primary is a footprint without candidates drawn, mark centroid
    if primary and primary.get("id", "").startswith("way/"):
        e = float(primary.get("offset_E_m") or 0)
        n = float(primary.get("offset_N_m") or 0)
        ax.plot(e, n, "r*", markersize=14, label=f"primary {primary.get('id')}")

    ax.plot(0, 0, "k*", markersize=18, label="pin", zorder=10)
    ax.axhline(0, color="#bbb", lw=0.5)
    ax.axvline(0, color="#bbb", lw=0.5)

    # 10 ft grid
    grid_color = "#ffffff55" if basemap else "#f0f0f0"
    for g in range(-200, 201, 10):
        ax.axhline(g * 0.3048, color=grid_color, lw=0.4, zorder=1)
        ax.axvline(g * 0.3048, color=grid_color, lw=0.4, zorder=1)

    ax.set_aspect("equal")
    # Autoscale with pad
    ax.relim()
    ax.autoscale()
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    pad = 5
    ax.set_xlim(xlim[0] - pad, xlim[1] + pad)
    ax.set_ylim(ylim[0] - pad, ylim[1] + pad)

    def m2ft(x: float) -> float:
        return x / 0.3048

    def ft2m(x: float) -> float:
        return x * 0.3048

    secax = ax.secondary_xaxis("top", functions=(m2ft, ft2m))
    secay = ax.secondary_yaxis("right", functions=(m2ft, ft2m))
    secax.set_xlabel("feet east of pin")
    secay.set_ylabel("feet north of pin")
    ax.set_xlabel("meters east of pin")
    ax.set_ylabel("meters north of pin")

    status = receipt.get("status", "?")
    addr = (receipt.get("query") or {}).get("address") or ""
    default_title = f"map-ruler · {status}"
    if addr:
        default_title += f"\n{addr}"
    if primary.get("footprint_sqft"):
        default_title += f"\nprimary {primary.get('footprint_sqft')} ft²"
    if primary.get("length_ft"):
        default_title += f" · length {primary.get('length_ft')} ft"
    if basemap_note:
        default_title += basemap_note
    ax.set_title(title or default_title, fontsize=11)
    ax.legend(loc="upper left", fontsize=7, framealpha=0.9)
    ax.annotate("N", xy=(0.92, 0.95), xycoords="axes fraction", fontsize=14, fontweight="bold")
    ax.annotate("↑", xy=(0.92, 0.90), xycoords="axes fraction", fontsize=16)

    if not plotted_any:
        ax.text(
            0.5,
            0.5,
            "no drawable candidates\n(re-run measure or pass --vertices)",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=12,
            color="#666",
        )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def plot_measure(
    *,
    out_path: Path,
    address: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    feature: str = "roof",
    radius_m: float = 60.0,
    calibrators: list[str] | None = None,
    vertices_path: str | Path | None = None,
    receipt_path: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Measure (or load receipt) then plot. Returns (png_path, receipt)."""
    if receipt_path is not None:
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    else:
        receipt = measure(
            address=address,
            lat=lat,
            lon=lon,
            feature=feature,
            radius_m=radius_m,
            calibrators=calibrators or ["basemap"],
            vertices_path=vertices_path,
            include_building_context=True,
        )
    png = plot_from_receipt(
        receipt,
        out_path=out_path,
        vertices_path=vertices_path
        or (receipt.get("query") or {}).get("vertices_path"),
    )
    return png, receipt


def plot_true_footprints(
    *,
    lat: float,
    lon: float,
    radius_m: float,
    out_path: Path,
    address: str | None = None,
    calibrators: list[str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Re-fetch OSM rings and plot true polygons (best visual)."""
    plt, MplPoly = _require_matplotlib()
    from map_ruler.footprints import fetch_buildings_overpass
    from map_ruler.geometry import centroid, m2_to_sqft, ring_area_m2

    receipt = measure(
        address=address,
        lat=lat,
        lon=lon,
        feature="roof",
        radius_m=radius_m,
        calibrators=calibrators or ["basemap"],
    )
    buildings = fetch_buildings_overpass(lat, lon, radius_m=radius_m)

    fig, ax = plt.subplots(figsize=(10, 10), dpi=140)
    colors = [
        "#e74c3c",
        "#3498db",
        "#2ecc71",
        "#9b59b6",
        "#f39c12",
        "#1abc9c",
        "#95a5a6",
    ]
    for i, b in enumerate(buildings):
        coords = b["coords"]
        xy = [to_xy(la, lo, origin_lat=lat, origin_lon=lon) for la, lo in coords]
        if xy[0] != xy[-1]:
            xy = xy + [xy[0]]
        color = colors[i % len(colors)]
        m2 = ring_area_m2(coords, origin_lat=lat, origin_lon=lon)
        sqft = m2_to_sqft(m2)
        poly = MplPoly(
            xy,
            closed=True,
            facecolor=color,
            alpha=0.4,
            edgecolor=color,
            linewidth=2,
            label=f"{b['id']} · {sqft:.0f} ft²",
        )
        ax.add_patch(poly)
        clat, clon = centroid(coords)
        e, n = to_xy(clat, clon, origin_lat=lat, origin_lon=lon)
        ax.text(e, n, f"{sqft:.0f}", ha="center", va="center", fontsize=8, fontweight="bold")

    ax.plot(0, 0, "k*", markersize=18, label="pin", zorder=10)
    ax.set_aspect("equal")
    ax.relim()
    ax.autoscale()
    for g in range(-200, 201, 10):
        ax.axhline(g * 0.3048, color="#f0f0f0", lw=0.4)
        ax.axvline(g * 0.3048, color="#f0f0f0", lw=0.4)

    def m2ft(x: float) -> float:
        return x / 0.3048

    def ft2m(x: float) -> float:
        return x * 0.3048

    secax = ax.secondary_xaxis("top", functions=(m2ft, ft2m))
    secay = ax.secondary_yaxis("right", functions=(m2ft, ft2m))
    secax.set_xlabel("feet east of pin")
    secay.set_ylabel("feet north of pin")
    ax.set_xlabel("meters east of pin")
    ax.set_ylabel("meters north of pin")
    title = "map-ruler · true OSM footprints"
    if address:
        title += f"\n{address}"
    primary = receipt.get("primary") or {}
    if primary.get("footprint_sqft"):
        title += f"\nprimary {primary.get('footprint_sqft')} ft²"
    ax.set_title(title)
    ax.legend(loc="upper left", fontsize=7, framealpha=0.9)
    ax.annotate("N↑", xy=(0.92, 0.93), xycoords="axes fraction", fontsize=12, fontweight="bold")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path, receipt
