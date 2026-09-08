# Why map-ruler exists

Map UIs draw areas. They rarely defend scale or leave a checkable record.

`map-ruler` is a metrology brick:

1. **Geocode** (Nominatim) or accept user lat/lon
2. **Pull building footprints** (OSM Overpass; often Microsoft Building Footprints)
3. **Scale chain** — basemap CRS + optional car/parking/dual-basemap protocol
4. **Shoelace area** in local meters → sq ft
5. **Seal** `measure-testify/receipt/v1` with SHA-256

It reports CLEAN / PARTIAL / ABSTAIN / ERROR. It does not invent interior living area.

Not a cadastral survey. Roof print ≠ interior GLA.
