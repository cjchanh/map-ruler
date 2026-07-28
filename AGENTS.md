# AGENTS.md — map-ruler

Open spatial **measure-testify** tool (CDS).  
Doctrine: scale chain → polygon → sealed receipt. Footprint ≠ GLA. Not a survey.

## Layout

| Path | Role |
|------|------|
| `map_ruler/` | Library + CLI |
| `schema/measure-testify-receipt-v1.json` | Receipt contract |
| `tests/` | Offline unit tests |
| `examples/` | Sample vertices |
| `receipts/` | Dogfood outputs (ok to commit examples) |
| `~/.grok/skills/map-ruler/` | Grok skill (user scope) |

## Commands

```bash
cd ~/Workspace/active/map-ruler
PYTHONPATH=. python3 -m map_ruler measure --address "..." --feature roof --pretty
PYTHONPATH=. python3 -m map_ruler measure --feature fence --vertices path.json --lat X --lon Y
PYTHONPATH=. python3 -m map_ruler measure --address "..." --scale-segment "lat1,lon1,lat2,lon2" --scale-length-ft 15.5
PYTHONPATH=. python3 -m map_ruler plot --address "..." --out out.png --receipt-out out.json
python3 -m unittest discover -s tests -v
```

## Invariants

1. **Fail-closed** — ERROR/ABSTAIN/PARTIAL are first-class; never invent GLA.
2. **Scale chain always present** — basemap minimum; ground_segment when two-point cal given.
3. **Rings in receipt** (`coords_latlon`) by default so plot does not re-fetch.
4. **No secrets / no push of private addresses** in public remotes without operator review.
5. **No AI attribution** in commits.

## Blast radius

- Reversible local: edit, test, commit in this repo.
- Network: Nominatim + Overpass + optional Toronto GIS parcels + basemap tiles.
- Irreversible: `git push` / public GitHub — **operator must explicitly request push**; default is local only.
- **Never commit private residential addresses or home satellite dogfood** — public demo is Ontario civic site only (`examples/DEMO_ADDRESS.md`).

## Install for agents

```bash
bash ~/Workspace/active/map-ruler/scripts/install-pipx.sh
# or: PYTHONPATH=~/Workspace/active/map-ruler python3 -m map_ruler ...
```

## Next product bricks

- County GIS parcel rings
- Auto car detection (optional; not default)
- Public GitHub: https://github.com/cjchanh/map-ruler
