# Changelog

## 1.1.0
- New: **Erase Multiple** (difference with several polygon layers).
- New: Intersection Multiple accepts points, lines and polygons (mixed); Union Multiple accepts points, lines or polygons (all the same type).
- New: per-layer *selected features only* (checkbox list), *field selection* and *prefix* (**Configure...** button, or `CONFIG` JSON in scripts/models).
- New: standard Processing output chooser (temporary layer, save to file / GeoPackage / database, skip).
- New: *Fix invalid geometries* option.
- New: QGIS 3.18+ support.
- Fix: Clip Multiple no longer touches `QgsProject` from inside the algorithm; writes one file per layer to an output folder (temporary folder or directory; GeoPackage / Shapefile).
- Improved: layers are copied to memory only when the attribute table has to change; custom CRSs are handled.
- Improved: all messages in English, help texts, tags, parameter validation.

## 1.0.0
- Intersection Multiple, Union Multiple, Clip Multiple.
