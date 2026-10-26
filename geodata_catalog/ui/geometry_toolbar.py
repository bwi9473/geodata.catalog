from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from geodata_catalog.logging_utils import PluginLogger

try:
    from qgis.core import (
        QgsApplication,
        QgsCoordinateTransform,
        QgsFeatureRequest,
        QgsGeometry,
        QgsProject,
        QgsRectangle,
    )
    from qgis.gui import QgsMapToolEmitPoint, QgsMapToolIdentify, QgsRubberBand
    from qgis.PyQt.QtCore import QPoint, QSize, Qt
    from qgis.PyQt.QtGui import QColor, QCursor, QIcon
    from qgis.PyQt.QtWidgets import (
        QDialog,
        QFrame,
        QGridLayout,
        QLabel,
        QMenu,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )
    try:
        from qgis.PyQt.QtGui import QAction
    except ImportError:
        from qgis.PyQt.QtWidgets import QAction
except ImportError:  # pragma: no cover
    QgsApplication = None
    QgsCoordinateTransform = None
    QgsFeatureRequest = None
    QgsGeometry = None
    QgsProject = None
    QgsRectangle = None
    QgsMapToolIdentify = object
    QgsMapToolEmitPoint = None
    QgsRubberBand = None
    QPoint = None
    QSize = None
    Qt = None
    QColor = None
    QCursor = None
    QIcon = None
    QAction = None
    QDialog = object
    QFrame = None
    QGridLayout = None
    QLabel = None
    QMenu = None
    QScrollArea = None
    QVBoxLayout = None
    QWidget = None


IDENTIFY_ICON_NAME = "/mActionIdentify.svg"


def _enum(owner, scope: str, member: str):
    """Resolve an enum member for both unscoped (PyQt5) and scoped (PyQt6) enums."""
    scoped = getattr(owner, scope, None)
    if scoped is not None and hasattr(scoped, member):
        return getattr(scoped, member)
    return getattr(owner, member)


def contrasting_text_color(color: str) -> str:
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    luminance = sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    return "#202020" if luminance > 0.179 else "#FFFFFF"


class IdentifyResultsPopup(QDialog):
    """Small popup listing the attributes of the identified features."""

    def __init__(self, parent, layer_blocks: list[tuple[str, list[tuple[str, str]]]]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Identify results")
        self.setWindowFlags(
            _enum(Qt, "WindowType", "Tool") | _enum(Qt, "WindowType", "WindowCloseButtonHint")
        )
        self.setStyleSheet(
            "\n".join(
                [
                    "QDialog { background: #F0F0F0; }",
                    "QFrame[identifyBlock='true'] { border: 1px solid #B8B8B8; border-radius: 4px; background: #E7E7E7; }",
                    "QLabel[identifyHeader='true'] { color: #202020; font-weight: 700; padding: 4px 2px; }",
                    "QLabel[identifyField='true'] { color: #4A4A4A; }",
                    "QLabel[identifyValue='true'] { color: #202020; }",
                ]
            )
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        for layer_name, attributes in layer_blocks:
            content_layout.addWidget(self._build_block(content, layer_name, attributes))
        content_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_enum(QFrame, "Shape", "NoFrame"))
        scroll.setWidget(content)
        root.addWidget(scroll)

        self.resize(340, min(520, 90 + 26 * sum(len(a) + 2 for _, a in layer_blocks)))

    def _build_block(self, parent, layer_name: str, attributes: list[tuple[str, str]]) -> QFrame:
        block = QFrame(parent)
        block.setProperty("identifyBlock", True)
        layout = QGridLayout(block)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(2)

        header = QLabel(layer_name, block)
        header.setProperty("identifyHeader", True)
        layout.addWidget(header, 0, 0, 1, 2)

        separator = QFrame(block)
        separator.setFrameShape(_enum(QFrame, "Shape", "HLine"))
        separator.setFrameShadow(_enum(QFrame, "Shadow", "Plain"))
        layout.addWidget(separator, 1, 0, 1, 2)

        for row, (field_name, value) in enumerate(attributes, start=2):
            name_label = QLabel(field_name, block)
            name_label.setProperty("identifyField", True)
            value_label = QLabel(value, block)
            value_label.setProperty("identifyValue", True)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(
                _enum(Qt, "TextInteractionFlag", "TextSelectableByMouse")
            )
            align_top = _enum(Qt, "AlignmentFlag", "AlignTop")
            layout.addWidget(name_label, row, 0, align_top)
            layout.addWidget(value_label, row, 1, align_top)

        layout.setColumnStretch(1, 1)
        return block


class IdentifyMapTool(QgsMapToolIdentify):
    """Map tool that shows all attributes of the clicked features."""

    MAX_RESULTS = 10
    HIGHLIGHT_COLOR = (255, 0, 0)

    def __init__(self, canvas, parent_widget, logger: PluginLogger) -> None:
        super().__init__(canvas)
        self._parent_widget = parent_widget
        self._logger = logger
        self._popup: IdentifyResultsPopup | None = None
        self._result_bands: list = []
        self.setCursor(QCursor(_enum(Qt, "CursorShape", "ArrowCursor")))

    def canvasReleaseEvent(self, event) -> None:
        pos = self._event_pos(event)
        hits = self._collect_hits(int(pos.x()), int(pos.y()))

        self._clear_bands(self._result_bands)
        self._highlight(hits, self._result_bands, self.HIGHLIGHT_COLOR, 2)

        blocks = [self._hit_to_block(hit) for hit in hits] or [("No features found", [])]
        self._show_popup(blocks, event)

    def deactivate(self) -> None:
        self.clear_highlights()
        super().deactivate()

    def clear_highlights(self) -> None:
        self._clear_bands(self._result_bands)

    def _collect_hits(self, x: int, y: int) -> list[dict]:
        hits = [
            hit
            for hit in (self._result_to_hit(result) for result in self._identify_at(x, y))
            if hit is not None
        ]
        if hits:
            return hits[: self.MAX_RESULTS]
        return self._spatial_hits(x, y, limit=self.MAX_RESULTS)

    def _identify_at(self, x: int, y: int) -> list:
        mode = _enum(QgsMapToolIdentify, "IdentifyMode", "TopDownAll")
        layer_type = _enum(QgsMapToolIdentify, "LayerType", "VectorLayer")

        try:
            results = self.identify(x, y, mode, layer_type) or []
        except Exception as exc:
            self._logger.warning(f"Identify (project layers) failed: {exc}")
            results = []

        if results:
            return list(results)

        # Layers excluded from project identification still need to be queryable here.
        layers = self._canvas_vector_layers()
        if not layers:
            return []
        try:
            return list(self.identify(x, y, layers, mode) or [])
        except Exception as exc:
            self._logger.warning(f"Identify (explicit layer list) failed: {exc}")
            return []

    def _spatial_hits(self, x: int, y: int, limit: int) -> list[dict]:
        """Query the visible vector layers directly around the given screen position."""
        if QgsRectangle is None:
            return []

        canvas = self.canvas()
        layers = self._canvas_vector_layers()
        if canvas is None or not layers:
            return []

        try:
            map_point = self.toMapCoordinates(QPoint(x, y))
            radius = self.searchRadiusMU(canvas)
        except Exception as exc:
            self._logger.error(f"Could not convert click position: {exc}")
            return []

        search_rect = QgsRectangle(
            map_point.x() - radius,
            map_point.y() - radius,
            map_point.x() + radius,
            map_point.y() + radius,
        )
        canvas_crs = canvas.mapSettings().destinationCrs()

        hits: list[dict] = []
        for layer in layers:
            try:
                layer_rect = self._to_layer_rect(search_rect, canvas_crs, layer)
                search_geometry = QgsGeometry.fromRect(layer_rect)
                for feature in layer.getFeatures(QgsFeatureRequest(layer_rect)):
                    if not self._geometry_matches(feature.geometry(), search_geometry):
                        continue
                    hits.append({"layer": layer, "feature": feature, "derived": {}})
                    if len(hits) >= limit:
                        return hits
            except Exception as exc:
                self._logger.warning(f"Spatial identify failed for layer {layer.name()}: {exc}")

        return hits

    def _geometry_matches(self, geometry, search_geometry) -> bool:
        if geometry is None or geometry.isNull():
            return False
        try:
            if geometry.intersects(search_geometry):
                return True
        except Exception:
            pass
        try:
            # Airspace polygons are often self-intersecting, which breaks the direct test.
            repaired = geometry.makeValid()
            return not repaired.isNull() and repaired.intersects(search_geometry)
        except Exception:
            return False

    def _to_layer_rect(self, rect, canvas_crs, layer):
        layer_crs = layer.crs()
        if canvas_crs == layer_crs or QgsCoordinateTransform is None:
            return rect
        transform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
        return transform.transformBoundingBox(rect)

    def _canvas_vector_layers(self) -> list:
        canvas = self.canvas()
        if canvas is None:
            return []
        layers = []
        for layer in canvas.layers() or []:
            if hasattr(layer, "fields") and hasattr(layer, "getFeatures"):
                layers.append(layer)
        return layers

    def _highlight(self, hits: list[dict], bands: list, color: tuple[int, int, int], width: int) -> None:
        canvas = self.canvas()
        if canvas is None or QgsRubberBand is None or QColor is None:
            return

        for hit in hits:
            geometry = hit["feature"].geometry()
            if geometry is None or geometry.isNull():
                continue
            try:
                band = QgsRubberBand(canvas, geometry.type())
                band.setColor(QColor(*color))
                band.setFillColor(QColor(*color, 40))
                band.setWidth(width)
                band.setToGeometry(geometry, hit["layer"])
                bands.append(band)
            except Exception as exc:
                self._logger.warning(f"Could not highlight feature: {exc}")

    def _clear_bands(self, bands: list) -> None:
        canvas = self.canvas()
        while bands:
            band = bands.pop()
            try:
                band.reset()
                if canvas is not None:
                    canvas.scene().removeItem(band)
            except Exception:
                pass

    def _result_to_hit(self, result) -> dict | None:
        layer = self._result_member(result, "mLayer", "layer")
        feature = self._result_member(result, "mFeature", "feature")
        if layer is None or feature is None:
            return None
        derived = self._result_member(result, "mDerivedAttributes", "derivedAttributes") or {}
        return {"layer": layer, "feature": feature, "derived": derived}

    def _hit_to_block(self, hit: dict) -> tuple[str, list[tuple[str, str]]]:
        attributes = self._feature_attributes(hit["feature"])
        for key, value in (hit.get("derived") or {}).items():
            attributes.append((str(key), self._format_value(value)))
        return (hit["layer"].name(), attributes)

    def _feature_attributes(self, feature) -> list[tuple[str, str]]:
        attributes: list[tuple[str, str]] = []
        for index, field in enumerate(feature.fields()):
            attributes.append((field.displayName(), self._format_value(feature[index])))
        return attributes

    @staticmethod
    def _result_member(result, member_name: str, accessor_name: str):
        value = getattr(result, member_name, None)
        if value is None:
            accessor = getattr(result, accessor_name, None)
            value = accessor() if callable(accessor) else accessor
        return value

    @staticmethod
    def _format_value(value) -> str:
        if value is None:
            return ""
        text = str(value)
        return "" if text == "NULL" else text

    def _show_popup(self, blocks, event) -> None:
        if self._popup is not None:
            self._popup.close()
            self._popup.deleteLater()

        self._popup = IdentifyResultsPopup(self._parent_widget, blocks)
        self._popup.move(self._popup_position(event))
        self._popup.show()

    def _popup_position(self, event) -> QPoint:
        try:
            global_pos = event.globalPos()
        except AttributeError:  # Qt6 removed globalPos()
            global_pos = event.globalPosition().toPoint()
        return global_pos + QPoint(12, 12)

    @staticmethod
    def _event_pos(event):
        try:
            return event.pos()
        except AttributeError:  # Qt6 removed pos()
            return event.position().toPoint()

    def close_popup(self) -> None:
        if self._popup is None:
            return
        self._popup.close()
        self._popup.deleteLater()
        self._popup = None


class GeometryToolbar:
    """QGIS toolbar with geometry tools, styled like the default QGIS toolbars."""

    OBJECT_NAME = "GeoDataCatalogGeometryToolbar"
    TITLE = "GeoData Geometry Toolbox"
    def __init__(
        self,
        iface,
        logger: PluginLogger,
        on_configuration_requested: Callable[[], None] | None = None,
        on_loadable_layers_requested: Callable[[], None] | None = None,
        on_focus_muac_requested: Callable[[], None] | None = None,
        on_save_layer_view_requested: Callable[[], None] | None = None,
        on_copy_layer_filter_requested: Callable[[], None] | None = None,
        on_place_marker_requested: Callable[[], bool] | None = None,
        on_hide_marker_requested: Callable[[], None] | None = None,
        has_saved_marker: Callable[[], bool] | None = None,
        on_marker_position_selected: Callable[[object], bool] | None = None,
        on_connect_requested: Callable[[], None] | None = None,
        on_disconnect_requested: Callable[[], bool] | None = None,
    ) -> None:
        self._iface = iface
        self._logger = logger
        self._on_configuration_requested = on_configuration_requested
        self._on_loadable_layers_requested = on_loadable_layers_requested
        self._on_focus_muac_requested = on_focus_muac_requested
        self._on_save_layer_view_requested = on_save_layer_view_requested
        self._on_copy_layer_filter_requested = on_copy_layer_filter_requested
        self._on_place_marker_requested = on_place_marker_requested
        self._on_hide_marker_requested = on_hide_marker_requested
        self._has_saved_marker = has_saved_marker
        self._on_marker_position_selected = on_marker_position_selected
        self._on_connect_requested = on_connect_requested
        self._on_disconnect_requested = on_disconnect_requested
        self._connect_action = None
        self._disconnect_action = None
        self._connection_label = None
        self._toolbar = None
        self._identify_action: QAction | None = None
        self._configuration_action: QAction | None = None
        self._loadable_layers_action: QAction | None = None
        self._focus_muac_action: QAction | None = None
        self._save_layer_view_action: QAction | None = None
        self._copy_layer_filter_action: QAction | None = None
        self._place_marker_action: QAction | None = None
        self._identify_tool: IdentifyMapTool | None = None
        self._marker_visible = False
        self._marker_map_tool = None
        self._previous_map_tool = None

    def initGui(self) -> None:
        if self._toolbar is not None:
            return

        self._toolbar = self._iface.addToolBar(self.TITLE)
        self._toolbar.setObjectName(self.OBJECT_NAME)
        self._toolbar.setIconSize(QSize(24, 24))
        self._toolbar.setStyleSheet(
            "\n".join(
                [
                    f"QToolBar#{self.OBJECT_NAME} {{ border: 1px solid #C9D5E6; border-radius: 6px;"
                    " background: #F8FBFF; padding: 1px 3px; spacing: 2px; }",
                    "QLabel[toolbarBrand='true'] { color: #64748B; font-size: 10px; font-weight: 600;"
                    " padding: 0 6px 0 2px; }",
                ]
            )
        )

        brand = QLabel("GeoData Catalog", self._toolbar)
        brand.setProperty("toolbarBrand", True)
        brand.setToolTip("GeoData Catalog geometry tools")
        self._toolbar.addWidget(brand)
        self._toolbar.addSeparator()
        self._connect_action = QAction(
            QIcon(str(Path(__file__).resolve().parent.parent / "resources" / "database_connect.svg")),
            "Connect to database",
            self._iface.mainWindow(),
        )
        self._disconnect_action = QAction(
            QIcon(str(Path(__file__).resolve().parent.parent / "resources" / "database_disconnect.svg")),
            "Disconnect database",
            self._iface.mainWindow(),
        )
        self._connect_action.triggered.connect(
            lambda: self._on_connect_requested() if self._on_connect_requested else None
        )
        self._disconnect_action.triggered.connect(
            lambda: self._on_disconnect_requested() if self._on_disconnect_requested else None
        )
        self._toolbar.addAction(self._connect_action)
        self._toolbar.addAction(self._disconnect_action)
        self._connection_label = QLabel(self._toolbar)
        self._connection_label.setTextFormat(_enum(Qt, "TextFormat", "PlainText"))
        self._toolbar.addWidget(self._connection_label)
        self._toolbar.addSeparator()
        self.set_database_connection()

        self._identify_action = QAction(
            self._identify_icon(),
            "Identify features",
            self._iface.mainWindow(),
        )
        self._identify_action.setCheckable(True)
        self._identify_action.setToolTip("Identify features: click a feature on the map to see its attributes.")
        self._identify_action.toggled.connect(self._on_identify_toggled)
        self._toolbar.addAction(self._identify_action)
        self._toolbar.addSeparator()

        self._configuration_action = QAction(
            self._configuration_icon(),
            "Open data source configuration",
            self._iface.mainWindow(),
        )
        self._configuration_action.setToolTip("Open data source configuration")
        self._configuration_action.triggered.connect(self._emit_configuration_requested)
        self._toolbar.addAction(self._configuration_action)

        self._loadable_layers_action = QAction(
            self._loadable_layers_icon(),
            "Choose map layers",
            self._iface.mainWindow(),
        )
        self._loadable_layers_action.setToolTip("Choose map layers")
        self._loadable_layers_action.triggered.connect(self._emit_loadable_layers_requested)
        self._toolbar.addAction(self._loadable_layers_action)

        self._save_layer_view_action = QAction(
            self._save_layer_view_icon(),
            "Save layer view",
            self._iface.mainWindow(),
        )
        self._save_layer_view_action.setToolTip("Save the current filter and grouping for a layer")
        self._save_layer_view_action.triggered.connect(self._emit_save_layer_view_requested)
        self._toolbar.addAction(self._save_layer_view_action)

        self._copy_layer_filter_action = QAction(
            self._copy_layer_filter_icon(),
            "Apply filter to another layer",
            self._iface.mainWindow(),
        )
        self._copy_layer_filter_action.setToolTip("Copy the current filter from one layer to another")
        self._copy_layer_filter_action.triggered.connect(self._emit_copy_layer_filter_requested)
        self._toolbar.addAction(self._copy_layer_filter_action)

        self._focus_muac_action = QAction(
            self._focus_muac_icon(),
            "Focus MUAC",
            self._iface.mainWindow(),
        )
        self._focus_muac_action.setToolTip("Focus map on the MUAC control area")
        self._focus_muac_action.triggered.connect(self._emit_focus_muac_requested)
        self._toolbar.addAction(self._focus_muac_action)

        self._toolbar.addSeparator()

        self._place_marker_action = QAction(
            self._place_marker_icon(),
            "Interactive Marker",
            self._iface.mainWindow(),
        )
        self._place_marker_action.setCheckable(True)
        self._place_marker_action.setToolTip(
            "Show or hide the interactive marker. If not configured, click the map to set its position. "
            "Right-click this button to change its position."
        )
        self._place_marker_action.toggled.connect(self._on_place_marker_toggled)
        self._toolbar.addAction(self._place_marker_action)
        marker_button = self._toolbar.widgetForAction(self._place_marker_action)
        marker_button.setContextMenuPolicy(_enum(Qt, "ContextMenuPolicy", "CustomContextMenu"))
        marker_button.customContextMenuRequested.connect(self._show_marker_context_menu)

        canvas = self._map_canvas()
        if canvas is not None:
            canvas.mapToolSet.connect(self._on_map_tool_set)

    def set_database_connection(self, label: str = "", color: str = "#F8FBFF", tooltip: str = "") -> None:
        if self._toolbar is None or self._connection_label is None:
            return
        background = QColor(color)
        foreground = contrasting_text_color(background.name())
        self._toolbar.setStyleSheet(
            f"QToolBar#{self.OBJECT_NAME} {{ background: {background.name()}; padding: 1px 3px; spacing: 2px; }}"
            f"QToolBar#{self.OBJECT_NAME} QLabel {{ color: {foreground}; padding: 2px 6px; font-weight: 600; }}"
        )
        self._connection_label.setText(label or "Database disconnected")
        self._connection_label.setToolTip(tooltip or "Use Connect to log in to a configured database.")
        self._connect_action.setEnabled(not bool(label))
        self._disconnect_action.setEnabled(bool(label))

    def unload(self) -> None:
        self._deactivate_marker_mode()
        canvas = self._map_canvas()
        if canvas is not None:
            try:
                canvas.mapToolSet.disconnect(self._on_map_tool_set)
            except (TypeError, RuntimeError):
                pass
            if self._identify_tool is not None and canvas.mapTool() == self._identify_tool:
                canvas.unsetMapTool(self._identify_tool)

        if self._identify_tool is not None:
            self._identify_tool.close_popup()
            self._identify_tool = None

        if self._toolbar is not None:
            self._toolbar.deleteLater()
            self._toolbar = None
        self._identify_action = None
        self._configuration_action = None
        self._loadable_layers_action = None
        self._focus_muac_action = None
        self._save_layer_view_action = None
        self._copy_layer_filter_action = None
        self._place_marker_action = None
        self._marker_map_tool = None
        self._marker_visible = False
        self._connect_action = None
        self._disconnect_action = None
        self._connection_label = None

    def _identify_icon(self) -> QIcon:
        if QgsApplication is not None:
            icon = QgsApplication.getThemeIcon(IDENTIFY_ICON_NAME)
            if not icon.isNull():
                return icon
        return QIcon(":/images/themes/default/mActionIdentify.svg")

    def _loadable_layers_icon(self) -> QIcon:
        if QgsApplication is not None:
            icon = QgsApplication.getThemeIcon("/mActionAddLayer.svg")
            if not icon.isNull():
                return icon
        return QIcon(":/images/themes/default/mActionAddLayer.svg")

    def _configuration_icon(self) -> QIcon:
        if QgsApplication is not None:
            icon = QgsApplication.getThemeIcon("/mActionOptions.svg")
            if not icon.isNull():
                return icon
        return QIcon(":/images/themes/default/mActionOptions.svg")

    def _focus_muac_icon(self) -> QIcon:
        if QgsApplication is not None:
            icon = QgsApplication.getThemeIcon("/mActionZoomToLayer.svg")
            if not icon.isNull():
                return icon
        return QIcon(":/images/themes/default/mActionZoomToArea.svg")

    def _save_layer_view_icon(self) -> QIcon:
        if QgsApplication is not None:
            icon = QgsApplication.getThemeIcon("/mActionFileSave.svg")
            if not icon.isNull():
                return icon
        return QIcon(":/images/themes/default/mActionFileSave.svg")

    def _copy_layer_filter_icon(self) -> QIcon:
        if QgsApplication is not None:
            icon = QgsApplication.getThemeIcon("/mActionEditCopy.svg")
            if not icon.isNull():
                return icon
        return QIcon(":/images/themes/default/mActionEditCopy.svg")

    def _place_marker_icon(self) -> QIcon:
        if QgsApplication is not None:
            icon = QgsApplication.getThemeIcon("/mActionCapturePoint.svg")
            if not icon.isNull():
                return icon
        return QIcon(":/images/themes/default/mActionCapturePoint.svg")

    def _emit_loadable_layers_requested(self, _checked: bool = False) -> None:
        if self._on_loadable_layers_requested is not None:
            self._on_loadable_layers_requested()

    def _emit_configuration_requested(self, _checked: bool = False) -> None:
        if self._on_configuration_requested is not None:
            self._on_configuration_requested()

    def _emit_focus_muac_requested(self, _checked: bool = False) -> None:
        if self._on_focus_muac_requested is not None:
            self._on_focus_muac_requested()

    def _emit_save_layer_view_requested(self, _checked: bool = False) -> None:
        if self._on_save_layer_view_requested is not None:
            self._on_save_layer_view_requested()

    def _emit_copy_layer_filter_requested(self, _checked: bool = False) -> None:
        if self._on_copy_layer_filter_requested is not None:
            self._on_copy_layer_filter_requested()

    def _map_canvas(self):
        if self._iface is None:
            return None
        return getattr(self._iface, "mapCanvas", lambda: None)()

    def _on_identify_toggled(self, enabled: bool) -> None:
        canvas = self._map_canvas()
        if canvas is None:
            return

        if not enabled:
            if self._identify_tool is not None:
                self._identify_tool.close_popup()
                if canvas.mapTool() == self._identify_tool:
                    canvas.unsetMapTool(self._identify_tool)
            return

        if self._identify_tool is None:
            self._identify_tool = IdentifyMapTool(canvas, self._iface.mainWindow(), self._logger)
            self._identify_tool.setAction(self._identify_action)
        canvas.setMapTool(self._identify_tool)

    def _on_place_marker_toggled(self, enabled: bool) -> None:
        self._logger.info(f"Marker toolbar toggled: enabled={enabled} visible={self._marker_visible}")

        if not enabled:
            self._deactivate_marker_mode()
            if self._marker_visible and self._on_hide_marker_requested is not None:
                self._on_hide_marker_requested()
            self._marker_visible = False
            return

        if self._has_saved_marker is not None and not self._has_saved_marker():
            self._activate_marker_mode()
            return

        self._logger.info("Marker toolbar toggle-on requested stored marker display.")
        shown = False
        if self._on_place_marker_requested is not None:
            shown = bool(self._on_place_marker_requested())
        self._logger.info(f"Stored marker display callback finished: shown={shown}.")
        self._marker_visible = shown
        self._sync_marker_action()

    def _sync_marker_action(self) -> None:
        if self._place_marker_action is not None:
            blocked = self._place_marker_action.blockSignals(True)
            self._place_marker_action.setChecked(self._marker_visible)
            self._place_marker_action.blockSignals(blocked)

    def _show_marker_context_menu(self, position) -> None:
        button = self._toolbar.widgetForAction(self._place_marker_action)
        menu = QMenu(button)
        configured = self._has_saved_marker is not None and self._has_saved_marker()
        action = menu.addAction("Change marker position..." if configured else "Set marker position...")
        action.triggered.connect(self._activate_marker_mode)
        execute = getattr(menu, "exec", None) or menu.exec_
        execute(button.mapToGlobal(position))

    def _activate_marker_mode(self, _checked: bool = False) -> None:
        canvas = self._map_canvas()
        if canvas is None or QgsMapToolEmitPoint is None or self._on_marker_position_selected is None:
            self._logger.warning("Cannot set marker position: map tool or position callback unavailable.")
            self._sync_marker_action()
            return
        if self._marker_map_tool is None:
            self._marker_map_tool = QgsMapToolEmitPoint(canvas)
            self._marker_map_tool.canvasClicked.connect(self._on_canvas_marker_clicked)
        if canvas.mapTool() != self._marker_map_tool:
            self._previous_map_tool = canvas.mapTool()
            canvas.setMapTool(self._marker_map_tool)

    def _deactivate_marker_mode(self) -> None:
        canvas = self._map_canvas()
        if canvas is not None and self._marker_map_tool is not None and canvas.mapTool() == self._marker_map_tool:
            previous = self._previous_map_tool
            self._previous_map_tool = None
            if previous is not None:
                canvas.setMapTool(previous)
            else:
                canvas.unsetMapTool(self._marker_map_tool)

    def _on_canvas_marker_clicked(self, point, button) -> None:
        if button == _enum(Qt, "MouseButton", "RightButton"):
            self._deactivate_marker_mode()
            self._sync_marker_action()
            return
        if button != _enum(Qt, "MouseButton", "LeftButton"):
            return
        if self._on_marker_position_selected is None or not self._on_marker_position_selected(point):
            self._logger.warning("Could not save the interactive marker position; placement remains active.")
            return
        self._marker_visible = True
        self._deactivate_marker_mode()
        self._sync_marker_action()

    def _on_map_tool_set(self, new_tool, _old_tool=None) -> None:
        if self._marker_map_tool is not None and new_tool != self._marker_map_tool:
            self._sync_marker_action()
        if self._identify_action is not None:
            is_active = self._identify_tool is not None and new_tool == self._identify_tool
            if self._identify_action.isChecked() != is_active:
                self._identify_action.setChecked(is_active)
