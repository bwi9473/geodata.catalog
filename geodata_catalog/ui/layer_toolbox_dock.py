from __future__ import annotations

from pathlib import Path

from geodata_catalog.logging_utils import PluginLogger
from geodata_catalog.services.layer_toolbox_service import LayerToolboxService

try:
    from qgis.core import QgsMapLayerType, QgsProject, QgsWkbTypes
    from qgis.PyQt.QtCore import QSize, Qt
    from qgis.PyQt.QtGui import QIcon, QPixmap
    from qgis.PyQt.QtWidgets import (
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QDockWidget,
        QDoubleSpinBox,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover
    QgsMapLayerType = None
    QgsProject = None
    QgsWkbTypes = None
    QSize = None
    Qt = None
    QIcon = None
    QPixmap = None
    QButtonGroup = None
    QCheckBox = None
    QComboBox = None
    QDockWidget = object
    QDoubleSpinBox = None
    QFormLayout = None
    QGridLayout = None
    QGroupBox = None
    QHBoxLayout = None
    QLabel = None
    QPushButton = None
    QToolButton = None
    QVBoxLayout = None
    QWidget = None


class LayerToolboxDock(QDockWidget):
    """Dock panel with helper tools for loaded layers."""

    def __init__(
        self,
        parent,
        toolbox_service: LayerToolboxService,
        logger: PluginLogger,
        iface=None,
    ) -> None:
        if QDockWidget is object:  # pragma: no cover
            raise RuntimeError("QGIS runtime is not available.")

        super().__init__("Layer Toolbox", parent)
        self._toolbox_service = toolbox_service
        self._logger = logger
        self._iface = iface
        self._updating_ui = False

        self._layer_combo = None
        self._refresh_btn = None
        self._polygon_vertices_check = None
        self._point_connections_check = None
        self._color_by_group_check = None
        self._line_width_spin = None
        self._group_field_combo = None
        self._order_field_combo = None
        self._basemap_tile_group = None
        self._basemap_tile_layout = None
        self._basemap_tile_buttons = {}
        self._focus_muac_btn = None
        self._fl_lower_field_combo = None
        self._fl_upper_field_combo = None
        self._apply_fl_rules_btn = None

        self._build_ui()
        self.refresh_layers()

    def _build_ui(self) -> None:
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self._apply_theme(body)

        hint = QLabel("Helpful layer tools for visualization and analysis.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        map_group = QGroupBox("Map view")
        map_layout = QVBoxLayout(map_group)
        map_layout.setSpacing(8)

        map_hint = QLabel("Choose a basemap via the tile. The preview shows the same map style.")
        map_hint.setWordWrap(True)
        map_layout.addWidget(map_hint)

        self._basemap_tile_group = QButtonGroup(self)
        self._basemap_tile_group.setExclusive(True)

        self._basemap_tile_layout = QGridLayout()
        self._basemap_tile_layout.setHorizontalSpacing(10)
        self._basemap_tile_layout.setVerticalSpacing(10)
        self._basemap_tile_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.addLayout(self._basemap_tile_layout)
        self._populate_basemap_tiles()

        map_buttons = QHBoxLayout()
        self._focus_muac_btn = QPushButton("Focus MUAC")
        self._focus_muac_btn.clicked.connect(self._on_focus_muac_clicked)
        map_buttons.addWidget(self._focus_muac_btn)
        map_buttons.addStretch(1)
        map_layout.addLayout(map_buttons)

        root.addWidget(map_group)

        layer_row = QHBoxLayout()
        self._layer_combo = QComboBox()
        self._layer_combo.currentIndexChanged.connect(self._on_active_layer_changed)
        layer_row.addWidget(self._layer_combo, stretch=1)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_layers)
        layer_row.addWidget(self._refresh_btn)
        root.addLayout(layer_row)

        polygon_group = QGroupBox("Polygon tools")
        polygon_form = QFormLayout(polygon_group)
        self._polygon_vertices_check = QCheckBox("Show polygon vertices")
        self._polygon_vertices_check.toggled.connect(self._on_polygon_vertices_toggled)
        polygon_form.addRow("Vertices", self._polygon_vertices_check)
        root.addWidget(polygon_group)

        point_group = QGroupBox("Point tools")
        point_form = QFormLayout(point_group)

        self._point_connections_check = QCheckBox("Connect points with lines")
        self._point_connections_check.toggled.connect(self._on_point_connections_toggled)
        point_form.addRow("Connect", self._point_connections_check)

        self._color_by_group_check = QCheckBox("Color lines by group")
        self._color_by_group_check.setChecked(True)
        self._color_by_group_check.toggled.connect(self._on_point_tool_settings_toggle_changed)
        point_form.addRow("Style", self._color_by_group_check)

        self._line_width_spin = QDoubleSpinBox()
        self._line_width_spin.setRange(0.1, 10.0)
        self._line_width_spin.setSingleStep(0.1)
        self._line_width_spin.setDecimals(1)
        self._line_width_spin.setValue(1.5)
        self._line_width_spin.valueChanged.connect(self._on_point_tool_settings_value_changed)
        point_form.addRow("Line width", self._line_width_spin)

        self._group_field_combo = QComboBox()
        self._group_field_combo.currentIndexChanged.connect(self._on_point_tool_settings_changed)
        point_form.addRow("Group by", self._group_field_combo)

        self._order_field_combo = QComboBox()
        self._order_field_combo.currentIndexChanged.connect(self._on_point_tool_settings_changed)
        point_form.addRow("Order by", self._order_field_combo)
        root.addWidget(point_group)

        fl_group = QGroupBox("Flight level tools")
        fl_form = QFormLayout(fl_group)

        self._fl_lower_field_combo = QComboBox()
        self._fl_upper_field_combo = QComboBox()
        fl_form.addRow("Lower", self._fl_lower_field_combo)
        fl_form.addRow("Upper", self._fl_upper_field_combo)

        self._apply_fl_rules_btn = QPushButton("Apply FL range rules")
        self._apply_fl_rules_btn.clicked.connect(self._on_apply_fl_rules_clicked)
        fl_form.addRow(self._apply_fl_rules_btn)

        root.addWidget(fl_group)

        root.addStretch(1)
        self.setWidget(body)
        self.setMinimumWidth(220)
        self.resize(240, self.height())

    def _apply_theme(self, body: QWidget) -> None:
        body.setStyleSheet(
            "\n".join(
                [
                    "QGroupBox { border: 1px solid #D9E3EF; border-radius: 8px; margin-top: 10px; padding: 8px; background: #FAFCFF; }",
                    "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #1E293B; font-weight: 600; }",
                    "QComboBox, QDoubleSpinBox { min-height: 26px; border: 1px solid #C9D5E6; border-radius: 6px; padding: 2px 8px; background: #FFFFFF; color: #1E293B; }",
                    "QComboBox:focus, QDoubleSpinBox:focus { border: 1px solid #3B82F6; }",
                    "QComboBox QAbstractItemView { color: #1E293B; background: #FFFFFF; selection-background-color: #BFDBFE; }",
                    "QPushButton { min-height: 28px; border: 1px solid #B6C5DA; border-radius: 6px; background: #FFFFFF; padding: 2px 10px; }",
                    "QPushButton:hover { background: #EFF6FF; }",
                    "QPushButton:pressed { background: #DBEAFE; }",
                    "QToolButton[basemapTile='true'] { border: 1px solid #C9D5E6; border-radius: 8px; background: #FFFFFF; padding: 4px; color: #0F172A; font-weight: 600; text-align: left; }",
                    "QToolButton[basemapTile='true']:hover { background: #F8FBFF; border: 1px solid #60A5FA; }",
                    "QToolButton[basemapTile='true']:checked { background: #E0F2FE; border: 2px solid #0284C7; }",
                    "QLabel { color: #1E293B; }",
                ]
            )
        )

    def _populate_basemap_tiles(self) -> None:
        if self._basemap_tile_layout is None or self._basemap_tile_group is None:
            return

        options = self._toolbox_service.list_basemap_options()
        for index, basemap in enumerate(options):
            basemap_name = str(basemap.get("name", "")).strip()
            if not basemap_name:
                continue

            button = QToolButton(self)
            button.setProperty("basemapTile", True)
            button.setCheckable(True)
            button.setToolButtonStyle(self._tool_button_icon_only())
            button.setIcon(self._placeholder_preview_icon())
            button.setIconSize(QSize(32, 32))
            button.setFixedSize(40, 40)
            button.setToolTip(basemap_name)
            button.setProperty("basemap_name", basemap_name)
            button.clicked.connect(self._on_basemap_tile_clicked)

            row = 0
            column = index
            self._basemap_tile_layout.addWidget(button, row, column)
            self._basemap_tile_group.addButton(button)
            self._basemap_tile_buttons[basemap_name] = button

            button.setIcon(self._resolve_preview_icon(basemap))

        self._sync_selected_basemap_tile()

    def _placeholder_preview_icon(self) -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(self._light_gray_color())
        return QIcon(pixmap)

    def _tool_button_icon_only(self):
        style = getattr(Qt, "ToolButtonIconOnly", None)
        if style is not None:
            return style
        tool_button_style = getattr(Qt, "ToolButtonStyle", None)
        if tool_button_style is not None:
            return tool_button_style.ToolButtonIconOnly
        raise RuntimeError("ToolButtonIconOnly is unavailable in this Qt runtime.")

    def _light_gray_color(self):
        color = getattr(Qt, "lightGray", None)
        if color is not None:
            return color
        global_color = getattr(Qt, "GlobalColor", None)
        if global_color is not None:
            return global_color.lightGray
        raise RuntimeError("lightGray color is unavailable in this Qt runtime.")

    def _resolve_preview_icon(self, basemap: dict[str, str]) -> QIcon:
        preview_file = str(basemap.get("preview_file", "")).strip()
        if preview_file:
            root_dir = Path(__file__).resolve().parent.parent
            preview_path = root_dir / preview_file
            if preview_path.exists():
                return QIcon(str(preview_path))
        return self._placeholder_preview_icon()

    def _sync_selected_basemap_tile(self) -> None:
        current_name = self._toolbox_service.current_basemap_name()
        button = self._basemap_tile_buttons.get(current_name)
        if button is None:
            button = self._basemap_tile_buttons.get(self._toolbox_service.default_basemap_name())
        if button is not None:
            button.setChecked(True)

    def refresh_layers(self) -> None:
        self._updating_ui = True
        try:
            self._layer_combo.clear()
            project = QgsProject.instance() if QgsProject else None
            if project is None:
                return

            layers = []
            for layer in project.mapLayers().values():
                if not self._is_vector_layer(layer):
                    continue
                layers.append(layer)

            layers.sort(key=lambda item: str(item.name()).casefold())
            for layer in layers:
                self._layer_combo.addItem(layer.name(), layer)

            self._sync_selected_basemap_tile()
            self._refresh_field_combos()
            self._sync_toggle_states()
        finally:
            self._updating_ui = False

    def _selected_layer(self):
        if self._layer_combo is None:
            return None
        layer = self._layer_combo.currentData()
        return layer

    def _on_active_layer_changed(self, _index: int) -> None:
        if self._updating_ui:
            return
        self._updating_ui = True
        try:
            self._refresh_field_combos()
            self._sync_toggle_states()
        finally:
            self._updating_ui = False

    def _refresh_field_combos(self) -> None:
        layer = self._selected_layer()
        self._group_field_combo.clear()
        self._order_field_combo.clear()
        self._fl_lower_field_combo.clear()
        self._fl_upper_field_combo.clear()
        self._group_field_combo.addItem("(none)", "")
        self._order_field_combo.addItem("(none)", "")
        self._fl_lower_field_combo.addItem("fl_lower", "fl_lower")
        self._fl_upper_field_combo.addItem("fl_upper", "fl_upper")

        if layer is None or not hasattr(layer, "fields"):
            return
        try:
            field_names = [str(name) for name in layer.fields().names()]
        except Exception:
            field_names = []
        for field_name in field_names:
            self._group_field_combo.addItem(field_name, field_name)
            self._order_field_combo.addItem(field_name, field_name)
            self._fl_lower_field_combo.addItem(field_name, field_name)
            self._fl_upper_field_combo.addItem(field_name, field_name)

        self._select_preferred_fl_field(self._fl_lower_field_combo, "fl_lower")
        self._select_preferred_fl_field(self._fl_upper_field_combo, "fl_upper")

    def _sync_toggle_states(self) -> None:
        layer = self._selected_layer()
        polygon_enabled = self._is_polygon_layer(layer)
        point_enabled = self._is_point_layer(layer)

        self._polygon_vertices_check.setEnabled(polygon_enabled)
        self._polygon_vertices_check.setChecked(
            bool(layer is not None and self._toolbox_service.has_vertices_helper(layer))
        )

        self._point_connections_check.setEnabled(point_enabled)
        has_connections = bool(
            layer is not None and self._toolbox_service.has_point_connections_helper(layer)
        )
        self._point_connections_check.setChecked(has_connections)

        self._group_field_combo.setEnabled(point_enabled)
        self._order_field_combo.setEnabled(point_enabled)
        self._color_by_group_check.setEnabled(point_enabled)
        self._line_width_spin.setEnabled(point_enabled)

        has_layer = layer is not None
        self._fl_lower_field_combo.setEnabled(has_layer)
        self._fl_upper_field_combo.setEnabled(has_layer)
        self._apply_fl_rules_btn.setEnabled(has_layer)

    def _on_polygon_vertices_toggled(self, checked: bool) -> None:
        if self._updating_ui:
            return
        layer = self._selected_layer()
        if layer is None:
            return
        self._toolbox_service.set_polygon_vertices_visible(layer, checked)

    def _on_point_connections_toggled(self, checked: bool) -> None:
        if self._updating_ui:
            return
        layer = self._selected_layer()
        if layer is None:
            return
        group_field = str(self._group_field_combo.currentData() or "")
        order_field = str(self._order_field_combo.currentData() or "")
        color_by_group = bool(self._color_by_group_check.isChecked())
        line_width = float(self._line_width_spin.value())
        self._toolbox_service.set_point_connections_visible(
            layer,
            checked,
            group_field=group_field,
            order_field=order_field,
            color_by_group=color_by_group,
            line_width=line_width,
        )

    def _on_point_tool_settings_changed(self, _index: int) -> None:
        if self._updating_ui:
            return
        if not self._point_connections_check.isChecked():
            return
        self._on_point_connections_toggled(True)

    def _on_point_tool_settings_toggle_changed(self, _checked: bool) -> None:
        if self._updating_ui:
            return
        if not self._point_connections_check.isChecked():
            return
        self._on_point_connections_toggled(True)

    def _on_point_tool_settings_value_changed(self, _value: float) -> None:
        if self._updating_ui:
            return
        if not self._point_connections_check.isChecked():
            return
        self._on_point_connections_toggled(True)

    def _on_basemap_tile_clicked(self) -> None:
        button = self.sender()
        basemap_name = str(button.property("basemap_name") or "").strip() if button is not None else ""
        if not basemap_name:
            basemap_name = self._toolbox_service.default_basemap_name()
        if self._toolbox_service.set_basemap(basemap_name):
            self._sync_selected_basemap_tile()
            return

        self._sync_selected_basemap_tile()

    def _on_focus_muac_clicked(self) -> None:
        self._toolbox_service.focus_muac_on_canvas(self._iface)

    def _on_apply_fl_rules_clicked(self) -> None:
        layer = self._selected_layer()
        if layer is None:
            return
        lower_field = str(self._fl_lower_field_combo.currentData() or "fl_lower")
        upper_field = str(self._fl_upper_field_combo.currentData() or "fl_upper")
        self._toolbox_service.apply_flight_level_range_rules(
            layer,
            lower_field=lower_field,
            upper_field=upper_field,
        )

    def _select_preferred_fl_field(self, combo, preferred_name: str) -> None:
        idx = combo.findData(preferred_name)
        if idx >= 0:
            combo.setCurrentIndex(idx)
            return
        preferred_key = str(preferred_name).casefold()
        for i in range(combo.count()):
            value = str(combo.itemData(i) or "")
            if value.casefold() == preferred_key:
                combo.setCurrentIndex(i)
                return

    def _is_vector_layer(self, layer) -> bool:
        if layer is None or QgsMapLayerType is None:
            return False
        layer_type = getattr(layer, "type", None)
        if not callable(layer_type):
            return False
        try:
            return layer_type() == QgsMapLayerType.VectorLayer
        except Exception:
            return False

    def _is_polygon_layer(self, layer) -> bool:
        if layer is None or QgsWkbTypes is None:
            return False
        try:
            return QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PolygonGeometry
        except Exception:
            return False

    def _is_point_layer(self, layer) -> bool:
        if layer is None or QgsWkbTypes is None:
            return False
        try:
            return QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PointGeometry
        except Exception:
            return False