# Multiple Overlay Tools (QGIS 3.18+)

Overlay many layers in one step: **Intersection**, **Union**, **Erase** and **Clip**.

Open them from *Vector > Overlay Multiple* or the Processing Toolbox. They use the standard Processing dialog: tick the input layers, tick the layers that should use *selected features only*, press **Configure...** for a per-layer field prefix / fields to keep, and choose the output (temporary layer, file, GeoPackage, database, skip).

Scripts and models can pass the per-layer prefix / fields in `CONFIG` as JSON keyed by layer id or name:

```json
{"Roads": {"prefix": "r_", "fields": ["id", "name"]},
 "Parcels": {"prefix": "p_"}}
```

`fields: null` (or missing) keeps all fields.

| Tool | Layers | Notes |
|------|--------|-------|
| Intersection Multiple | points / lines / polygons, mixed | result has the lowest geometry dimension |
| Union Multiple | all points, or all lines, or all polygons | QGIS union needs identical types |
| Erase Multiple | layer to erase from: any; erase layers: polygons | difference repeated per erase layer |
| Clip Multiple | any, clipped by one polygon layer | one file per layer into the output folder |

Add a LICENSE file of your choice (QGIS plugins are normally GPL-2.0-or-later compatible).
