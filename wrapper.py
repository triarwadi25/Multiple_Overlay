# -*- coding: utf-8 -*-
"""'Configure...' widget for the CONFIG parameter of the Processing dialog.

Best effort UI: if anything about the Processing widget API differs in a
QGIS version, the parameter silently stays a plain JSON text box.
"""
import json

from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)
from qgis.core import (
    QgsMapLayer,
    QgsProcessingFeatureSourceDefinition,
    QgsProject,
    QgsVectorLayer,
)
from processing.gui.wrappers import WidgetWrapper

from .engine import geometry_kind, log_problem
from .widgets import LayerSettingsDialog, run_dialog


def _resolve_layer(item):
    if isinstance(item, QgsProcessingFeatureSourceDefinition):
        try:
            item = item.source.staticValue()
        except Exception as exc:  # noqa: BLE001
            log_problem("Could not read layer source: {}".format(exc))
            return None
    if isinstance(item, QgsMapLayer):
        return item
    if isinstance(item, str):
        project = QgsProject.instance()
        layer = project.mapLayer(item)
        if layer is None:
            named = project.mapLayersByName(item)
            layer = named[0] if named else None
        if layer is None:
            for candidate in project.mapLayers().values():
                if candidate.source() == item:
                    return candidate
        return layer
    return None


def _is_usable(layer):
    return isinstance(layer, QgsVectorLayer) and geometry_kind(layer) is not None


class SettingsWrapper(WidgetWrapper):
    """Button that opens a per-layer prefix / fields table."""

    LAYER_PARAMS = ("LAYERS",)

    def createWidget(self, **kwargs):
        self._settings = {}
        self._wrappers = []
        self._plain = None
        try:
            if getattr(self, "dialogType", "standard") != "standard":
                raise RuntimeError("plain text in batch / modeler")
            holder = QWidget()
            layout = QHBoxLayout(holder)
            layout.setContentsMargins(0, 0, 0, 0)
            self._summary = QLabel()
            self._button = QPushButton("Configure...")
            self._button.clicked.connect(self._configure)
            layout.addWidget(self._summary, 1)
            layout.addWidget(self._button)
            self._refresh_summary()
            return holder
        except Exception as exc:  # noqa: BLE001
            log_problem("Using plain text for CONFIG: {}".format(exc))
            self._plain = QLineEdit()
            self._plain.setPlaceholderText(
                'optional JSON, e.g. {"Layer name": {"prefix": "a_"}}')
            return self._plain

    def postInitialize(self, wrappers):
        self._wrappers = list(wrappers)

    # ---- value ------------------------------------------------------
    def value(self):
        if getattr(self, "_plain", None) is not None:
            return self._plain.text()
        settings = getattr(self, "_settings", {})
        return json.dumps(settings) if settings else ""

    def setValue(self, value):
        text = "" if value is None else str(value)
        if getattr(self, "_plain", None) is not None:
            self._plain.setText(text)
            return
        self._settings = {}
        if text.strip():
            try:
                data = json.loads(text)
            except ValueError:
                data = None
            if isinstance(data, dict):
                self._settings = {
                    key: entry for key, entry in data.items()
                    if isinstance(entry, dict)
                }
        self._refresh_summary()

    # ---- helpers ----------------------------------------------------
    def _refresh_summary(self):
        count = len(self._settings)
        if count:
            self._summary.setText("{} layer(s) customised".format(count))
        else:
            self._summary.setText("Default (all fields, no prefix)")

    def _wrapper_name(self, wrapper):
        definition = getattr(wrapper, "parameterDefinition", None)
        if callable(definition):
            return definition().name()
        return wrapper.param.name()

    def _layer_values(self, wrapper):
        """Raw value of a layer parameter, or None if unavailable."""
        try:
            if self._wrapper_name(wrapper) not in self.LAYER_PARAMS:
                return None
            return wrapper.parameterValue()
        except Exception as exc:  # noqa: BLE001
            log_problem("Could not read a parameter value: {}".format(exc))
            return None

    def _current_layers(self):
        found = []
        for wrapper in self._wrappers:
            value = self._layer_values(wrapper)
            if value is None:
                continue
            items = value if isinstance(value, (list, tuple)) else [value]
            for item in items:
                layer = _resolve_layer(item)
                if _is_usable(layer) and all(
                        layer.id() != other.id() for other in found):
                    found.append(layer)
        return found

    def _configure(self):
        layers = self._current_layers()
        dialog = LayerSettingsDialog(layers, self._settings, self.widget)
        if run_dialog(dialog):
            listed = set(layer.id() for layer in layers)
            merged = {
                key: entry for key, entry in self._settings.items()
                if key not in listed
            }
            merged.update(dialog.settings())
            self._settings = merged
            self._refresh_summary()


class IntersectionSettingsWrapper(SettingsWrapper):
    LAYER_PARAMS = ("LAYERS",)


class UnionSettingsWrapper(SettingsWrapper):
    LAYER_PARAMS = ("LAYERS",)


class EraseSettingsWrapper(SettingsWrapper):
    LAYER_PARAMS = ("INPUT",)
