# map-ruler

**Open spatial measurements that testify.**

Scale chain → polygon → sealed receipt.  
Not a cadastral survey. Roof print ≠ interior GLA.

```
map-ruler measure --address "Ontario Legislative Building, 111 Wellesley Street West, Toronto, ON, Canada" \
  --feature roof --calibrators basemap,car_sedan --pretty

# Fence / driveway with operator vertices (GeoJSON or [[lat,lon],...])
map-ruler measure --address "..." --feature fence \
  --vertices examples/ontario-demo-fence.json --pretty

# PNG overlay (rings from receipt — no second fetch when coords_latlon present)
map-ruler plot --address "Ontario Legislative Building, 111 Wellesley Street West, Toronto, ON, Canada" \
  --feature roof --out receipts/ontario-demo.png --receipt-out receipts/ontario-demo.json

# Two-point car (or any known length) scale check
map-ruler measure --address "..." --feature roof \
  --scale-segment "43.66250,-79.39120,43.66250,-79.39105" \
  --scale-length-ft 15.5 --pretty
```

## Why

Map UIs draw areas. They rarely **defend scale** or leave a **receipt**.

`map-ruler` is the CDS metrology brick:

1. **Geocode** (Nominatim) or accept operator lat/lon  
2. **Pull building footprints** (OSM Overpass; often Microsoft Building Footprints)  
3. **Scale chain** — basemap CRS + optional car/parking/dual-basemap protocol  
4. **Shoelace area** in local meters → sq ft  
5. **Seal** `measure-testify/receipt/v1` with SHA-256  

Doctrine: *It doesn’t answer. It testifies.*

## Install

```bash
cd ~/Workspace/active/map-ruler
python3 -m pip install -e .
# or run without install:
PYTHONPATH=. python3 -m map_ruler measure --address "..." --pretty
```

No third-party Python deps. Needs network for Nominatim + Overpass.

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
| any + `--vertices` | Operator/agent path wins; seals length/area from file |

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

## Receipt schema

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

Grok: `~/.grok/skills/map-ruler/SKILL.md`  
Invoke when the operator wants roof/fence/driveway measure with a receipt.

## Plot

```bash
# True Microsoft/OSM footprints around address
python3 -m map_ruler plot \
  --address "Ontario Legislative Building, 111 Wellesley Street West, Toronto, ON, Canada" \
  --out receipts/ontario-demo-roof.png \
  --receipt-out receipts/ontario-demo-roof.json

# Fence path on top of context (vertices required for path)
python3 -m map_ruler plot \
  --address "..." --feature fence \
  --vertices examples/ontario-demo-fence.json \
  --out receipts/fence.png
```

Plot needs `matplotlib` (`pip install matplotlib`). Core measure stays dependency-free.

## Tests

```bash
cd ~/Workspace/active/map-ruler
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
Use for operator evidence, agent context, and open research.  
Field tape/laser upgrades authority — record it in the scale chain later.
