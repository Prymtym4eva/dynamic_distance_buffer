# Dynamic Distance Buffer Tool — QGIS Plugin

## Technical Specification & Design Document

**Version:** 1.0.0  
**Minimum QGIS Version:** 3.22+  
**Python Version:** 3.9+  
**License:** GPL v3  

---

## 1. Overview

The Dynamic Distance Buffer Tool plugin for QGIS generates concentric buffer zones around point, line, or polygon features using user-defined, dynamic distances. Unlike the default QGIS single-distance buffer, this plugin allows analysts to specify an arbitrary list of distances and produce discrete, non-overlapping ring polygons — each representing a distinct proximity zone from the source features.

### 1.1 Key Capabilities

- Accept any number of buffer distances as a comma-separated list or loaded from a field.
- Generate non-overlapping rings (donuts) or cumulative overlapping buffers.
- Support for point, line, and polygon input geometries.
- Option to dissolve buffers per distance band.
- Dynamic distance input — distances can be pulled from a numeric field in the attribute table.
- Full integration with the QGIS Processing Framework for use in models and scripts.

### 1.2 Use Cases

- Emergency response planning (evacuation zones at 1 km, 3 km, 5 km, 10 km).
- Site suitability and proximity analysis.
- Noise or pollution dispersion modelling.
- Service area delineation for schools, hospitals, fire stations.
- Retail trade area analysis.

---

## 2. Architecture

### 2.1 Plugin Structure

```
dynamic_distance_buffer_tool/
├── __init__.py                  # Plugin loader
├── metadata.txt                 # QGIS plugin metadata
├── plugin.py                    # Main plugin class (toolbar & menu)
├── processing_provider.py       # Processing provider registration
├── ring_buffer_algorithm.py     # Core QgsProcessingAlgorithm
├── ui/
│   ├── ring_buffer_dialog.py    # Standalone dialog (non-processing)
│   └── ring_buffer_dialog.ui    # Qt Designer UI file
├── resources/
│   ├── icon.png                 # Toolbar icon
│   └── resources.qrc            # Qt resource file
├── help/
│   └── index.html               # Built-in help page
└── tests/
    ├── test_algorithm.py        # Unit tests for the algorithm
    └── fixtures/
        └── sample_points.gpkg   # Test data
```

### 2.2 Class Diagram

```
┌──────────────────────────────┐
│   DynamicDistanceBufferPlugin   │  ← Main entry point (plugin.py)
│  - iface: QgisInterface      │
│  + initGui()                 │
│  + unload()                  │
│  + run()                     │
└──────────┬───────────────────┘
           │ registers
           ▼
┌──────────────────────────────┐
│  DynamicDistanceBufferProvider          │  ← Processing provider
│  + loadAlgorithms()          │
└──────────┬───────────────────┘
           │ loads
           ▼
┌──────────────────────────────┐
│  DynamicDistanceBufferAlgorithm │  ← Core algorithm
│  + name()                    │
│  + displayName()             │
│  + group()                   │
│  + initAlgorithm()           │
│  + processAlgorithm()        │
└──────────────────────────────┘
```

### 2.3 Data Flow

```
Input Layer ─► Parse Distances ─► Sort Ascending ─► For Each Feature:
                                                       │
                                     ┌─────────────────┘
                                     ▼
                              Buffer at d[n] ─► Subtract d[n-1] ─► Ring Geometry
                                     │
                                     ▼
                              Assign attributes (distance band, source ID)
                                     │
                                     ▼
                              ┌──────────────┐
                              │ Output Layer  │
                              │  (rings)      │
                              └──────────────┘
```

---

## 3. User Interface

### 3.1 Processing Dialog Parameters

The algorithm integrates with the QGIS Processing Toolbox and exposes the following parameters:

| Parameter | Type | Description |
|---|---|---|
| **Input Layer** | `QgsProcessingParameterFeatureSource` | Any vector layer (point, line, polygon). |
| **Distances** | `QgsProcessingParameterString` | Comma-separated list of buffer distances (e.g. `500,1000,2000,5000`). |
| **Distance Field** | `QgsProcessingParameterField` (optional) | Numeric field containing per-feature distances. Overrides the manual list when set. |
| **Distance Unit** | `QgsProcessingParameterEnum` | Meters, Kilometers, Miles, Feet, Nautical Miles. |
| **Ring Type** | `QgsProcessingParameterEnum` | `Rings (non-overlapping)` or `Discs (cumulative)`. |
| **Dissolve by Distance** | `QgsProcessingParameterBoolean` | Merge all rings at the same distance band into a single feature. Default: `True`. |
| **Segments** | `QgsProcessingParameterNumber` | Number of segments per quarter-circle for curved approximation. Default: `36`. |
| **End Cap Style** | `QgsProcessingParameterEnum` | Round, Flat, Square. Default: Round. |
| **Output Layer** | `QgsProcessingParameterFeatureSink` | Destination for the ring buffer layer. |

### 3.2 Standalone Dialog (Optional)

A simplified dialog accessible from the toolbar button:

```
┌───────────────────────────────────────────────┐
│  Dynamic Distance Buffer Tool                    [?]  │
├───────────────────────────────────────────────┤
│                                               │
│  Input Layer:    [ ▼ Dropdown            ]    │
│                                               │
│  ── Distance Configuration ──────────────     │
│                                               │
│  ○ Manual distances                           │
│    [ 500, 1000, 2000, 5000             ]      │
│    [+ Add] [- Remove] [↑↓ Sort]              │
│                                               │
│  ○ From field                                 │
│    [ ▼ Select numeric field            ]      │
│                                               │
│  Unit:           [ ▼ Meters              ]    │
│                                               │
│  ── Output Options ──────────────────────     │
│                                               │
│  Ring Type:      [ ▼ Rings (donut)       ]    │
│  ☑ Dissolve by distance band                  │
│  Segments:       [ 36                    ]    │
│                                               │
│           [ Cancel ]  [ Run ]                 │
└───────────────────────────────────────────────┘
```

---

## 4. Algorithm Design

### 4.1 Core Logic — `processAlgorithm()`

```python
def processAlgorithm(self, parameters, context, feedback):
    source = self.parameterAsSource(parameters, 'INPUT', context)
    distances = self._parse_distances(parameters, context)
    ring_type = self.parameterAsEnum(parameters, 'RING_TYPE', context)
    dissolve = self.parameterAsBool(parameters, 'DISSOLVE', context)
    segments = self.parameterAsInt(parameters, 'SEGMENTS', context)

    # Sort distances ascending — required for ring subtraction
    distances = sorted(set(distances))

    # Define output fields
    fields = QgsFields()
    fields.append(QgsField('ring_id', QVariant.Int))
    fields.append(QgsField('source_fid', QVariant.LongLong))
    fields.append(QgsField('dist_inner', QVariant.Double))
    fields.append(QgsField('dist_outer', QVariant.Double))
    fields.append(QgsField('distance', QVariant.Double))

    (sink, dest_id) = self.parameterAsSink(
        parameters, 'OUTPUT', context,
        fields, QgsWkbTypes.MultiPolygon, source.sourceCrs()
    )

    total = source.featureCount() * len(distances)
    current = 0

    for feature in source.getFeatures():
        if feedback.isCanceled():
            break

        geom = feature.geometry()
        prev_buffer = None

        for i, dist in enumerate(distances):
            if feedback.isCanceled():
                break

            buffer_geom = geom.buffer(dist, segments)

            if ring_type == 0 and prev_buffer is not None:
                # Ring mode: subtract previous buffer to create donut
                ring_geom = buffer_geom.difference(prev_buffer)
                inner_dist = distances[i - 1]
            else:
                ring_geom = buffer_geom
                inner_dist = 0.0

            if not ring_geom.isEmpty():
                out_feat = QgsFeature(fields)
                out_feat.setGeometry(ring_geom)
                out_feat.setAttributes([
                    i + 1,
                    feature.id(),
                    inner_dist,
                    dist,
                    dist
                ])
                sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

            prev_buffer = buffer_geom
            current += 1
            feedback.setProgress(int(current / total * 100))

    # Optional dissolve pass
    if dissolve:
        self._dissolve_by_distance(dest_id, context, feedback)

    return {'OUTPUT': dest_id}
```

### 4.2 Distance Parsing

```python
def _parse_distances(self, parameters, context):
    """
    Resolve distances from either the manual string input
    or from a numeric attribute field.
    """
    field_name = self.parameterAsString(parameters, 'DISTANCE_FIELD', context)

    if field_name:
        source = self.parameterAsSource(parameters, 'INPUT', context)
        distances = set()
        for feature in source.getFeatures():
            val = feature[field_name]
            if val is not None and val > 0:
                distances.add(float(val))
        return sorted(distances)

    raw = self.parameterAsString(parameters, 'DISTANCES', context)
    parts = [s.strip() for s in raw.replace(';', ',').split(',')]
    distances = []
    for p in parts:
        try:
            d = float(p)
            if d > 0:
                distances.append(d)
        except ValueError:
            pass

    if not distances:
        raise QgsProcessingException(
            'No valid distances provided. Enter positive numbers separated by commas.'
        )

    return sorted(set(distances))
```

### 4.3 Unit Conversion

```python
UNIT_FACTORS = {
    0: 1.0,          # Meters (base)
    1: 1000.0,       # Kilometers
    2: 1609.344,     # Miles
    3: 0.3048,       # Feet
    4: 1852.0,       # Nautical Miles
}

def _convert_distances(self, distances, unit_enum):
    factor = self.UNIT_FACTORS.get(unit_enum, 1.0)
    return [d * factor for d in distances]
```

### 4.4 CRS Handling

The algorithm must operate in a projected CRS to produce metrically accurate buffers. If the input layer uses a geographic CRS (e.g. EPSG:4326), the algorithm will:

1. Detect the CRS type via `source.sourceCrs().isGeographic()`.
2. Reproject features to an appropriate UTM zone or a user-specified projected CRS.
3. Perform the buffer operations in the projected space.
4. Optionally reproject the output back to the original CRS.

A warning is emitted via `feedback.reportError()` if the input CRS is geographic and no reprojection is configured.

---

## 5. Output Schema

### 5.1 Attribute Table

Each feature in the output layer carries the following attributes:

| Field | Type | Description |
|---|---|---|
| `ring_id` | Integer | Sequential ring number (1 = innermost). |
| `source_fid` | Long | Feature ID of the original input feature. |
| `dist_inner` | Double | Inner boundary distance (0 for the first ring or in disc mode). |
| `dist_outer` | Double | Outer boundary distance. |
| `distance` | Double | The nominal buffer distance for this ring (same as `dist_outer`). |

### 5.2 Geometry

- **Ring mode:** MultiPolygon with a hole (donut) for all rings beyond the first.
- **Disc mode:** MultiPolygon without holes (full cumulative buffers).
- **Dissolve on:** One feature per distance band (all source features merged).
- **Dissolve off:** One ring feature per source feature per distance.

---

## 6. Processing Framework Integration

### 6.1 Provider Registration

```python
# processing_provider.py
from qgis.core import QgsProcessingProvider
from .ring_buffer_algorithm import DynamicDistanceBufferAlgorithm


class DynamicDistanceBufferProvider(QgsProcessingProvider):

    def id(self):
        return 'dynamicdistancebuffer'

    def name(self):
        return 'Dynamic Distance Buffer Tool'

    def icon(self):
        return QgsProcessingProvider.icon(self)

    def loadAlgorithms(self):
        self.addAlgorithm(DynamicDistanceBufferAlgorithm())
```

### 6.2 Algorithm Metadata

```python
class DynamicDistanceBufferAlgorithm(QgsProcessingAlgorithm):

    def name(self):
        return 'dynamicdistancebuffer'

    def displayName(self):
        return 'Dynamic Distance Buffer Tool'

    def group(self):
        return 'Proximity Analysis'

    def groupId(self):
        return 'proximityanalysis'

    def shortHelpString(self):
        return (
            'Generates multiple concentric buffer rings around input features '
            'at user-specified distances. Supports non-overlapping ring (donut) '
            'and cumulative disc modes, with optional dissolve per distance band.'
        )

    def tags(self):
        return ['buffer', 'ring', 'multiple', 'concentric', 'proximity', 'donut']
```

### 6.3 Usage in PyQGIS Scripts

```python
import processing

result = processing.run('dynamicdistancebuffer:dynamicdistancebuffer', {
    'INPUT': 'path/to/points.gpkg',
    'DISTANCES': '500,1000,2000,5000',
    'DISTANCE_FIELD': '',
    'DISTANCE_UNIT': 0,        # Meters
    'RING_TYPE': 0,            # Rings (donut)
    'DISSOLVE': True,
    'SEGMENTS': 36,
    'END_CAP_STYLE': 0,       # Round
    'OUTPUT': 'memory:'
})

ring_layer = result['OUTPUT']
```

### 6.4 Usage in Graphical Modeler

The algorithm appears under **Proximity Analysis → Dynamic Distance Buffer Tool** in the Processing Toolbox and can be dragged into any Graphical Model. All parameters are exposed as model inputs.

---

## 7. Edge Cases & Validation

| Scenario | Behaviour |
|---|---|
| Empty distance list | Raises `QgsProcessingException` with a descriptive message. |
| Negative distances | Silently filtered out during parsing. |
| Duplicate distances | Deduplicated via `set()` before processing. |
| Zero distance | Filtered out (no zero-width buffer). |
| Empty input layer | Returns an empty output layer with correct schema. |
| Mixed geometry types | All geometries buffered; output is always MultiPolygon. |
| Geographic CRS input | Warning emitted; user advised to reproject or enable auto-reprojection. |
| Very large distances | Memory warning via feedback if estimated ring count exceeds 100 000 features. |
| NULL geometry features | Skipped with a logged warning per feature. |
| Cancelled by user | Graceful stop via `feedback.isCanceled()` check at every loop iteration. |

---

## 8. Sketched Visual Behaviour

### 8.1 Ring (Donut) Mode — Distances: 500, 1000, 2000

```
            ┌─────────────────────────┐
            │                         │
            │   Ring 3: 1000–2000 m   │
            │  ┌───────────────────┐  │
            │  │                   │  │
            │  │  Ring 2: 500–1000 │  │
            │  │  ┌─────────────┐  │  │
            │  │  │             │  │  │
            │  │  │  Ring 1:    │  │  │
            │  │  │  0–500 m    │  │  │
            │  │  │    [ • ]    │  │  │
            │  │  │             │  │  │
            │  │  └─────────────┘  │  │
            │  │                   │  │
            │  └───────────────────┘  │
            │                         │
            └─────────────────────────┘
```

### 8.2 Disc (Cumulative) Mode — Same Distances

```
            ┌─────────────────────────┐
            │ Disc 3: 0–2000 m        │
            │  ┌───────────────────┐  │
            │  │ Disc 2: 0–1000 m  │  │
            │  │  ┌─────────────┐  │  │
            │  │  │ Disc 1:     │  │  │
            │  │  │ 0–500 m     │  │  │
            │  │  │    [ • ]    │  │  │
            │  │  └─────────────┘  │  │
            │  └───────────────────┘  │
            └─────────────────────────┘
```

---

## 9. Styling & Symbology

The plugin ships with a default graduated colour ramp applied to the `distance` field:

| Ring | Default Fill | Opacity |
|---|---|---|
| Innermost | `#d73027` (red) | 40% |
| Middle bands | `#fee08b` → `#91cf60` | 35% |
| Outermost | `#1a9850` (green) | 30% |

Symbology is applied as a `QgsGraduatedSymbolRenderer` on the output layer when loaded via the standalone dialog. Processing Toolbox runs use the default single symbol unless the user loads a `.qml` style file.

---

## 10. Testing

### 10.1 Unit Tests

```python
# tests/test_algorithm.py
class TestDynamicDistanceBuffer(unittest.TestCase):

    def test_basic_point_rings(self):
        """Three rings around a single point produce 3 non-overlapping donuts."""

    def test_disc_mode(self):
        """Disc mode produces overlapping full buffers."""

    def test_dissolve(self):
        """Dissolve merges rings from multiple features at the same distance."""

    def test_field_distances(self):
        """Distances read from a numeric field produce correct rings."""

    def test_empty_layer(self):
        """Empty input returns empty output with correct schema."""

    def test_negative_distances_ignored(self):
        """Negative values in the distance list are silently dropped."""

    def test_geographic_crs_warning(self):
        """A geographic CRS triggers a feedback warning."""

    def test_cancellation(self):
        """Algorithm stops cleanly when feedback signals cancellation."""
```

### 10.2 Running Tests

```bash
cd ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/dynamic_distance_buffer_tool
python -m pytest tests/ -v
```

---

## 11. Installation

### From the QGIS Plugin Repository

1. Open QGIS → **Plugins** → **Manage and Install Plugins**.
2. Search for **Dynamic Distance Buffer Tool**.
3. Click **Install Plugin**.

### From a ZIP Archive

1. Download `dynamic_distance_buffer_tool.zip`.
2. Open QGIS → **Plugins** → **Manage and Install Plugins** → **Install from ZIP**.
3. Browse to the ZIP file and click **Install Plugin**.

### Manual Installation

Copy the `dynamic_distance_buffer_tool/` folder to:

- **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
- **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`

Restart QGIS and enable the plugin in **Plugins → Manage and Install Plugins**.

---

## 12. Metadata

```ini
# metadata.txt
[general]
name=Dynamic Distance Buffer Tool
qgisMinimumVersion=3.22
description=Generate multiple concentric buffer rings at dynamic distances.
version=1.0.0
author=<Your Name>
email=<your.email@example.com>
about=Creates non-overlapping ring (donut) or cumulative disc buffers around
    point, line, or polygon features. Distances can be entered manually as a
    comma-separated list or read dynamically from a numeric attribute field.
    Fully integrated with the QGIS Processing Framework.
tracker=https://github.com/<user>/dynamic-distance-buffer-tool/issues
repository=https://github.com/<user>/dynamic-distance-buffer-tool
tags=buffer,ring,multiple,concentric,proximity,donut,analysis
homepage=https://github.com/<user>/dynamic-distance-buffer-tool
category=Analysis
icon=resources/icon.png
experimental=False
deprecated=False
changelog=
    1.0.0 - Initial release
        - Manual and field-based dynamic distances
        - Ring (donut) and disc (cumulative) modes
        - Dissolve by distance band
        - Processing Framework integration
```

---

## 13. Roadmap

| Version | Feature |
|---|---|
| 1.1 | Variable distances per feature (multi-field mode). |
| 1.2 | Negative (inward) buffers for polygon shrinkage rings. |
| 1.3 | Flat-sided buffers for line features (single-side mode). |
| 1.4 | Expression-based distances (e.g. `"population" / 100`). |
| 2.0 | Network-based service area rings using road graph data. |
