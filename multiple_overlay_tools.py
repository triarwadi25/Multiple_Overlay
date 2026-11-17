# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication

from .provider import MultipleOverlayProvider

ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")

# (mode, menu text, tooltip, icon)
ACTIONS = [
    ("intersection", "Intersection Multiple",
     "Intersect several layers (points, lines, polygons)",
     "intersection.svg"),
    ("union", "Union Multiple",
     "Union of several layers of the same geometry type", "union.svg"),
    ("erase", "Erase Multiple",
     "Erase one layer with several polygon layers", "erase.svg"),
    ("clip", "Clip Multiple",
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

        for mode, text, tooltip, icon in ACTIONS:
            action = QAction(
                QIcon(os.path.join(ICON_DIR, icon)),
                text,
                self.iface.mainWindow(),
            )
            action.setToolTip(tooltip)
            action.triggered.connect(
                lambda checked=False, m=mode: self.open_dialog(m))
            self.menu.addAction(action)
            self.actions.append(action)

    def open_dialog(self, mode):
        # Imported lazily so a GUI problem can never block plugin loading.
        from .dialog import OverlayDialog

        dialog = OverlayDialog(self.iface, mode, self.iface.mainWindow())
        runner = getattr(dialog, "exec", None) or dialog.exec_
        runner()

    def unload(self):
        if self.menu:
            self.iface.vectorMenu().removeAction(self.menu.menuAction())
            self.menu.deleteLater()
            self.menu = None

        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

        self.actions = []
