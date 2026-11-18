# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication
from qgis import processing

from .provider import MultipleOverlayProvider

ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")

# (algorithm name, menu text, tooltip, icon)
ACTIONS = [
    ("intersection_multiple", "Intersection Multiple",
     "Intersect several layers (points, lines, polygons)",
     "intersection.svg"),
    ("union_multiple", "Union Multiple",
     "Union of several layers of the same geometry type", "union.svg"),
    ("erase_multiple", "Erase Multiple",
     "Erase one layer with several polygon layers", "erase.svg"),
    ("clip_multiple", "Clip Multiple",
     "Clip several layers with one polygon layer", "clip.svg"),
]


class MultipleOverlayToolsPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.menu = None
        self.actions = []

    def initGui(self):
        self.provider = MultipleOverlayProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

        self.menu = self.iface.vectorMenu().addMenu(
            QIcon(os.path.join(ICON_DIR, "overlay_multiple.svg")),
            "Overlay Multiple",
        )

        for algorithm, text, tooltip, icon in ACTIONS:
            action = QAction(
                QIcon(os.path.join(ICON_DIR, icon)),
                text,
                self.iface.mainWindow(),
            )
            action.setToolTip(tooltip)
            action.triggered.connect(
                lambda checked=False, a=algorithm: self.run_algorithm(a))
            self.menu.addAction(action)
            self.actions.append(action)

    def run_algorithm(self, algorithm):
        try:
            processing.execAlgorithmDialog(
                "multiple_overlay_tools:" + algorithm)
        except Exception as exc:  # noqa: BLE001
            self.iface.messageBar().pushCritical(
                "Multiple Overlay Tools", str(exc))

    def unload(self):
        if self.menu:
            self.iface.vectorMenu().removeAction(self.menu.menuAction())
            self.menu.deleteLater()
            self.menu = None

        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

        self.actions = []
