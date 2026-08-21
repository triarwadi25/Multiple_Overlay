from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication
from qgis import processing
import os

from .provider import MultipleOverlayProvider


class MultipleOverlayToolsPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.menu = None
        self.actions = []

    def initGui(self):
        self.provider = MultipleOverlayProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

        vector_menu = self.iface.vectorMenu()
        self.menu = vector_menu.addMenu(
            QIcon(os.path.join(os.path.dirname(__file__), "icons", "overlay_multiple.svg")),
            "Overlay Multiple"
        )

        self._add_action(
            "Intersection Multiple",
            "Run multiple polygon intersection",
            "multiple_overlay_tools:intersection_multiple"
        )

        self._add_action(
            "Union Multiple",
            "Run multiple polygon union",
            "multiple_overlay_tools:union_multiple"
        )

        self._add_action(
            "Clip Multiple",
            "Clip multiple layers using one polygon",
            "multiple_overlay_tools:clip_multiple"
        )

    def _add_action(self, text, tooltip, algorithm_id):
        icon_map = {
            "multiple_overlay_tools:intersection_multiple": "intersection.svg",
            "multiple_overlay_tools:union_multiple": "union.svg",
            "multiple_overlay_tools:clip_multiple": "clip.svg",
        }

        icon_name = icon_map.get(algorithm_id)
        icon_path = (
            os.path.join(os.path.dirname(__file__), "icons", icon_name)
            if icon_name else None
        )

        action = QAction(
            QIcon(icon_path) if icon_path and os.path.exists(icon_path) else QIcon(),
            text,
            self.iface.mainWindow()
        )
        action.setToolTip(tooltip)
        action.triggered.connect(
            lambda checked=False, aid=algorithm_id: self.run_algorithm(aid)
        )

        self.menu.addAction(action)
        self.actions.append(action)

    def run_algorithm(self, algorithm_id):
        try:
            processing.execAlgorithmDialog(algorithm_id)
        except Exception as e:
            self.iface.messageBar().pushCritical(
                "Multiple Overlay Tools",
                str(e)
            )

    def unload(self):
        if self.menu:
            parent = self.iface.vectorMenu()
            parent.removeAction(self.menu.menuAction())
            self.menu.deleteLater()
            self.menu = None

        if self.provider:
            QgsApplication.processingRegistry().removeProvider(
                self.provider.id()
            )
            self.provider = None

        self.actions.clear()
