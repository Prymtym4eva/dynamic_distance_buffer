# -*- coding: utf-8 -*-
"""
Unit tests for the Dynamic Distance Buffer algorithm.

Run from the QGIS Python console or via pytest with a QGIS environment:
    cd dynamic_distance_buffer_tool
    python -m pytest tests/ -v
"""

import unittest
from unittest.mock import MagicMock

from qgis.core import (
    QgsApplication,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProject,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
)
from qgis.PyQt.QtCore import QVariant

from dynamic_distance_buffer_tool.ring_buffer_algorithm import DynamicDistanceBufferAlgorithm


def _make_point_layer(points, crs='EPSG:32632', fields=None, field_values=None):
    """Create an in-memory point layer for testing.

    :param points: list of (x, y) tuples.
    :param crs: CRS auth id string.
    :param fields: optional list of (name, QVariant type) tuples.
    :param field_values: optional list of dicts {field_name: value} per feature.
    """
    uri = 'Point?crs={}'.format(crs)
    if fields:
        for name, vtype in fields:
            uri += '&field={}:{}'.format(
                name,
                {QVariant.Double: 'double', QVariant.Int: 'integer'}.get(
                    vtype, 'string'
                ),
            )

    layer = QgsVectorLayer(uri, 'test_points', 'memory')
    provider = layer.dataProvider()

    for i, (x, y) in enumerate(points):
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        if field_values and i < len(field_values):
            feat.setAttributes(list(field_values[i].values()))
        provider.addFeatures([feat])

    layer.updateExtents()
    return layer


class TestDistanceParsing(unittest.TestCase):
    """Test distance parsing from string and field inputs."""

    def setUp(self):
        self.alg = DynamicDistanceBufferAlgorithm()
        self.alg.initAlgorithm()
        self.context = QgsProcessingContext()
        self.feedback = QgsProcessingFeedback()

    def test_comma_separated(self):
        """Parse a basic comma-separated distance list."""
        layer = _make_point_layer([(0, 0)])
        source = layer
        params = {
            'DISTANCES': '500,1000,2000',
            'DISTANCE_FIELD': '',
        }
        distances = self.alg._parse_distances(
            params, self.context, source, self.feedback
        )
        self.assertEqual(distances, [500.0, 1000.0, 2000.0])

    def test_semicolons_accepted(self):
        """Semicolons should be treated as delimiters too."""
        layer = _make_point_layer([(0, 0)])
        params = {
            'DISTANCES': '100;200;300',
            'DISTANCE_FIELD': '',
        }
        distances = self.alg._parse_distances(
            params, self.context, layer, self.feedback
        )
        self.assertEqual(distances, [100.0, 200.0, 300.0])

    def test_duplicates_removed(self):
        """Duplicate distances should be deduplicated."""
        layer = _make_point_layer([(0, 0)])
        params = {
            'DISTANCES': '500,500,1000,1000',
            'DISTANCE_FIELD': '',
        }
        distances = self.alg._parse_distances(
            params, self.context, layer, self.feedback
        )
        self.assertEqual(distances, [500.0, 1000.0])

    def test_negative_ignored(self):
        """Negative values should be silently dropped."""
        layer = _make_point_layer([(0, 0)])
        params = {
            'DISTANCES': '-100,500,1000',
            'DISTANCE_FIELD': '',
        }
        distances = self.alg._parse_distances(
            params, self.context, layer, self.feedback
        )
        self.assertEqual(distances, [500.0, 1000.0])

    def test_empty_raises(self):
        """An empty distance string should raise an exception."""
        layer = _make_point_layer([(0, 0)])
        params = {
            'DISTANCES': '',
            'DISTANCE_FIELD': '',
        }
        with self.assertRaises(Exception):
            self.alg._parse_distances(
                params, self.context, layer, self.feedback
            )

    def test_unsorted_gets_sorted(self):
        """Distances should be returned sorted ascending."""
        layer = _make_point_layer([(0, 0)])
        params = {
            'DISTANCES': '2000,500,1000',
            'DISTANCE_FIELD': '',
        }
        distances = self.alg._parse_distances(
            params, self.context, layer, self.feedback
        )
        self.assertEqual(distances, [500.0, 1000.0, 2000.0])


class TestUnitConversion(unittest.TestCase):
    """Test unit conversion factors."""

    def setUp(self):
        self.alg = DynamicDistanceBufferAlgorithm()

    def test_meters_passthrough(self):
        result = self.alg._convert_distances([1000], 0)
        self.assertEqual(result, [1000])

    def test_kilometers(self):
        result = self.alg._convert_distances([1, 2], 1)
        self.assertEqual(result, [1000.0, 2000.0])

    def test_miles(self):
        result = self.alg._convert_distances([1], 2)
        self.assertAlmostEqual(result[0], 1609.344, places=3)

    def test_feet(self):
        result = self.alg._convert_distances([1000], 3)
        self.assertAlmostEqual(result[0], 304.8, places=1)

    def test_nautical_miles(self):
        result = self.alg._convert_distances([1], 4)
        self.assertEqual(result[0], 1852.0)


class TestRingGeneration(unittest.TestCase):
    """Integration tests for the full algorithm execution."""

    def setUp(self):
        self.alg = DynamicDistanceBufferAlgorithm()
        self.alg.initAlgorithm()
        self.context = QgsProcessingContext()
        self.context.setProject(QgsProject.instance())
        self.feedback = QgsProcessingFeedback()

    def test_single_point_three_rings(self):
        """A single point with 3 distances should produce 3 ring features."""
        layer = _make_point_layer([(500000, 5000000)], crs='EPSG:32632')
        QgsProject.instance().addMapLayer(layer, False)

        params = {
            'INPUT': layer,
            'DISTANCES': '500,1000,2000',
            'DISTANCE_FIELD': '',
            'DISTANCE_UNIT': 0,
            'RING_TYPE': 0,
            'DISSOLVE': False,
            'SEGMENTS': 36,
            'END_CAP_STYLE': 0,
            'OUTPUT': 'memory:test_output',
        }

        result = self.alg.processAlgorithm(params, self.context, self.feedback)
        self.assertIn('OUTPUT', result)

    def test_disc_mode(self):
        """Disc mode should produce cumulative (overlapping) buffers."""
        layer = _make_point_layer([(500000, 5000000)], crs='EPSG:32632')
        QgsProject.instance().addMapLayer(layer, False)

        params = {
            'INPUT': layer,
            'DISTANCES': '500,1000',
            'DISTANCE_FIELD': '',
            'DISTANCE_UNIT': 0,
            'RING_TYPE': 1,     # Disc mode
            'DISSOLVE': False,
            'SEGMENTS': 36,
            'END_CAP_STYLE': 0,
            'OUTPUT': 'memory:test_output',
        }

        result = self.alg.processAlgorithm(params, self.context, self.feedback)
        self.assertIn('OUTPUT', result)


class TestAlgorithmMetadata(unittest.TestCase):
    """Verify algorithm registration metadata."""

    def setUp(self):
        self.alg = DynamicDistanceBufferAlgorithm()

    def test_name(self):
        self.assertEqual(self.alg.name(), 'dynamicdistancebuffer')

    def test_display_name(self):
        self.assertEqual(self.alg.displayName(), 'Dynamic Distance Buffer')

    def test_group(self):
        self.assertEqual(self.alg.group(), 'Proximity Analysis')

    def test_tags(self):
        tags = self.alg.tags()
        self.assertIn('buffer', tags)
        self.assertIn('dynamic', tags)

    def test_create_instance(self):
        instance = self.alg.createInstance()
        self.assertIsInstance(instance, DynamicDistanceBufferAlgorithm)


if __name__ == '__main__':
    unittest.main()
