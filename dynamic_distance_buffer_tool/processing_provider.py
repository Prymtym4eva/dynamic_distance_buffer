# -*- coding: utf-8 -*-
"""
Processing provider for Dynamic Distance Buffer Tool.
Registers the algorithm so it appears in the Processing Toolbox.
"""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .ring_buffer_algorithm import DynamicDistanceBufferAlgorithm


class DynamicDistanceBufferProvider(QgsProcessingProvider):
    """Processing provider for dynamic distance buffer tools."""

    def id(self):
        return 'dynamicdistancebuffer'

    def name(self):
        return 'Dynamic Distance Buffer Tool'

    def longName(self):
        return 'Dynamic Distance Buffer Tools'

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'icon.png')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QgsProcessingProvider.icon(self)

    def loadAlgorithms(self):
        """Register all algorithms belonging to this provider."""
        self.addAlgorithm(DynamicDistanceBufferAlgorithm())
