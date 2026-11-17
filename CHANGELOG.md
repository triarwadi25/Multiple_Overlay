# Changelog

## 1.1.0
- New: **Erase Multiple** (difference with several polygon layers).
- New: Intersection Multiple accepts points, lines and polygons (mixed); Union Multiple accepts points, lines or polygons (all the same type).
- New: per-layer *selected features only*, *field selection* and *prefix* (menu dialog, or `CONFIG` JSON in the Processing Toolbox).
- New: *Fix invalid geometries* option.
- New: QGIS 3.18+ support.
- Fix: Clip Multiple no longer touches `QgsProject` from inside the algorithm; supports an output folder (GeoPackage / Shapefile) or temporary layers.
- Improved: layers are copied to memory only when the attribute table has to change; custom CRSs are handled.
- Improved: all messages in English, help texts, tags, parameter validation.

## 1.0.0
- Intersection Multiple, Union Multiple, Clip Multiple.
