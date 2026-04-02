# -*- coding: utf-8 -*-
"""
Standalone dialog for Dynamic Distance Buffer Tool.
Provides a simplified GUI accessible from the toolbar button,
wrapping the Processing algorithm underneath.
"""

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QPushButton,
    QDialogButtonBox,
    QMessageBox,
    QApplication,
    QFileDialog,
)
from qgis.core import (
    QgsMapLayerProxyModel,
    QgsProject,
    QgsVectorLayer,
    QgsProcessingFeedback,
)
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox

import processing


class DynamicDistanceBufferDialog(QDialog):
    """Standalone dialog for running the Dynamic Distance Buffer algorithm."""

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle('Dynamic Distance Buffer Tool')
        self.setMinimumWidth(480)
        self._build_ui()
        self._connect_signals()

    # -------------------------------------------------------------------------
    # UI construction
    # -------------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ---- Input layer ----
        form = QFormLayout()
        self.layer_combo = QgsMapLayerComboBox()
        self.layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self.layer_combo.setMinimumWidth(350)
        form.addRow('Input layer:', self.layer_combo)
        layout.addLayout(form)

        # ---- Distance configuration ----
        dist_group = QGroupBox('Distance Configuration')
        dist_layout = QVBoxLayout()

        # Radio: manual vs field
        self.radio_manual = QRadioButton('Manual distances')
        self.radio_field = QRadioButton('From attribute field')
        self.radio_manual.setChecked(True)

        radio_group = QButtonGroup(self)
        radio_group.addButton(self.radio_manual)
        radio_group.addButton(self.radio_field)

        dist_layout.addWidget(self.radio_manual)

        # Manual distance input
        manual_layout = QHBoxLayout()
        self.distance_edit = QLineEdit()
        self.distance_edit.setPlaceholderText('e.g. 500, 1000, 2000, 5000')
        self.distance_edit.setText('500,1000,2000,5000')
        manual_layout.addWidget(self.distance_edit)
        dist_layout.addLayout(manual_layout)

        dist_layout.addWidget(self.radio_field)

        # Field combo
        self.field_combo = QgsFieldComboBox()
        self.field_combo.setFilters(QgsFieldProxyModel_Numeric())
        self.field_combo.setEnabled(False)
        dist_layout.addWidget(self.field_combo)

        # Unit combo
        unit_layout = QFormLayout()
        self.unit_combo = QComboBox()
        self.unit_combo.addItems([
            'Meters', 'Kilometers', 'Miles', 'Feet', 'Nautical Miles',
        ])
        unit_layout.addRow('Unit:', self.unit_combo)
        dist_layout.addLayout(unit_layout)

        dist_group.setLayout(dist_layout)
        layout.addWidget(dist_group)

        # ---- Output options ----
        opts_group = QGroupBox('Output Options')
        opts_layout = QFormLayout()

        self.ring_type_combo = QComboBox()
        self.ring_type_combo.addItems([
            'Rings (non-overlapping donuts)',
            'Discs (cumulative)',
        ])
        opts_layout.addRow('Ring type:', self.ring_type_combo)

        self.dissolve_check = QCheckBox('Dissolve by distance band')
        self.dissolve_check.setChecked(True)
        opts_layout.addRow(self.dissolve_check)

        self.segments_spin = QSpinBox()
        self.segments_spin.setRange(1, 1000)
        self.segments_spin.setValue(36)
        opts_layout.addRow('Segments:', self.segments_spin)

        self.endcap_combo = QComboBox()
        self.endcap_combo.addItems(['Round', 'Flat', 'Square'])
        opts_layout.addRow('End cap style:', self.endcap_combo)

        opts_group.setLayout(opts_layout)
        layout.addWidget(opts_group)

        # ---- Output destination ----
        output_group = QGroupBox('Output')
        output_layout = QVBoxLayout()

        self.radio_memory = QRadioButton('Save to temporary layer')
        self.radio_file = QRadioButton('Save to file')
        self.radio_memory.setChecked(True)

        output_radio_group = QButtonGroup(self)
        output_radio_group.addButton(self.radio_memory)
        output_radio_group.addButton(self.radio_file)

        output_layout.addWidget(self.radio_memory)
        output_layout.addWidget(self.radio_file)

        file_layout = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText('Select output file...')
        self.output_path_edit.setEnabled(False)
        self.browse_button = QPushButton('Browse...')
        self.browse_button.setEnabled(False)
        self.browse_button.clicked.connect(self._browse_output)
        file_layout.addWidget(self.output_path_edit)
        file_layout.addWidget(self.browse_button)
        output_layout.addLayout(file_layout)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # ---- Buttons ----
        button_box = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Ok
        )
        button_box.button(QDialogButtonBox.Ok).setText('Run')
        button_box.accepted.connect(self._on_run)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _connect_signals(self):
        self.radio_manual.toggled.connect(self._toggle_distance_mode)
        self.radio_field.toggled.connect(self._toggle_distance_mode)
        self.layer_combo.layerChanged.connect(self._on_layer_changed)
        self.radio_file.toggled.connect(self._toggle_output_mode)

        # Initialise field combo with current layer
        self._on_layer_changed(self.layer_combo.currentLayer())

    def _toggle_distance_mode(self):
        manual = self.radio_manual.isChecked()
        self.distance_edit.setEnabled(manual)
        self.field_combo.setEnabled(not manual)

    def _on_layer_changed(self, layer):
        if layer:
            self.field_combo.setLayer(layer)

    def _toggle_output_mode(self):
        save_to_file = self.radio_file.isChecked()
        self.output_path_edit.setEnabled(save_to_file)
        self.browse_button.setEnabled(save_to_file)

    def _browse_output(self):
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            'Save Output As',
            '',
            'GeoPackage (*.gpkg);;Shapefile (*.shp);;GeoJSON (*.geojson);;All Files (*)',
        )
        if path:
            self.output_path_edit.setText(path)

    # -------------------------------------------------------------------------
    # Execution
    # -------------------------------------------------------------------------

    def _on_run(self):
        """Gather parameters and run the processing algorithm."""
        layer = self.layer_combo.currentLayer()
        if not layer:
            QMessageBox.warning(self, 'Error', 'Please select an input layer.')
            return

        # Determine output destination
        if self.radio_file.isChecked():
            output_path = self.output_path_edit.text().strip()
            if not output_path:
                QMessageBox.warning(self, 'Error', 'Please select an output file location.')
                return
            output_dest = output_path
        else:
            output_dest = 'memory:Dynamic Distance Buffers'

        params = {
            'INPUT': layer,
            'DISTANCES': self.distance_edit.text() if self.radio_manual.isChecked() else '',
            'DISTANCE_FIELD': self.field_combo.currentField() if self.radio_field.isChecked() else '',
            'DISTANCE_UNIT': self.unit_combo.currentIndex(),
            'RING_TYPE': self.ring_type_combo.currentIndex(),
            'DISSOLVE': self.dissolve_check.isChecked(),
            'SEGMENTS': self.segments_spin.value(),
            'END_CAP_STYLE': self.endcap_combo.currentIndex(),
            'OUTPUT': output_dest,
        }

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            result = processing.run(
                'dynamicdistancebuffer:dynamicdistancebuffer',
                params,
            )
            QApplication.restoreOverrideCursor()

            output_layer = result.get('OUTPUT')
            if isinstance(output_layer, str):
                output_layer = QgsVectorLayer(output_layer, 'Dynamic Distance Buffers', 'ogr')

            if isinstance(output_layer, QgsVectorLayer) and output_layer.isValid():
                self._apply_default_style(output_layer)
                QgsProject.instance().addMapLayer(output_layer)
                self.iface.messageBar().pushSuccess(
                    'Dynamic Distance Buffer Tool',
                    'Created {} buffer features.'.format(output_layer.featureCount()),
                )
            else:
                QgsProject.instance().addMapLayer(
                    QgsVectorLayer(result['OUTPUT'], 'Dynamic Distance Buffers', 'memory')
                )

            self.accept()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self, 'Processing Error', str(e)
            )

    def _apply_default_style(self, layer):
        """Apply a graduated colour ramp based on the distance field."""
        try:
            from qgis.core import (
                QgsGraduatedSymbolRenderer,
                QgsRendererRange,
                QgsSymbol,
                QgsStyle,
                QgsClassificationEqualInterval,
            )

            # Use a spectral colour ramp (red -> yellow -> green)
            style = QgsStyle.defaultStyle()
            ramp = style.colorRamp('Spectral')
            if ramp is None:
                ramp = style.colorRamp('RdYlGn')

            renderer = QgsGraduatedSymbolRenderer('distance')
            renderer.setSourceColorRamp(ramp)
            renderer.updateClasses(
                layer,
                QgsGraduatedSymbolRenderer.EqualInterval,
                layer.featureCount(),
            )

            # Set fill opacity on all symbols
            for r in renderer.ranges():
                symbol = r.symbol()
                symbol.setOpacity(0.4)

            layer.setRenderer(renderer)
            layer.triggerRepaint()

        except Exception:
            # Fall back to default style if anything goes wrong
            pass


def QgsFieldProxyModel_Numeric():
    """Return the numeric field filter flag."""
    from qgis.core import QgsFieldProxyModel
    return QgsFieldProxyModel.Numeric
