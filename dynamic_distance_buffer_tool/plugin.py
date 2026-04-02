# -*- coding: utf-8 -*-
"""
Main plugin class for Dynamic Distance Buffer Tool.
Registers the processing provider and adds a toolbar button / menu entry.
"""

import os

from qgis.PyQt.QtCore import QCoreApplication, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication

from .processing_provider import DynamicDistanceBufferProvider
from .ui.ring_buffer_dialog import DynamicDistanceBufferDialog


class DynamicDistanceBufferPlugin:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that provides the hook into the
            QGIS application at run time.
        :type iface: QgsInterface
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.provider = None
        self.actions = []
        self.menu = '&Dynamic Distance Buffer Tool'
        self.toolbar = self.iface.addToolBar('Dynamic Distance Buffer Tool')
        self.toolbar.setObjectName('DynamicDistanceBufferToolbar')

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        # Register the processing provider
        self.provider = DynamicDistanceBufferProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

        # Add toolbar action
        icon_path = os.path.join(self.plugin_dir, 'resources', 'icon.png')
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        action = QAction(icon, 'Dynamic Distance Buffer Tool', self.iface.mainWindow())
        action.triggered.connect(self.run)
        action.setStatusTip('Create multiple concentric buffer rings at dynamic distances')

        self.toolbar.addAction(action)
        self.iface.addPluginToVectorMenu(self.menu, action)
        self.actions.append(action)

    def unload(self):
        """Remove the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginVectorMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

        if self.toolbar:
            del self.toolbar

        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

    def run(self):
        """Run the plugin via the standalone dialog."""
        dialog = DynamicDistanceBufferDialog(self.iface)
        dialog.exec_()
