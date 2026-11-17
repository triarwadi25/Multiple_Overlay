# Multiple Overlay Tools (QGIS 3.18+)

Overlay many layers in one step: **Intersection**, **Union**, **Erase** and **Clip**.

* Menu: *Vector > Overlay Multiple* (dialog with per-layer *selected only*, *prefix*, *fields*).
* Processing Toolbox: *Multiple Overlay Tools*. Per-layer settings can be passed as JSON in the advanced `CONFIG` parameter:

```json
[{"selected_only": true, "prefix": "a_", "fields": ["id", "name"]},
 {"prefix": "b_"}]
```

One entry per input layer, same order as `LAYERS`. `fields: null` keeps all fields.

| Tool | Layers | Notes |
|------|--------|-------|
| Intersection Multiple | points / lines / polygons, mixed | result has the lowest geometry dimension |
| Union Multiple | all points, or all lines, or all polygons | QGIS union needs identical types |
| Erase Multiple | 1st: any; others: polygons | difference repeated per erase layer |
| Clip Multiple | any, clipped by one polygon layer | temporary layers or output folder |

Add a LICENSE file of your choice (QGIS plugins are normally GPL-2.0-or-later compatible).
