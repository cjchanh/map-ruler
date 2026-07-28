"""Scale chain — stacked calibrators that defend area claims."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

# Reference lengths (meters) with uncertainty bands for ground-truth-ish objects
# seen in satellite scenes. Used when basemap CRS alone is insufficient.
CAR_SEDAN_LENGTH_M = (4.42, 5.03)  # ~14.5–16.5 ft
PARKING_STALL_LENGTH_M = (5.18, 5.79)  # ~17–19 ft


@dataclass(frozen=True)
class Calibrator:
    id: str
    kind: str
    meters_per_unit: float
    uncertainty_pct: float
    notes: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "meters_per_unit": self.meters_per_unit,
            "uncertainty_pct": self.uncertainty_pct,
            "notes": self.notes,
        }


def basemap_calibrator(*, lat: float) -> Calibrator:
    """Equirectangular projection around pin — primary scale for vector footprints."""
    # Unit = 1 meter in local EN frame (identity).
    # Uncertainty: higher near poles / long spans; local <100m is tight.
    return Calibrator(
        id="basemap_local_en",
        kind="basemap",
        meters_per_unit=1.0,
        uncertainty_pct=2.0,
        notes=(
            f"Local equirectangular EN at lat={lat:.5f}; "
            "valid for footprints within ~200m of pin. "
            "Not a cadastral survey."
        ),
    )


def car_sedan_calibrator() -> Calibrator:
    """Optional second calibrator: sedan length band for image-scale checks.

    v0 does not auto-detect cars. Declaring this calibrator documents the
    protocol: operator/agent marks bumper-to-bumper on imagery, maps pixels
    to this length band, then re-measures roof. Wider uncertainty than CRS.
    """
    mid = sum(CAR_SEDAN_LENGTH_M) / 2.0
    half_span = (CAR_SEDAN_LENGTH_M[1] - CAR_SEDAN_LENGTH_M[0]) / 2.0
    # Convert length-band half-span to percent of mid length
    unc = (half_span / mid) * 100.0 + 5.0  # band + detection/placement slack
    return Calibrator(
        id="car_sedan_band",
        kind="car_sedan",
        meters_per_unit=mid,
        uncertainty_pct=round(unc, 1),
        notes=(
            f"Sedan length band {CAR_SEDAN_LENGTH_M[0]:.2f}–{CAR_SEDAN_LENGTH_M[1]:.2f} m "
            f"(~14.5–16.5 ft). Protocol: mark vehicle on satellite, derive ft/px, "
            "re-measure roof/fence. v0 records protocol only — no auto vision."
        ),
    )


def parking_stall_calibrator() -> Calibrator:
    mid = sum(PARKING_STALL_LENGTH_M) / 2.0
    half_span = (PARKING_STALL_LENGTH_M[1] - PARKING_STALL_LENGTH_M[0]) / 2.0
    unc = (half_span / mid) * 100.0 + 4.0
    return Calibrator(
        id="parking_stall_band",
        kind="parking_stall",
        meters_per_unit=mid,
        uncertainty_pct=round(unc, 1),
        notes="Typical US stall ~9×18 ft; use painted lines when visible.",
    )


def dual_basemap_calibrator() -> Calibrator:
    return Calibrator(
        id="dual_basemap_placeholder",
        kind="dual_basemap",
        meters_per_unit=1.0,
        uncertainty_pct=5.0,
        notes=(
            "Cross-check OSM/MS footprint vs second basemap (Esri/Google) manually; "
            "widen ± if outlines disagree. v0 does not fetch dual tiles."
        ),
    )


_BUILDERS = {
    "basemap": lambda lat: basemap_calibrator(lat=lat),
    "car_sedan": lambda lat: car_sedan_calibrator(),
    "parking_stall": lambda lat: parking_stall_calibrator(),
    "dual_basemap": lambda lat: dual_basemap_calibrator(),
}


def build_scale_chain(
    names: Sequence[str],
    *,
    lat: float,
) -> list[Calibrator]:
    """Build ordered scale chain. Always includes basemap if missing."""
    ordered: list[str] = []
    for n in names:
        key = n.strip().lower()
        if key and key not in ordered:
            ordered.append(key)
    if "basemap" not in ordered:
        ordered.insert(0, "basemap")

    chain: list[Calibrator] = []
    for key in ordered:
        builder = _BUILDERS.get(key)
        if builder is None:
            raise ValueError(f"Unknown calibrator: {key}")
        chain.append(builder(lat))
    return chain


def combined_uncertainty_pct(chain: Sequence[Calibrator]) -> float:
    """Conservative combined ±% — max of chain (not RSS; fail closed)."""
    if not chain:
        return 100.0
    return max(c.uncertainty_pct for c in chain)


def parse_segment(spec: str) -> tuple[tuple[float, float], tuple[float, float]]:
    """Parse 'lat1,lon1,lat2,lon2' into two (lat, lon) points."""
    parts = [p.strip() for p in spec.replace(" ", "").split(",")]
    if len(parts) != 4:
        raise ValueError(
            "scale segment must be lat1,lon1,lat2,lon2 (four comma-separated numbers)"
        )
    lat1, lon1, lat2, lon2 = (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
    for lat in (lat1, lat2):
        if not -90 <= lat <= 90:
            raise ValueError(f"latitude out of range: {lat}")
    for lon in (lon1, lon2):
        if not -180 <= lon <= 180:
            raise ValueError(f"longitude out of range: {lon}")
    return (lat1, lon1), (lat2, lon2)


def ground_segment_calibrator(
    p1: tuple[float, float],
    p2: tuple[float, float],
    *,
    true_length_ft: float,
    pin_lat: float,
    pin_lon: float,
) -> tuple[Calibrator, float]:
    """Build calibrator from two map points + declared ground-truth length.

    Returns (calibrator, linear_scale_factor) where
    true_meters ≈ basemap_meters * linear_scale_factor.
    """
    from map_ruler.geometry import m_to_ft, path_length_m

    if true_length_ft <= 0:
        raise ValueError("true_length_ft must be positive")
    map_m = path_length_m([p1, p2], origin_lat=pin_lat, origin_lon=pin_lon)
    if map_m < 0.5:
        raise ValueError(
            f"scale segment too short on basemap ({map_m:.2f} m) — pick clearer points"
        )
    map_ft = m_to_ft(map_m)
    true_m = true_length_ft * 0.3048
    factor = true_m / map_m
    # Uncertainty: placement (~0.5 m each end) + residual CRS
    placement_m = 0.5
    placement_pct = (placement_m / map_m) * 100.0 * 2  # both ends
    unc = max(3.0, placement_pct + 1.0)
    delta_pct = abs(factor - 1.0) * 100.0
    cal = Calibrator(
        id="ground_segment",
        kind="ground_segment",
        meters_per_unit=factor,
        uncertainty_pct=round(unc, 1),
        notes=(
            f"Two-point ground truth: basemap={map_ft:.2f} ft, "
            f"declared={true_length_ft:.2f} ft, linear_scale_factor={factor:.4f} "
            f"(Δ {delta_pct:.1f}% vs basemap). "
            f"Lengths × factor; areas × factor². "
            f"p1={p1[0]:.6f},{p1[1]:.6f} p2={p2[0]:.6f},{p2[1]:.6f}."
        ),
    )
    return cal, factor


def apply_linear_scale(
    *,
    length_m: float | None,
    area_m2: float | None,
    factor: float,
) -> tuple[float | None, float | None]:
    """Scale length by factor; area by factor²."""
    lm = None if length_m is None else length_m * factor
    am = None if area_m2 is None else area_m2 * (factor**2)
    return lm, am
