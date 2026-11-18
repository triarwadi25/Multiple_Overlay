# -*- coding: utf-8 -*-
"""Small dialogs used by the 'Configure...' button of the Processing dialog."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .engine import KIND_NAMES, geometry_kind


def run_dialog(dialog):
    """exec() on PyQt5/6 alike."""
    runner = getattr(dialog, "exec", None) or dialog.exec_
    return runner()


class FieldsDialog(QDialog):
    """Check the fields that should be kept."""

    def __init__(self, layer, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fields to keep - {}".format(layer.name()))
        self.resize(320, 400)

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

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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


class LayerSettingsDialog(QDialog):
    """Per-layer field prefix and fields to keep."""

    COL_LAYER, COL_GEOM, COL_PREFIX, COL_FIELDS = range(4)

    def __init__(self, layers, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Field prefix / fields to keep")
        self.resize(640, 360)
        self.layers = list(layers)
        self._fields = {}
        self._prefix_edits = {}

        layout = QVBoxLayout(self)
        info = QLabel(
            "Optional. Add a prefix to the field names of a layer and/or "
            "keep only some of its fields. Leave defaults to keep every "
            "field unchanged.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget(len(self.layers), 4)
        self.table.setHorizontalHeaderLabels(
            ["Layer", "Geometry", "Prefix", "Fields"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_LAYER, QHeaderView.Stretch)
        header.setSectionResizeMode(
            self.COL_GEOM, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_PREFIX, QHeaderView.Interactive)
        header.setSectionResizeMode(
            self.COL_FIELDS, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(self.COL_PREFIX, 120)
        layout.addWidget(self.table, 1)

        for row, layer in enumerate(self.layers):
            saved = settings.get(layer.id(), {}) or {}
            self._fields[layer.id()] = saved.get("fields")

            item = QTableWidgetItem(layer.name())
            item.setToolTip(layer.source())
            self.table.setItem(row, self.COL_LAYER, item)
            self.table.setItem(row, self.COL_GEOM, QTableWidgetItem(
                KIND_NAMES.get(geometry_kind(layer), "?")))

            edit = QLineEdit(saved.get("prefix", "") or "")
            edit.setPlaceholderText("no prefix")
            self._prefix_edits[layer.id()] = edit
            self.table.setCellWidget(row, self.COL_PREFIX, edit)

            button = QPushButton()
            button.clicked.connect(
                lambda checked=False, lyr=layer: self._choose_fields(lyr))
            self.table.setCellWidget(row, self.COL_FIELDS, button)
            self._update_button(layer)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if not self.layers:
            info.setText("Choose the input layers first, then reopen this "
                         "dialog.")

    def _row_of(self, layer):
        return self.layers.index(layer)

    def _update_button(self, layer):
        total = layer.fields().count()
        chosen = self._fields[layer.id()]
        kept = total if chosen is None else len(chosen)
        button = self.table.cellWidget(self._row_of(layer), self.COL_FIELDS)
        button.setText(
            "All fields ({})".format(total) if chosen is None
            else "{} of {} fields".format(kept, total))

    def _choose_fields(self, layer):
        dialog = FieldsDialog(layer, self._fields[layer.id()], self)
        if run_dialog(dialog):
            self._fields[layer.id()] = dialog.selected_fields()
            self._update_button(layer)

    def settings(self):
        """{layer id: {"prefix": str, "fields": list or None}} (non-default)."""
        result = {}
        for layer in self.layers:
            prefix = self._prefix_edits[layer.id()].text()
            fields = self._fields[layer.id()]
            if prefix or fields is not None:
                result[layer.id()] = {"prefix": prefix, "fields": fields}
        return result
