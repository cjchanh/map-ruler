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
            "Footprint ≠ GLA."
        ),
    )
    parser.add_argument("--version", action="version", version=f"map-ruler {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("measure", help="Measure buildings or vertex paths near an address/pin")
    m.add_argument("--address", type=str, default=None, help="Street address")
    m.add_argument("--lat", type=float, default=None)
    m.add_argument("--lon", type=float, default=None)
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
        help="GeoJSON LineString/Polygon or [[lat,lon],...] JSON for fence/driveway/roof",
    )
    m.add_argument(
        "--no-building-context",
        action="store_true",
        help="With --vertices, skip nearby building context fetch",
    )
    m.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write receipt JSON to this path",
    )
    m.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON to stdout",
    )
    m.add_argument("--max-candidates", type=int, default=12)

    args = parser.parse_args(argv)

    if args.cmd == "measure":
        cals = [c.strip() for c in args.calibrators.split(",") if c.strip()]
        receipt = measure(
            address=args.address,
            lat=args.lat,
            lon=args.lon,
            feature=args.feature,
            radius_m=args.radius_m,
            calibrators=cals,
            max_candidates=args.max_candidates,
            vertices_path=args.vertices,
            include_building_context=not args.no_building_context,
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
                f"gla={primary.get('gla_band_sqft')} "
                f"out={args.out}",
                file=sys.stderr,
            )
        print(text if args.pretty or not args.out else json.dumps(receipt, indent=2))
        if receipt.get("status") == "ERROR":
            return 2
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
