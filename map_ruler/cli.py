"""map-ruler CLI — measure that testifies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from map_ruler import __version__
from map_ruler.measure import measure


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="map-ruler",
        description=(
            "Open spatial measure-testify: geocode → OSM/MS building footprints → "
            "scale chain → sealed receipt. Optional --vertices for fence/driveway/roof. "
            "plot: PNG overlay. Footprint ≠ GLA."
        ),
    )
    parser.add_argument("--version", action="version", version=f"map-ruler {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("measure", help="Measure buildings or vertex paths near an address/pin")
    _add_common_location(m)
    m.add_argument(
        "--feature",
        choices=["roof", "fence", "driveway", "building", "parcel"],
        default="roof",
    )
    m.add_argument("--radius-m", type=float, default=60.0)
    m.add_argument(
        "--calibrators",
        type=str,
        default="basemap",
        help="Comma list: basemap,car_sedan,parking_stall,dual_basemap",
    )
    m.add_argument(
        "--vertices",
        type=Path,
        default=None,
        help="GeoJSON LineString/Polygon or [[lat,lon],...] JSON",
    )
    m.add_argument(
        "--no-building-context",
        action="store_true",
        help="With --vertices, skip nearby building context fetch",
    )
    m.add_argument(
        "--scale-segment",
        type=str,
        default=None,
        help="Two-point ground scale: lat1,lon1,lat2,lon2 (e.g. car bumpers)",
    )
    m.add_argument(
        "--scale-length-ft",
        type=float,
        default=None,
        help="Declared true length of scale segment in feet (default 15.5 sedan mid)",
    )
    m.add_argument(
        "--no-rings",
        action="store_true",
        help="Omit coords_latlon from receipt (smaller JSON)",
    )
    m.add_argument("--out", type=Path, default=None, help="Write receipt JSON")
    m.add_argument("--pretty", action="store_true")
    m.add_argument("--max-candidates", type=int, default=12)

    p = sub.add_parser("plot", help="Measure (or load receipt) and write PNG overlay")
    _add_common_location(p)
    p.add_argument(
        "--feature",
        choices=["roof", "fence", "driveway", "building", "parcel"],
        default="roof",
    )
    p.add_argument("--radius-m", type=float, default=60.0)
    p.add_argument("--calibrators", type=str, default="basemap")
    p.add_argument("--vertices", type=Path, default=None)
    p.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help="Existing receipt JSON (skip live measure)",
    )
    p.add_argument(
        "--true-footprints",
        action="store_true",
        help="Re-fetch OSM rings and plot true polygons (network)",
    )
    p.add_argument(
        "--scale-segment",
        type=str,
        default=None,
        help="Two-point ground scale: lat1,lon1,lat2,lon2",
    )
    p.add_argument("--scale-length-ft", type=float, default=None)
    p.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output PNG path",
    )
    p.add_argument(
        "--receipt-out",
        type=Path,
        default=None,
        help="Also write receipt JSON",
    )

    args = parser.parse_args(argv)

    if args.cmd == "measure":
        return _cmd_measure(args)
    if args.cmd == "plot":
        return _cmd_plot(args)
    return 1


def _add_common_location(p: argparse.ArgumentParser) -> None:
    p.add_argument("--address", type=str, default=None)
    p.add_argument("--lat", type=float, default=None)
    p.add_argument("--lon", type=float, default=None)


def _cals(s: str) -> list[str]:
    return [c.strip() for c in s.split(",") if c.strip()]


def _cmd_measure(args: argparse.Namespace) -> int:
    receipt = measure(
        address=args.address,
        lat=args.lat,
        lon=args.lon,
        feature=args.feature,
        radius_m=args.radius_m,
        calibrators=_cals(args.calibrators),
        max_candidates=args.max_candidates,
        vertices_path=args.vertices,
        include_building_context=not args.no_building_context,
        scale_segment=args.scale_segment,
        scale_length_ft=args.scale_length_ft,
        include_rings=not args.no_rings,
    )
    text = json.dumps(receipt, indent=2 if args.pretty else None, sort_keys=args.pretty)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2) + "\n")
        primary = receipt.get("primary") or {}
        print(
            f"status={receipt.get('status')} "
            f"sqft={primary.get('footprint_sqft')} "
            f"length_ft={primary.get('length_ft')} "
            f"out={args.out}",
            file=sys.stderr,
        )
    print(text if args.pretty or not args.out else json.dumps(receipt, indent=2))
    return 2 if receipt.get("status") == "ERROR" else 0


def _cmd_plot(args: argparse.Namespace) -> int:
    from map_ruler.plot import PlotError, plot_from_receipt, plot_true_footprints

    try:
        if args.true_footprints:
            if args.lat is None or args.lon is None:
                # need pin — measure first for geocode if address only
                if not args.address and args.receipt is None:
                    print("plot --true-footprints needs --address or --lat/--lon", file=sys.stderr)
                    return 2
            if args.receipt:
                rec = json.loads(args.receipt.read_text(encoding="utf-8"))
                lat = rec["geocode"]["lat"]
                lon = rec["geocode"]["lon"]
                address = (rec.get("query") or {}).get("address")
            elif args.lat is not None and args.lon is not None:
                lat, lon = args.lat, args.lon
                address = args.address
            else:
                # geocode via measure
                rec0 = measure(
                    address=args.address,
                    feature="roof",
                    radius_m=args.radius_m,
                    calibrators=_cals(args.calibrators),
                )
                lat = rec0["geocode"]["lat"]
                lon = rec0["geocode"]["lon"]
                address = args.address
            png, receipt = plot_true_footprints(
                lat=lat,
                lon=lon,
                radius_m=args.radius_m,
                out_path=args.out,
                address=address,
                calibrators=_cals(args.calibrators),
            )
        elif args.receipt:
            receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
            png = plot_from_receipt(
                receipt,
                out_path=args.out,
                vertices_path=args.vertices,
            )
        else:
            receipt = measure(
                address=args.address,
                lat=args.lat,
                lon=args.lon,
                feature=args.feature,
                radius_m=args.radius_m,
                calibrators=_cals(args.calibrators),
                vertices_path=args.vertices,
                scale_segment=args.scale_segment,
                scale_length_ft=args.scale_length_ft,
                include_rings=True,
            )
            # Prefer receipt rings (no second Overpass) unless --true-footprints
            has_rings = any(
                (c.get("coords_latlon") for c in (receipt.get("candidates") or []))
            )
            if (
                args.feature in {"roof", "building"}
                and not args.vertices
                and not has_rings
            ):
                geo = receipt.get("geocode") or {}
                png, receipt = plot_true_footprints(
                    lat=geo["lat"],
                    lon=geo["lon"],
                    radius_m=args.radius_m,
                    out_path=args.out,
                    address=args.address,
                    calibrators=_cals(args.calibrators),
                )
            else:
                png = plot_from_receipt(
                    receipt,
                    out_path=args.out,
                    vertices_path=args.vertices,
                )
    except PlotError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n")

    primary = receipt.get("primary") or {}
    print(
        f"status={receipt.get('status')} "
        f"sqft={primary.get('footprint_sqft')} "
        f"length_ft={primary.get('length_ft')} "
        f"png={png}",
        file=sys.stderr,
    )
    print(str(png))
    return 2 if receipt.get("status") == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
