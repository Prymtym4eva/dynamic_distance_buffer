# -*- coding: utf-8 -*-
"""
Dynamic Distance Buffer Algorithm
Core QgsProcessingAlgorithm that generates concentric buffer rings
at user-defined dynamic distances.
"""

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
)


class DynamicDistanceBufferAlgorithm(QgsProcessingAlgorithm):
    """
    Generates multiple concentric buffer rings around input features
    using user-defined dynamic distances. Supports both non-overlapping
    ring (donut) and cumulative disc modes.
    """

    # Parameter constants
    INPUT = 'INPUT'
    DISTANCES = 'DISTANCES'
    DISTANCE_FIELD = 'DISTANCE_FIELD'
    DISTANCE_UNIT = 'DISTANCE_UNIT'
    RING_TYPE = 'RING_TYPE'
    DISSOLVE = 'DISSOLVE'
    SEGMENTS = 'SEGMENTS'
    END_CAP_STYLE = 'END_CAP_STYLE'
    OUTPUT = 'OUTPUT'

    # Unit conversion factors to meters
    UNIT_LABELS = ['Meters', 'Kilometers', 'Miles', 'Feet', 'Nautical Miles']
    UNIT_FACTORS = {
        0: 1.0,            # Meters
        1: 1000.0,         # Kilometers
        2: 1609.344,       # Miles
        3: 0.3048,         # Feet
        4: 1852.0,         # Nautical Miles
    }

    # Ring type options
    RING_TYPE_LABELS = ['Rings (non-overlapping donuts)', 'Discs (cumulative)']

    # End cap style options
    END_CAP_LABELS = ['Round', 'Flat', 'Square']
    END_CAP_MAP = {
        0: QgsGeometry.CapRound,
        1: QgsGeometry.CapFlat,
        2: QgsGeometry.CapSquare,
    }

    def name(self):
        return 'dynamicdistancebuffer'

    def displayName(self):
        return self.tr('Dynamic Distance Buffer')

    def group(self):
        return self.tr('Proximity Analysis')

    def groupId(self):
        return 'proximityanalysis'

    def tags(self):
        return [
            'buffer', 'ring', 'multiple', 'concentric', 'dynamic',
            'proximity', 'donut', 'distance', 'zones',
        ]

    def shortHelpString(self):
        return self.tr(
            'Generates multiple concentric buffer rings around input features '
            'at user-specified dynamic distances.\n\n'
            'DISTANCES: Enter a comma-separated list of positive numbers '
            '(e.g. 500,1000,2000,5000). Alternatively, select a numeric field '
            'from the input layer to read distances dynamically.\n\n'
            'RING TYPE:\n'
            '  \u2022 Rings \u2014 Non-overlapping donut polygons. Each ring represents '
            'only the area between consecutive distance thresholds.\n'
            '  \u2022 Discs \u2014 Cumulative full buffers that overlap.\n\n'
            'DISSOLVE: When enabled, merges all ring features that share the '
            'same distance band into a single multipart feature.\n\n'
            'NOTE: For accurate metric buffers, use a projected coordinate '
            'system. If the input layer uses a geographic CRS (e.g. WGS 84), '
            'results may be distorted.'
        )

    def createInstance(self):
        return DynamicDistanceBufferAlgorithm()

    def tr(self, string):
        return QCoreApplication.translate('DynamicDistanceBufferAlgorithm', string)

    # -------------------------------------------------------------------------
    # Parameter definition
    # -------------------------------------------------------------------------

    def initAlgorithm(self, config=None):
        """Define the inputs and outputs of the algorithm."""

        # Input layer
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input layer'),
                types=[QgsProcessing.TypeVectorAnyGeometry],
            )
        )

        # Manual distances
        self.addParameter(
            QgsProcessingParameterString(
                self.DISTANCES,
                self.tr('Distances (comma-separated)'),
                defaultValue='500,1000,2000,5000',
                optional=True,
            )
        )

        # Distance field (overrides manual distances when set)
        self.addParameter(
            QgsProcessingParameterField(
                self.DISTANCE_FIELD,
                self.tr('Distance field (overrides manual distances)'),
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.Numeric,
                optional=True,
            )
        )

        # Distance unit
        self.addParameter(
            QgsProcessingParameterEnum(
                self.DISTANCE_UNIT,
                self.tr('Distance unit'),
                options=self.UNIT_LABELS,
                defaultValue=0,
            )
        )

        # Ring type
        self.addParameter(
            QgsProcessingParameterEnum(
                self.RING_TYPE,
                self.tr('Ring type'),
                options=self.RING_TYPE_LABELS,
                defaultValue=0,
            )
        )

        # Dissolve
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.DISSOLVE,
                self.tr('Dissolve rings by distance band'),
                defaultValue=True,
            )
        )

        # Segments per quarter circle
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SEGMENTS,
                self.tr('Segments per quarter circle'),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=36,
                minValue=1,
                maxValue=1000,
            )
        )

        # End cap style
        self.addParameter(
            QgsProcessingParameterEnum(
                self.END_CAP_STYLE,
                self.tr('End cap style'),
                options=self.END_CAP_LABELS,
                defaultValue=0,
            )
        )

        # Output layer
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Output buffer layer'),
            )
        )

    # -------------------------------------------------------------------------
    # Core processing
    # -------------------------------------------------------------------------

    def processAlgorithm(self, parameters, context, feedback):
        """Run the dynamic distance buffer algorithm."""

        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.INPUT)
            )

        ring_type = self.parameterAsEnum(parameters, self.RING_TYPE, context)
        dissolve = self.parameterAsBool(parameters, self.DISSOLVE, context)
        segments = self.parameterAsInt(parameters, self.SEGMENTS, context)
        end_cap = self.parameterAsEnum(parameters, self.END_CAP_STYLE, context)
        unit_enum = self.parameterAsEnum(parameters, self.DISTANCE_UNIT, context)

        # Resolve and convert distances
        distances = self._parse_distances(parameters, context, source, feedback)
        distances = self._convert_distances(distances, unit_enum)

        # CRS warning
        if source.sourceCrs().isGeographic():
            feedback.pushWarning(
                'The input layer uses a geographic CRS ({}). Buffer distances '
                'are in degrees and results will be distorted. For accurate '
                'metric buffers, reproject the layer to an appropriate '
                'projected CRS first.'.format(source.sourceCrs().authid())
            )

        # Build output fields
        fields = self._build_output_fields()

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            fields, QgsWkbTypes.MultiPolygon, source.sourceCrs(),
        )
        if sink is None:
            raise QgsProcessingException(
                self.invalidSinkError(parameters, self.OUTPUT)
            )

        feature_count = source.featureCount()
        if feature_count == 0:
            feedback.pushInfo('Input layer is empty. Returning empty output.')
            return {self.OUTPUT: dest_id}

        total = feature_count * len(distances)
        if total > 100000:
            feedback.pushWarning(
                'Estimated output: {:,} features. This may require '
                'significant memory.'.format(total)
            )

        # ---- Main loop ----
        if dissolve:
            # Dissolve mode: collect geometries per distance band, then merge
            ring_collectors = {d: [] for d in distances}
            self._generate_rings(
                source, distances, ring_type, segments, end_cap,
                feedback, total, ring_collectors=ring_collectors,
            )
            self._write_dissolved(ring_collectors, distances, fields, sink, feedback)
        else:
            # Non-dissolve mode: write features directly
            self._generate_rings(
                source, distances, ring_type, segments, end_cap,
                feedback, total, sink=sink, fields=fields,
            )

        return {self.OUTPUT: dest_id}

    # -------------------------------------------------------------------------
    # Ring generation
    # -------------------------------------------------------------------------

    def _generate_rings(
        self, source, distances, ring_type, segments, end_cap,
        feedback, total, sink=None, fields=None, ring_collectors=None,
    ):
        """
        Iterate over features and distances to produce ring geometries.

        In dissolve mode, geometries are collected into ring_collectors.
        In non-dissolve mode, features are written directly to the sink.
        """
        end_cap_style = self.END_CAP_MAP.get(end_cap, QgsGeometry.CapRound)
        current = 0

        for feature in source.getFeatures():
            if feedback.isCanceled():
                break

            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                feedback.pushWarning(
                    'Feature {} has NULL or empty geometry \u2014 skipped.'.format(
                        feature.id()
                    )
                )
                current += len(distances)
                feedback.setProgress(int(current / total * 100))
                continue

            prev_buffer = None

            for i, dist in enumerate(distances):
                if feedback.isCanceled():
                    break

                # Create the buffer at the current distance
                buffer_geom = geom.buffer(
                    dist, segments,
                    endCapStyle=end_cap_style,
                    joinStyle=QgsGeometry.JoinStyleRound,
                    miterLimit=2.0,
                )

                # Determine ring or disc geometry
                if ring_type == 0 and prev_buffer is not None:
                    # Ring mode: subtract previous buffer
                    ring_geom = buffer_geom.difference(prev_buffer)
                    inner_dist = distances[i - 1]
                else:
                    ring_geom = buffer_geom
                    inner_dist = 0.0

                # Force to MultiPolygon for consistent output
                if ring_geom and not ring_geom.isEmpty():
                    ring_geom = QgsGeometry.collectGeometry([ring_geom])

                    if ring_collectors is not None:
                        # Dissolve mode: collect
                        ring_collectors[dist].append(ring_geom)
                    elif sink is not None and fields is not None:
                        # Direct write mode
                        out_feat = QgsFeature(fields)
                        out_feat.setGeometry(ring_geom)
                        out_feat.setAttributes([
                            i + 1,                  # ring_id
                            feature.id(),           # source_fid
                            inner_dist,             # dist_inner
                            dist,                   # dist_outer
                            dist,                   # distance
                        ])
                        sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

                prev_buffer = buffer_geom
                current += 1
                feedback.setProgress(int(current / total * 100))

    # -------------------------------------------------------------------------
    # Dissolve
    # -------------------------------------------------------------------------

    def _write_dissolved(self, ring_collectors, distances, fields, sink, feedback):
        """Merge collected geometries per distance band and write to sink."""
        for i, dist in enumerate(distances):
            if feedback.isCanceled():
                break

            geom_list = ring_collectors.get(dist, [])
            if not geom_list:
                continue

            # Union all geometries for this distance band
            merged = geom_list[0]
            for g in geom_list[1:]:
                if feedback.isCanceled():
                    break
                merged = merged.combine(g)

            if merged and not merged.isEmpty():
                merged = QgsGeometry.collectGeometry([merged])

                inner_dist = distances[i - 1] if i > 0 else 0.0
                out_feat = QgsFeature(fields)
                out_feat.setGeometry(merged)
                out_feat.setAttributes([
                    i + 1,          # ring_id
                    -1,             # source_fid (-1 = dissolved/mixed)
                    inner_dist,     # dist_inner
                    dist,           # dist_outer
                    dist,           # distance
                ])
                sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

        feedback.pushInfo(
            'Dissolved {} distance bands.'.format(len(distances))
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _build_output_fields(self):
        """Define the attribute schema for the output layer."""
        fields = QgsFields()
        fields.append(QgsField('ring_id', QVariant.Int))
        fields.append(QgsField('source_fid', QVariant.LongLong))
        fields.append(QgsField('dist_inner', QVariant.Double))
        fields.append(QgsField('dist_outer', QVariant.Double))
        fields.append(QgsField('distance', QVariant.Double))
        return fields

    def _parse_distances(self, parameters, context, source, feedback):
        """
        Resolve buffer distances from either a numeric field or a manual
        comma-separated string. Field-based distances take precedence.

        Returns a sorted list of unique positive distances (in the
        user's declared unit -- not yet converted to meters).
        """
        field_name = self.parameterAsString(
            parameters, self.DISTANCE_FIELD, context
        )

        if field_name:
            feedback.pushInfo(
                'Reading distances from field: "{}".'.format(field_name)
            )
            distances = set()
            for feature in source.getFeatures():
                val = feature[field_name]
                if val is not None:
                    try:
                        d = float(val)
                        if d > 0:
                            distances.add(d)
                    except (TypeError, ValueError):
                        pass

            if not distances:
                raise QgsProcessingException(
                    'No valid positive distances found in field "{}".'.format(
                        field_name
                    )
                )

            feedback.pushInfo(
                'Found {} unique distances from field.'.format(len(distances))
            )
            return sorted(distances)

        # Fall back to manual comma-separated string
        raw = self.parameterAsString(parameters, self.DISTANCES, context)
        if not raw or not raw.strip():
            raise QgsProcessingException(
                'No distances provided. Enter a comma-separated list of '
                'positive numbers or select a distance field.'
            )

        parts = [s.strip() for s in raw.replace(';', ',').split(',')]
        distances = []
        for p in parts:
            if not p:
                continue
            try:
                d = float(p)
                if d > 0:
                    distances.append(d)
                elif d <= 0:
                    feedback.pushWarning(
                        'Ignoring non-positive distance: {}'.format(p)
                    )
            except ValueError:
                feedback.pushWarning(
                    'Ignoring invalid distance value: "{}"'.format(p)
                )

        if not distances:
            raise QgsProcessingException(
                'No valid positive distances found in input. '
                'Please provide values like: 500,1000,2000'
            )

        unique = sorted(set(distances))
        feedback.pushInfo(
            'Using {} distances: {}'.format(
                len(unique),
                ', '.join(str(d) for d in unique),
            )
        )
        return unique

    def _convert_distances(self, distances, unit_enum):
        """Convert distances from the declared unit to the layer's CRS unit.

        Since QGIS buffer() operates in the layer's CRS units, and
        projected CRS units are typically meters, we multiply by the
        appropriate factor. For geographic CRS, the user has been warned.
        """
        factor = self.UNIT_FACTORS.get(unit_enum, 1.0)
        if factor == 1.0:
            return distances
        return [d * factor for d in distances]
