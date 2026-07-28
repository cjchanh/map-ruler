# Changelog

## 0.4.0

- Store `coords_latlon` rings on candidates/primary (plot without Overpass re-fetch)
- `--scale-segment lat1,lon1,lat2,lon2` + `--scale-length-ft` two-point ground calibration
- Linear scale factor: lengths × f, areas × f²; `ground_segment` in scale_chain
- `AGENTS.md` for agent operators
- Offline tests for scale segment + rings

## 0.3.0

- `map-ruler plot` — PNG overlay (true OSM footprints or receipt + vertices)
- `--true-footprints` for exact building rings
- `--receipt-out` to seal JSON beside PNG

## 0.2.0

- `--vertices` GeoJSON / latlon lists for fence, driveway, roof
- Length + optional closed-ring area in primary
- Offline vertex unit tests

## 0.1.0

- Initial measure-testify CLI, schema, scale chain, Ontario public demo dogfood
