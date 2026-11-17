# -*- coding: utf-8 -*-
"""Shared helpers for Multiple Overlay Tools (QGIS 3.18+).

Design notes
------------
* A layer is only copied to a temporary (memory) layer when its attribute
  table has to change (field subset and/or prefix/de-duplication).
  "Selected features only" is handled with QgsProcessingFeatureSourceDefinition,
  so no copy is needed for it.
* Per-layer settings travel as a JSON list (one entry per input layer, same
  order as the LAYERS parameter):
      [{"selected_only": false, "prefix": "a_", "fields": ["id", "name"]}, ...]
  ``fields`` = null / missing keeps every field.
"""
import json

from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsMapLayer,
    QgsProcessingException,
    QgsProcessingFeatureSourceDefinition,
    QgsProcessingUtils,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis import processing

BATCH_SIZE = 2000
KIND_NAMES = {0: "point", 1: "line", 2: "polygon"}


# ---------------------------------------------------------------- basics --

def geometry_kind(layer):
    """0 = point, 1 = line, 2 = polygon, None = no geometry."""
    gtype = layer.geometryType()
    if gtype == QgsWkbTypes.PointGeometry:
        return 0
    if gtype == QgsWkbTypes.LineGeometry:
        return 1
    if gtype == QgsWkbTypes.PolygonGeometry:
        return 2
    return None


class LayerConfig(object):
    """Per-layer settings."""

    def __init__(self, selected_only=False, prefix="", fields=None):
        self.selected_only = bool(selected_only)
        self.prefix = prefix or ""
        self.fields = fields  # None = keep all fields


def parse_config(text, count):
    """Parse the CONFIG JSON into ``count`` LayerConfig objects."""
    if text is None or not str(text).strip():
        return [LayerConfig() for _ in range(count)]

    try:
        data = json.loads(text)
    except ValueError as exc:
        raise QgsProcessingException(
            "Per-layer settings are not valid JSON: {}".format(exc))

    if isinstance(data, dict):
        data = data.get("layers")

    if not isinstance(data, list) or len(data) != count:
        raise QgsProcessingException(
            "Per-layer settings must be a JSON list with exactly one entry "
            "per input layer ({} expected).".format(count))

    configs = []
    for item in data:
        if not isinstance(item, dict):
            raise QgsProcessingException(
                "Every per-layer setting must be a JSON object.")
        fields = item.get("fields")
        if fields is not None:
            if not isinstance(fields, list):
                raise QgsProcessingException(
                    "'fields' must be a list of field names or null.")
            fields = [str(name) for name in fields]
        configs.append(LayerConfig(
            item.get("selected_only", False),
            str(item.get("prefix") or ""),
            fields,
        ))
    return configs


def unique_name(name, used):
    """Return ``name`` (or name_1, name_2 ...) not yet in ``used``."""
    candidate = name
    counter = 1
    while candidate.lower() in used:
        candidate = "{}_{}".format(name, counter)
        counter += 1
    used.add(candidate.lower())
    return candidate


def plan_fields(layer, config, used, keep_attributes=True):
    """Decide which fields survive and what they are called.

    Returns (indexes, names). Names are prefixed and unique across every
    layer that shares the ``used`` set.
    """
    indexes = []
    names = []
    if not keep_attributes:
        return indexes, names

    wanted = None if config.fields is None else set(config.fields)
    for index, field in enumerate(layer.fields()):
        if wanted is not None and field.name() not in wanted:
            continue
        indexes.append(index)
        names.append(unique_name(config.prefix + field.name(), used))
    return indexes, names


# ------------------------------------------------------ child algorithms --

def run_child(algorithm, parameters, context, feedback):
    return processing.run(
        algorithm,
        parameters,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )


def as_layer(value, context):
    """Resolve an algorithm result (layer object, id or path) to a layer."""
    if isinstance(value, QgsMapLayer):
        return value
    layer = context.getMapLayer(value)
    if layer is None:
        layer = QgsProcessingUtils.mapLayerFromString(value, context)
    if layer is None:
        raise QgsProcessingException(
            "Could not retrieve intermediate result '{}'.".format(value))
    return layer


def source_reference(layer, selected_only):
    """Parameter value for a child algorithm input.

    A plain layer, or a feature-source definition restricted to the
    selection (no copy of the data is made).
    """
    if selected_only:
        if layer.selectedFeatureCount() == 0:
            raise QgsProcessingException(
                "Layer '{}' has no selected features, but 'selected "
                "features only' was requested.".format(layer.name()))
        return QgsProcessingFeatureSourceDefinition(layer.id(), True)
    return layer


def fix_geometries(reference, context, feedback):
    """Run native:fixgeometries; returns the id of the temporary result."""
    result = run_child(
        "native:fixgeometries",
        {"INPUT": reference, "OUTPUT": "memory:"},
        context,
        feedback,
    )
    return as_layer(result["OUTPUT"], context).id()


# ------------------------------------------------------- layer preparing --

def _new_memory_layer(layer):
    wkb = layer.wkbType()
    candidates = [
        QgsWkbTypes.displayString(wkb),
        QgsWkbTypes.displayString(QgsWkbTypes.flatType(wkb)),
    ]
    for geometry in candidates:
        memory = QgsVectorLayer(geometry, "mot_" + layer.name(), "memory")
        if memory.isValid():
            # setCrs also works for custom CRSs without an authid.
            memory.setCrs(layer.crs())
            return memory
    raise QgsProcessingException(
        "Could not create a temporary layer for '{}'.".format(layer.name()))


def copy_layer(layer, selected_only, indexes, names, context, feedback):
    """Copy a layer to a temporary layer with a chosen, renamed field set.

    Returns the id of the temporary layer (kept in the context's store).
    """
    memory = _new_memory_layer(layer)
    source_fields = layer.fields()

    new_fields = []
    for index, name in zip(indexes, names):
        field = QgsField(source_fields.at(index))
        field.setName(name)
        new_fields.append(field)

    provider = memory.dataProvider()
    if new_fields:
        provider.addAttributes(new_fields)
        memory.updateFields()

    request = QgsFeatureRequest()
    if selected_only:
        request.setFilterFids(list(layer.selectedFeatureIds()))
        total = layer.selectedFeatureCount()
    else:
        total = layer.featureCount()

    batch = []
    done = 0
    for feature in layer.getFeatures(request):
        if feedback.isCanceled():
            raise QgsProcessingException("Canceled.")

        new_feature = QgsFeature(memory.fields())
        new_feature.setGeometry(feature.geometry())
        attributes = feature.attributes()
        new_feature.setAttributes([attributes[i] for i in indexes])
        batch.append(new_feature)

        if len(batch) >= BATCH_SIZE:
            _flush(provider, batch, layer)
            batch = []

        done += 1
        if total:
            feedback.setProgress(done * 100.0 / total)

    if batch:
        _flush(provider, batch, layer)

    memory.updateExtents()
    context.temporaryLayerStore().addMapLayer(memory)
    return memory.id()


def _flush(provider, batch, layer):
    ok, _ = provider.addFeatures(batch)
    if not ok:
        raise QgsProcessingException(
            "Failed to copy features from '{}'.".format(layer.name()))


def prepare_layer(layer, config, used, context, feedback, fix=False):
    """Return a reference to ``layer`` ready for overlay processing.

    Applies (in this order): field selection / prefix / unique names
    (copy only if needed), selected-features-only, geometry fixing.
    """
    indexes, names = plan_fields(layer, config, used)
    original = [field.name() for field in layer.fields()]

    if names != original:
        reference = copy_layer(
            layer, config.selected_only, indexes, names, context, feedback)
    else:
        reference = source_reference(layer, config.selected_only)

    if fix and geometry_kind(layer) in (1, 2):
        reference = fix_geometries(reference, context, feedback)
    return reference


def prepare_overlay(layer, selected_only, fix, context, feedback):
    """Like prepare_layer for layers whose attributes are not used."""
    reference = source_reference(layer, selected_only)
    if fix and geometry_kind(layer) in (1, 2):
        reference = fix_geometries(reference, context, feedback)
    return reference
