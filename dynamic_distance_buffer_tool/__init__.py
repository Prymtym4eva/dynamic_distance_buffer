# -*- coding: utf-8 -*-
"""
Dynamic Distance Buffer Tool - QGIS Plugin
Generates multiple concentric buffer rings at dynamic distances.
"""


def classFactory(iface):
    """Load the DynamicDistanceBufferPlugin class.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .plugin import DynamicDistanceBufferPlugin
    return DynamicDistanceBufferPlugin(iface)
