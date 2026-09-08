# map-ruler

Measure roofs, fences, and driveways from OpenStreetMap footprints. Writes a sealed JSON record with a documented scale chain.

Not a cadastral survey. Roof print is not interior living area.

```
map-ruler measure --address "Ontario Legislative Building, 111 Wellesley Street West, Toronto, ON, Canada" \
  --feature roof --calibrators basemap,car_sedan --pretty

# Fence / driveway with user-supplied vertices (GeoJSON or [[lat,lon],...])
map-ruler measure --address "..." --feature fence \
  --vertices examples/ontario-demo-fence.json --pretty

# PNG overlay (rings from the JSON record — no second fetch when coords_latlon present)
map-ruler plot --address "Ontario Legislative Building, 111 Wellesley Street West, Toronto, ON, Canada" \
  --feature roof --out receipts/ontario-demo.png --receipt-out receipts/ontario-demo.json

# Two-point car (or any known length) scale check
map-ruler measure --address "..." --feature roof \
  --scale-segment "43.66250,-79.39120,43.66250,-79.39105" \
  --scale-length-ft 15.5 --pretty
```

**Refuses:** does not invent living area, does not claim survey-grade accuracy, and returns PARTIAL / ABSTAIN / ERROR instead of guessing.

Background and method: [docs/WHY.md](docs/WHY.md).

## Install

```bash
git clone https://github.com/cjchanh/map-ruler.git && cd map-ruler

# pipx (recommended)
bash scripts/install-pipx.sh
# or: pipx install --editable '.[plot]'

# pip editable
python3 -m pip install -e '.[plot]'

# no install
PYTHONPATH=. python3 -m map_ruler measure --address "..." --pretty
```

**Core measure:** zero required deps.  
**Plot + basemap:** `matplotlib` + `Pillow` (via `[plot]` extra).  
Network: Nominatim + Overpass (+ tile hosts when `--basemap`).

**Geocoding / Nominatim:** geocoding uses OSM Nominatim with an identifying
User-Agent and is throttled to 1 request/second per the Nominatim usage policy.
Heavy or automated use must use a self-hosted instance.

## CLI

```bash
# Roof / building footprint near address
python3 -m map_ruler measure \
  --address "Ontario Legislative Building, 111 Wellesley Street West, Toronto, ON, Canada" \
  --feature roof \
  --calibrators basemap,car_sedan \
  --out receipts/ontario-demo.json \
  --pretty

# Pin only
python3 -m map_ruler measure --lat 43.6626213 --lon -79.3910161 --feature building

# Fence / driveway — v0 returns PARTIAL + building context (no auto-trace yet)
python3 -m map_ruler measure --address "..." --feature fence
```

### Features

| Feature   | Behavior                                      |
|-----------|--------------------------------------------------|
| `roof` / `building` | Closest OSM footprint to pin; GLA band heuristic |
| `fence` / `driveway` | Without `--vertices`: PARTIAL context. With `--vertices`: CLEAN length (+ area if closed) |
| `parcel`  | Building context (parcel polygons later)         |
| any + `--vertices` | User-supplied path wins; seals length/area from file |

### Vertices file shapes

- GeoJSON `LineString` / `Polygon` / `Feature` (coordinates **lon,lat**)
- `[[lat, lon], ...]` JSON array
- `{"coordinates":[...], "order":"latlon"|"lonlat"}`

### Calibrators

| Id              | Role |
|-----------------|------|
| `basemap`       | Always on — local equirectangular EN (~2% for small spans) |
| `car_sedan`     | Protocol: 14.5–16.5 ft vehicle as image scale |
| `parking_stall` | Protocol: ~9×18 ft stall |
| `dual_basemap`  | Protocol: cross-check second imagery source |

Combined uncertainty = **max** of chain (fail-closed, not optimistic RSS).

## Record schema

See `schema/measure-testify-receipt-v1.json`.

Status enum: `CLEAN` | `PARTIAL` | `ABSTAIN` | `ERROR`.

Primary fields:

- `footprint_sqft` / `footprint_m2`  
- `gla_band_sqft` (0.85–0.95 × footprint, 1-story heuristic)  
- `scale_chain[]`  
- `polygon_sha256`  
- `receipt_sha256`  
- `maps` links (Google satellite, OSM, Earth)  

## Agent skill

An optional agent-skill wrapper (author tooling, kept outside this repo) can call map-ruler. The CLI documented above is the complete public interface — nothing in this repo depends on the skill wrapper.

## Plot

```bash
# True Microsoft/OSM footprints around address
python3 -m map_ruler plot \
  --address "Ontario Legislative Building, 111 Wellesley Street West, Toronto, ON, Canada" \
  --out receipts/ontario-demo-roof.png \
  --receipt-out receipts/ontario-demo-roof.json

# Satellite underlay
python3 -m map_ruler plot --receipt receipts/ontario-demo-roof.json \
  --basemap --basemap-source esri --out receipts/ontario-demo-sat.png

# Fence path on top of context (vertices required for path)
python3 -m map_ruler plot \
  --address "..." --feature fence \
  --vertices examples/ontario-demo-fence.json \
  --out receipts/fence.png
```

Plot needs `matplotlib` (+ `Pillow` for `--basemap`).

## Tests

```bash
git clone https://github.com/cjchanh/map-ruler.git && cd map-ruler
python3 -m unittest discover -s tests -v
```

Offline unit tests only. Live dogfood / plot need network (plot needs matplotlib).

## Dogfood

```bash
PYTHONPATH=. python3 -m map_ruler measure \
  --address "Ontario Legislative Building, 111 Wellesley Street West, Toronto, ON, Canada" \
  --feature roof --calibrators basemap,car_sedan \
  --out receipts/ontario-demo-roof.json --pretty
```

## License

MIT — see `LICENSE`.

## Disclaimer

Not a survey. Not legal property lines. Not assessor GLA.  
Use for local evidence, agent context, and open research.  
Field tape/laser upgrades authority — record it in the scale chain later.
