# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .algorithms import (
    ClipMultiple,
    EraseMultiple,
    IntersectionMultiple,
    UnionMultiple,
)


class MultipleOverlayProvider(QgsProcessingProvider):

    def loadAlgorithms(self):
        self.addAlgorithm(IntersectionMultiple())
        self.addAlgorithm(UnionMultiple())
        self.addAlgorithm(EraseMultiple())
        self.addAlgorithm(ClipMultiple())

    def id(self):
        return "multiple_overlay_tools"

    def name(self):
        return "Multiple Overlay Tools"

    def longName(self):
        return "Multiple Overlay Tools"

    def icon(self):
        return QIcon(os.path.join(
            os.path.dirname(__file__), "icons", "overlay_multiple.svg"))
