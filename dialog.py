# -*- coding: utf-8 -*-
"""Menu dialog: per-layer selected-only, prefix and field selection."""
import json
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsMapLayerProxyModel,
    QgsProcessingFeatureSourceDefinition,
    QgsProcessingFeedback,
    QgsProcessingOutputLayerDefinition,
    QgsProject,
)
from qgis.gui import QgsMapLayerComboBox
from qgis import processing

from .engine import KIND_NAMES, geometry_kind

# mode -> settings
MODES = {
    "intersection": {
        "title": "Intersection Multiple",
        "algorithm": "multiple_overlay_tools:intersection_multiple",
        "min_layers": 2,
        "hint": "Add two or more layers (points, lines and polygons may be "
                "mixed). Result geometry = lowest dimension.",
        "output_name": "Intersection Multiple",
    },
    "union": {
        "title": "Union Multiple",
        "algorithm": "multiple_overlay_tools:union_multiple",
        "min_layers": 2,
        "hint": "Add two or more layers of the SAME geometry type "
                "(all points, all lines or all polygons).",
        "output_name": "Union Multiple",
    },
    "erase": {
        "title": "Erase Multiple",
        "algorithm": "multiple_overlay_tools:erase_multiple",
        "min_layers": 2,
        "hint": "The FIRST row is the layer to erase from (any geometry). "
                "All other rows are polygon layers used to erase.",
        "output_name": "Erase Multiple",
    },
    "clip": {
        "title": "Clip Multiple",
        "algorithm": "multiple_overlay_tools:clip_multiple",
        "min_layers": 1,
        "hint": "Add the layers to clip, then choose the polygon clip layer.",
        "output_name": "Clip Multiple",
    },
}

COL_ROLE, COL_LAYER, COL_GEOM, COL_SEL, COL_PREFIX, COL_FIELDS = range(6)


class FieldsDialog(QDialog):
    """Check the fields that should be kept."""

    def __init__(self, layer, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fields to keep - {}".format(layer.name()))
        self.resize(320, 380)

        layout = QVBoxLayout(self)
        self.list = QListWidget()
        for field in layer.fields():
            item = QListWidgetItem(field.name())
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            keep = selected is None or field.name() in selected
            item.setCheckState(Qt.Checked if keep else Qt.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list)

        row = QHBoxLayout()
        all_btn = QPushButton("Select all")
        none_btn = QPushButton("Select none")
        all_btn.clicked.connect(lambda: self._set_all(Qt.Checked))
        none_btn.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        row.addWidget(all_btn)
        row.addWidget(none_btn)
        row.addStretch()
        layout.addLayout(row)

        buttons = QHBoxLayout()
        buttons.addStretch()
        ok = QPushButton("OK")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _set_all(self, state):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)

    def selected_fields(self):
        """None when every field is checked, otherwise the checked names."""
        names = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.Checked:
                names.append(item.text())
        return None if len(names) == self.list.count() else names


class DialogFeedback(QgsProcessingFeedback):
    """Feedback that writes to the dialog log and progress bar."""

    def __init__(self, log, progress):
        super().__init__()
        self._log = log
        self.progressChanged.connect(progress)

    def pushInfo(self, info):
        self._log(info)
        super().pushInfo(info)

    def pushWarning(self, warning):
        self._log("WARNING: {}".format(warning))
        super().pushWarning(warning)

    def reportError(self, error, fatalError=False):
        self._log("ERROR: {}".format(error))
        super().reportError(error, fatalError)


class OverlayDialog(QDialog):

    def __init__(self, iface, mode, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.mode = mode
        self.cfg = MODES[mode]
        self.rows = []  # dicts: layer_id, selected_only, prefix, fields
        self.feedback = None
        self.running = False

        self.setWindowTitle(self.cfg["title"])
        self.resize(820, 640)
        self._build_ui()

    # ------------------------------------------------------------- UI --
    def _build_ui(self):
        layout = QVBoxLayout(self)

        hint = QLabel(self.cfg["hint"])
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # layer picker
        picker = QHBoxLayout()
        self.combo = QgsMapLayerComboBox()
        self.combo.setFilters(QgsMapLayerProxyModel.HasGeometry)
        add_btn = QPushButton("Add layer")
        add_btn.clicked.connect(self._add_current)
        picker.addWidget(self.combo, 1)
        picker.addWidget(add_btn)
        layout.addLayout(picker)

        # table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Role", "Layer", "Geometry", "Selected only", "Prefix",
             "Fields"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_LAYER, QHeaderView.Stretch)
        for col in (COL_ROLE, COL_GEOM, COL_SEL, COL_PREFIX, COL_FIELDS):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        tools = QHBoxLayout()
        up = QPushButton("Move up")
        down = QPushButton("Move down")
        remove = QPushButton("Remove")
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        remove.clicked.connect(self._remove)
        for button in (up, down, remove):
            tools.addWidget(button)
        tools.addStretch()
        layout.addLayout(tools)

        # clip layer (clip mode only)
        if self.mode == "clip":
            box = QGroupBox("Clip layer (polygon)")
            row = QHBoxLayout(box)
            self.clip_combo = QgsMapLayerComboBox()
            self.clip_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
            self.clip_selected = QCheckBox("Selected features only")
            row.addWidget(self.clip_combo, 1)
            row.addWidget(self.clip_selected)
            layout.addWidget(box)

        # options
        self.fix_check = QCheckBox("Fix invalid geometries before processing")
        self.fix_check.setChecked(True)
        layout.addWidget(self.fix_check)

        # output
        out_row = QHBoxLayout()
        if self.mode == "clip":
            out_row.addWidget(QLabel("Output folder (empty = temporary):"))
            self.format_combo = QComboBox()
            self.format_combo.addItems(["GeoPackage (.gpkg)", "Shapefile (.shp)"])
        else:
            out_row.addWidget(QLabel("Output file (empty = temporary):"))
        self.output_edit = QLineEdit()
        browse = QPushButton("...")
        browse.clicked.connect(self._browse)
        out_row.addWidget(self.output_edit, 1)
        if self.mode == "clip":
            out_row.addWidget(self.format_combo)
        out_row.addWidget(browse)
        layout.addLayout(out_row)

        # log + progress
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        layout.addWidget(self.log)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.run_btn = QPushButton("Run")
        self.cancel_btn = QPushButton("Cancel run")
        self.cancel_btn.setEnabled(False)
        self.close_btn = QPushButton("Close")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn.clicked.connect(self._cancel)
        self.close_btn.clicked.connect(self.close)
        for button in (self.run_btn, self.cancel_btn, self.close_btn):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        # start with the layers selected in the layer tree
        for layer in self.iface.layerTreeView().selectedLayers():
            if hasattr(layer, "fields") and geometry_kind(layer) is not None:
                self._add_layer(layer)

    # ----------------------------------------------------- table state --
    def _layer(self, row):
        return QgsProject.instance().mapLayer(row["layer_id"])

    def _add_current(self):
        layer = self.combo.currentLayer()
        if layer is not None:
            self._add_layer(layer)

    def _add_layer(self, layer):
        self._sync_state()
        self.rows.append({
            "layer_id": layer.id(),
            "selected_only": False,
            "prefix": "",
            "fields": None,
        })
        self._rebuild()

    def _current_index(self):
        return self.table.currentRow()

    def _remove(self):
        index = self._current_index()
        if 0 <= index < len(self.rows):
            self._sync_state()
            del self.rows[index]
            self._rebuild()

    def _move(self, delta):
        index = self._current_index()
        target = index + delta
        if 0 <= index < len(self.rows) and 0 <= target < len(self.rows):
            self._sync_state()
            self.rows[index], self.rows[target] = (
                self.rows[target], self.rows[index])
            self._rebuild()
            self.table.selectRow(target)

    def _sync_state(self):
        """Copy widget values back into self.rows."""
        for i, row in enumerate(self.rows):
            check = self._checkbox(i)
            prefix = self.table.cellWidget(i, COL_PREFIX)
            if check is not None:
                row["selected_only"] = check.isChecked()
            if prefix is not None:
                row["prefix"] = prefix.text()

    def _uses_attributes(self, index):
        """Whether prefix/fields apply to this row."""
        if self.mode == "clip":
            return False
        if self.mode == "erase":
            return index == 0
        return True

    def _role(self, index):
        if self.mode == "erase":
            return "Erase from" if index == 0 else "Erase with"
        if self.mode == "clip":
            return "Clip input"
        return "Input"

    def _rebuild(self):
        self.rows = [r for r in self.rows if self._layer(r) is not None]
        self.table.setRowCount(len(self.rows))

        for i, row in enumerate(self.rows):
            layer = self._layer(row)

            self.table.setItem(i, COL_ROLE, QTableWidgetItem(self._role(i)))
            name_item = QTableWidgetItem(layer.name())
            name_item.setToolTip(layer.source())
            self.table.setItem(i, COL_LAYER, name_item)
            self.table.setItem(i, COL_GEOM, QTableWidgetItem(
                KIND_NAMES.get(geometry_kind(layer), "?")))

            selected_count = layer.selectedFeatureCount()
            check = QCheckBox("({})".format(selected_count))
            check.setEnabled(selected_count > 0)
            check.setChecked(row["selected_only"] and selected_count > 0)
            if selected_count == 0:
                check.setToolTip("This layer has no selected features.")
            self.table.setCellWidget(i, COL_SEL, self._centered(check))

            prefix = QLineEdit(row["prefix"])
            prefix.setPlaceholderText("none")
            prefix.setEnabled(self._uses_attributes(i))
            self.table.setCellWidget(i, COL_PREFIX, prefix)

            total = layer.fields().count()
            kept = total if row["fields"] is None else len(row["fields"])
            fields_btn = QPushButton("{} of {} fields".format(kept, total))
            fields_btn.setEnabled(self._uses_attributes(i))
            fields_btn.clicked.connect(
                lambda checked=False, idx=i: self._choose_fields(idx))
            self.table.setCellWidget(i, COL_FIELDS, fields_btn)

    @staticmethod
    def _centered(widget):
        holder = QWidget()
        box = QHBoxLayout(holder)
        box.setContentsMargins(4, 0, 4, 0)
        box.setAlignment(Qt.AlignCenter)
        box.addWidget(widget)
        # keep a reference so the check box stays reachable through the holder
        holder.checkbox = widget
        return holder

    def _choose_fields(self, index):
        self._sync_state()
        row = self.rows[index]
        layer = self._layer(row)
        if layer is None:
            return
        dialog = FieldsDialog(layer, row["fields"], self)
        runner = getattr(dialog, "exec", None) or dialog.exec_
        if runner():
            row["fields"] = dialog.selected_fields()
            self._rebuild()

    def _checkbox(self, index):
        holder = self.table.cellWidget(index, COL_SEL)
        return getattr(holder, "checkbox", None)

    # -------------------------------------------------------- output ----
    def _browse(self):
        if self.mode == "clip":
            path = QFileDialog.getExistingDirectory(
                self, "Output folder", self.output_edit.text())
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Output file", self.output_edit.text(),
                "GeoPackage (*.gpkg);;Shapefile (*.shp)")
        if path:
            self.output_edit.setText(path)

    # ----------------------------------------------------------- run ----
    def _write_log(self, text):
        self.log.appendPlainText(text)
        QApplication.processEvents()

    def _set_progress(self, value):
        self.progress.setValue(int(value))
        QApplication.processEvents()

    def _build_parameters(self):
        self._sync_state()

        layers = []
        config = []
        for i, row in enumerate(self.rows):
            layer = self._layer(row)
            if layer is None:
                raise ValueError("A layer was removed from the project.")
            layers.append(layer)
            uses = self._uses_attributes(i)
            config.append({
                "selected_only": bool(row["selected_only"]),
                "prefix": row["prefix"] if uses else "",
                "fields": row["fields"] if uses else None,
            })

        if len(layers) < self.cfg["min_layers"]:
            raise ValueError("Add at least {} layer(s).".format(
                self.cfg["min_layers"]))

        parameters = {
            "LAYERS": [layer.id() for layer in layers],
            "CONFIG": json.dumps(config),
            "FIX_GEOMETRIES": self.fix_check.isChecked(),
        }

        output = self.output_edit.text().strip()

        if self.mode == "clip":
            clip = self.clip_combo.currentLayer()
            if clip is None:
                raise ValueError("Choose a clip layer.")
            parameters["CLIP"] = QgsProcessingFeatureSourceDefinition(
                clip.id(), self.clip_selected.isChecked())
            parameters["OUTPUT_FORMAT"] = self.format_combo.currentIndex()
            if output:
                parameters["OUTPUT_FOLDER"] = output
        else:
            if output and os.path.exists(output):
                answer = QMessageBox.question(
                    self, self.cfg["title"],
                    "'{}' already exists. Overwrite it?".format(output))
                if answer != QMessageBox.Yes:
                    raise ValueError("Canceled.")
            definition = QgsProcessingOutputLayerDefinition(
                output if output else "memory:", QgsProject.instance())
            definition.destinationName = self.cfg["output_name"]
            parameters["OUTPUT"] = definition

        return parameters

    def _run(self):
        try:
            parameters = self._build_parameters()
        except ValueError as exc:
            if str(exc) != "Canceled.":
                QMessageBox.warning(self, self.cfg["title"], str(exc))
            return

        self.log.clear()
        self.progress.setValue(0)
        self._set_running(True)
        self.feedback = DialogFeedback(self._write_log, self._set_progress)

        try:
            result = processing.runAndLoadResults(
                self.cfg["algorithm"], parameters, feedback=self.feedback)
            if result is None:
                self._write_log("The algorithm did not finish. See messages "
                                "above.")
            elif self.feedback.isCanceled():
                self._write_log("Canceled.")
            else:
                self._write_log("Done.")
                self.progress.setValue(100)
        except Exception as exc:  # noqa: BLE001 - show any failure to the user
            self._write_log("ERROR: {}".format(exc))
            QMessageBox.critical(self, self.cfg["title"], str(exc))
        finally:
            self._set_running(False)

    def _cancel(self):
        if self.feedback is not None:
            self.feedback.cancel()

    def _set_running(self, running):
        self.running = running
        self.run_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.close_btn.setEnabled(not running)

    def closeEvent(self, event):
        if self.running:
            event.ignore()
        else:
            super().closeEvent(event)
