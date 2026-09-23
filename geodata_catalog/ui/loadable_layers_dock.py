from __future__ import annotations

from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.models.saved_layer_view import SavedLayerView

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QIcon, QBrush
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
)


_ITEM_DATA_ROLE = getattr(Qt, "ItemDataRole", None)
USER_ROLE = getattr(Qt, "UserRole", None)
if USER_ROLE is None and _ITEM_DATA_ROLE is not None:
    USER_ROLE = _ITEM_DATA_ROLE.UserRole
def _display_category_label(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value:
        return "Miscellaneous"
    if value.casefold() == "file sources":
        return "Uncategorized"
    return value


class LoadableLayersDockWidget(QDockWidget):
    """Dock for selecting visible catalog layers and the active basemap."""

    _GEOMETRY_ICON_CACHE: dict[str, QIcon] = {}

    load_layer_requested = pyqtSignal(str, str)
    basemap_selected = pyqtSignal(str)
    saved_view_requested = pyqtSignal(str)
    saved_view_details_requested = pyqtSignal(str)
    saved_view_rename_requested = pyqtSignal(str)
    saved_view_delete_requested = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__("Data Panel", parent)
        self._rows: list[dict[str, str | LayerDefinition]] = []
        self._updating_tree = False
        self._updating_basemap = False
        self._highlighted_item = None
        self._highlighted_identity = None
        self._theme_primary = "#59A947"
        self._theme_primary_text = "#FFFFFF"
        self._theme_text = "#1E293B"
        self._build_ui()

    def _build_ui(self) -> None:
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(7)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Zoeken in panel...")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.filter_edit, stretch=1)
        self.filter_button = QToolButton()
        self.filter_button.setIcon(QIcon(":/images/themes/default/mActionFilter.svg"))
        self.filter_button.setToolTip("Expand or collapse all categories")
        self.filter_button.clicked.connect(self._toggle_categories)
        search_row.addWidget(self.filter_button)
        root.addLayout(search_row)

        self.layers_tree = QTreeWidget()
        self.layers_tree.setColumnCount(2)
        self.layers_tree.setHeaderHidden(True)
        self.layers_tree.setRootIsDecorated(True)
        self.layers_tree.setAlternatingRowColors(False)
        self.layers_tree.setUniformRowHeights(True)
        self.layers_tree.setIndentation(19)
        self.layers_tree.setSelectionMode(self._selection_mode("NoSelection"))
        header = self.layers_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, self._header_resize_mode("Stretch"))
        header.setSectionResizeMode(1, self._header_resize_mode("Fixed"))
        self.layers_tree.setColumnWidth(1, 24)
        self.layers_tree.itemClicked.connect(self._on_item_clicked)
        self.layers_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        context_policy = getattr(Qt, "CustomContextMenu", None)
        if context_policy is None:
            context_policy = Qt.ContextMenuPolicy.CustomContextMenu
        self.layers_tree.setContextMenuPolicy(context_policy)
        self.layers_tree.customContextMenuRequested.connect(self._on_context_menu_requested)
        root.addWidget(self.layers_tree, stretch=1)

        footer = QFrame()
        footer.setProperty("basemapFooter", True)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(8, 8, 8, 8)
        footer_layout.setSpacing(4)
        basemap_label = QLabel("BASEMAP")
        basemap_label.setProperty("sectionLabel", True)
        footer_layout.addWidget(basemap_label)
        basemap_row = QHBoxLayout()
        basemap_row.setSpacing(6)
        self.basemap_combo = QComboBox()
        basemap_row.addWidget(self.basemap_combo, stretch=1)
        self.project_basemap_button = QToolButton()
        self.project_basemap_button.setIcon(QIcon(":/images/themes/default/mActionAddRasterLayer.svg"))
        self.project_basemap_button.setToolTip("Projecteer geselecteerde basemap als achtergrond")
        self.project_basemap_button.clicked.connect(self._on_project_basemap_clicked)
        basemap_row.addWidget(self.project_basemap_button)
        footer_layout.addLayout(basemap_row)
        root.addWidget(footer)

        self.setWidget(body)
        self.setMinimumWidth(280)

    def apply_theme(self, ui_colors: dict[str, str]) -> None:
        primary = str(ui_colors.get("primary", "#59A947"))
        primary_text = str(ui_colors.get("primary_text", "#FFFFFF"))
        panel_background = str(ui_colors.get("panel_background", "#F7F9FC"))
        window_background = str(ui_colors.get("window_background", "#FFFFFF"))
        border = str(ui_colors.get("border", "#D7DEE8"))
        text = str(ui_colors.get("text", "#1E293B"))
        header_background = str(ui_colors.get("header_background", "#EEF3FA"))
        header_text = str(ui_colors.get("header_text", "#0F172A"))
        self._theme_primary = primary
        self._theme_primary_text = primary_text
        self._theme_text = text
        self.setStyleSheet(
            "\n".join(
                [
                    f"QDockWidget {{ background: {window_background}; color: {text}; }}",
                    f"QWidget {{ background: {window_background}; color: {text}; }}",
                    f"QLineEdit, QComboBox {{ background: #FFFFFF; color: {text}; border: 1px solid {border}; border-radius: 4px; min-height: 30px; padding: 2px 8px; }}",
                    f"QLineEdit:focus, QComboBox:focus {{ border: 1px solid {primary}; }}",
                    f"QToolButton {{ border: 1px solid {border}; border-radius: 4px; background: #FFFFFF; color: {text}; min-width: 30px; min-height: 30px; }}",
                    f"QToolButton:hover {{ border-color: {primary}; background: {header_background}; color: {header_text}; }}",
                    f"QTreeWidget {{ background: #FFFFFF; color: {text}; border: 1px solid {border}; border-radius: 4px; outline: 0; }}",
                    f"QTreeWidget::item {{ min-height: 32px; padding: 2px 6px; border-bottom: 1px solid {header_background}; }}",
                    "QTreeWidget::item:column(1) { padding-right: 6px; padding-left: 0px; }",
                    f"QTreeWidget::item:selected {{ background: transparent; color: {text}; }}",
                    f"QTreeWidget::item:selected:active {{ background: transparent; color: {text}; }}",
                    f"QTreeWidget::item:selected:!active {{ background: transparent; color: {text}; }}",
                    f"QTreeWidget::branch:selected {{ background: transparent; }}",
                    f"QTreeWidget::branch:has-children:closed, QTreeWidget::branch:has-children:open {{ color: {primary}; }}",
                    f"QFrame[basemapFooter='true'] {{ background: {panel_background}; border: 1px solid {border}; border-radius: 4px; }}",
                    f"QLabel[sectionLabel='true'] {{ color: {primary}; font-size: 10px; font-weight: 700; }}",
                ]
            )
        )

    def set_rows(
        self,
        rows: list[dict[str, str | LayerDefinition]],
        loaded_layer_keys: set[str],
        _active_color: str,
        saved_views: list[SavedLayerView] | None = None,
    ) -> None:
        self._rows = list(rows)
        self._updating_tree = True
        self._highlighted_item = None
        self.layers_tree.clear()
        grouped_rows: dict[str, list[dict[str, str | LayerDefinition]]] = {}
        views_by_layer: dict[str, list[SavedLayerView]] = {}
        for view in saved_views or []:
            views_by_layer.setdefault(f"{view.datasource_id}:{view.layer_name}", []).append(view)

        for row in rows:
            datasource_id = str(row.get("datasource_id", ""))
            display_group = str(row.get("business_group", "")).strip()
            category = _display_category_label(display_group)
            layer = row.get("layer")
            if not datasource_id or layer is None or not isinstance(layer, LayerDefinition):
                continue
            grouped_rows.setdefault(category, []).append(row)

        for category in sorted(grouped_rows.keys(), key=str.casefold):
            category_item = QTreeWidgetItem([category.upper()])
            category_item.setFirstColumnSpanned(True)
            category_item.setIcon(0, QIcon(":/images/themes/default/mActionAddGroup.svg"))
            category_font = category_item.font(0)
            category_font.setBold(True)
            category_item.setFont(0, category_font)
            category_item.setForeground(0, QColor(self._theme_primary))
            self.layers_tree.addTopLevelItem(category_item)

            category_rows = sorted(
                grouped_rows[category],
                key=lambda r: (
                    str(r.get("source_name", "")).casefold(),
                    str((r.get("layer") or LayerDefinition("", "", "", "", "")).display_name).casefold(),
                ),
            )
            for row in category_rows:
                datasource_id = str(row.get("datasource_id", ""))
                source_name = str(row.get("source_name", ""))
                source_type = str(row.get("source_type", ""))
                loadable = bool(row.get("loadable", True))
                availability_reason = str(row.get("availability_reason", "")).strip()
                layer = row.get("layer")
                if not datasource_id or layer is None or not isinstance(layer, LayerDefinition):
                    continue

                layer_key = layer.key()
                item = QTreeWidgetItem(category_item, [layer.display_name])
                item.setIcon(0, self._datasource_icon(source_type))
                geometry_icon = self._layer_icon(layer)
                if geometry_icon is not None:
                    item.setIcon(1, geometry_icon)
                item.setTextAlignment(1, self._right_alignment())
                item_payload = (datasource_id, layer.layer_name, layer_key, loadable)
                item.setData(0, USER_ROLE, item_payload)
                if self._highlighted_identity == item_payload[:3]:
                    self._set_item_highlight(item)
                item.setToolTip(
                    0,
                    f"Category: {category}\n"
                    f"Source: {source_name} ({source_type})\n"
                    f"Layer: {layer.display_name}\n"
                    f"Geometry: {layer.geometry_type or 'Unknown'}\n"
                    f"CRS: {layer.default_crs or 'Not set'}\n"
                    f"Loadable: {'Yes' if loadable else 'No'}\n"
                    "Double-click to load this layer."
                )
                if not loadable and availability_reason:
                    item.setToolTip(0, f"{item.toolTip(0)}\nReason: {availability_reason}")
                if not loadable:
                    item.setDisabled(True)

                for view in sorted(views_by_layer.get(layer_key, []), key=lambda value: value.name.casefold()):
                    view_item = QTreeWidgetItem(item, [view.name])
                    view_payload = ("saved_view", view.id)
                    view_item.setData(0, USER_ROLE, view_payload)
                    if self._highlighted_identity == view_payload:
                        self._set_item_highlight(view_item)
                    filter_text = self._saved_view_filter_text(view)
                    grouping_text = self._saved_view_grouping_text(view)
                    tooltip = (
                        f"Layer: {layer.display_name}\n"
                        f"Filter: {filter_text}\n"
                        f"Grouping: {grouping_text}\n"
                        f"Last updated: {view.updated_at}\n"
                        "Double-click to apply this saved view."
                    )
                    view_item.setToolTip(0, tooltip)

            category_item.setExpanded(True)

        self._updating_tree = False
        self._apply_filter(self.filter_edit.text())

    def refresh_loaded_state(self, loaded_layer_keys: set[str]) -> None:
        # Layer loading is triggered by a double-click; no stateful checkbox is shown.
        return

    def set_basemap_options(self, options: list[dict[str, str]], selected_name: str) -> None:
        self._updating_basemap = True
        self.basemap_combo.clear()
        for option in options:
            name = str(option.get("name", "")).strip()
            if name:
                self.basemap_combo.addItem(name, name)
        index = self.basemap_combo.findData(selected_name)
        if index >= 0:
            self.basemap_combo.setCurrentIndex(index)
        self._updating_basemap = False

    @staticmethod
    def _checked_state(checked: bool):
        value = getattr(Qt, "Checked" if checked else "Unchecked", None)
        if value is not None:
            return value
        return getattr(Qt.CheckState, "Checked" if checked else "Unchecked")

    @staticmethod
    def _right_alignment():
        alignment_flag = getattr(Qt, "AlignmentFlag", None)
        if alignment_flag is not None:
            return alignment_flag.AlignRight | alignment_flag.AlignVCenter
        return Qt.AlignRight | Qt.AlignVCenter

    @staticmethod
    def _header_resize_mode(name: str):
        resize_mode = getattr(QHeaderView, "ResizeMode", None)
        if resize_mode is not None:
            return getattr(resize_mode, name)
        return getattr(QHeaderView, name)

    @staticmethod
    def _selection_behavior(name: str):
        selection_behavior = getattr(QAbstractItemView, name, None)
        if selection_behavior is not None:
            return selection_behavior
        return getattr(QAbstractItemView.SelectionBehavior, name)

    @staticmethod
    def _selection_mode(name: str):
        selection_mode = getattr(QAbstractItemView, name, None)
        if selection_mode is not None:
            return selection_mode
        return getattr(QAbstractItemView.SelectionMode, name)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        payload = item.data(0, USER_ROLE)
        if payload and len(payload) == 2 and payload[0] == "saved_view":
            self.saved_view_requested.emit(str(payload[1]))
        elif payload and len(payload) == 4 and bool(payload[3]):
            self.load_layer_requested.emit(str(payload[0]), str(payload[1]))

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        payload = item.data(0, USER_ROLE)
        if payload and len(payload) == 4:
            self._highlighted_identity = payload[:3]
        elif payload and len(payload) == 2 and payload[0] == "saved_view":
            self._highlighted_identity = payload
        else:
            self._highlighted_identity = None
        self._set_item_highlight(item)

    def _set_item_highlight(self, item: QTreeWidgetItem) -> None:
        clear_brush = QBrush(QColor("transparent"))
        if self._highlighted_item is not None and self._highlighted_item is not item:
            for column in range(self.layers_tree.columnCount()):
                self._highlighted_item.setBackground(column, clear_brush)
                self._highlighted_item.setForeground(column, QBrush(QColor(self._theme_text)))

        highlight_brush = QBrush(QColor(self._theme_primary))
        highlight_text_brush = QBrush(QColor(self._theme_text))
        for column in range(self.layers_tree.columnCount()):
            item.setBackground(column, highlight_brush)
            item.setForeground(column, highlight_text_brush)
        self._highlighted_item = item

    def _on_context_menu_requested(self, position) -> None:
        item = self.layers_tree.itemAt(position)
        payload = item.data(0, USER_ROLE) if item is not None else None
        if not payload or len(payload) != 2 or payload[0] != "saved_view":
            return
        menu = QMenu(self.layers_tree)
        rename_action = menu.addAction("Rename Layer View")
        delete_action = menu.addAction("Delete Layer View")
        selected_action = menu.exec(self.layers_tree.viewport().mapToGlobal(position))
        view_id = str(payload[1])
        if selected_action == rename_action:
            self.saved_view_rename_requested.emit(view_id)
        elif selected_action == delete_action:
            self.saved_view_delete_requested.emit(view_id)

    @staticmethod
    def _saved_view_filter_text(view: SavedLayerView) -> str:
        filter_state = view.filter_state
        parts: list[str] = []
        flight_level = filter_state.get("flight_level", {})
        if isinstance(flight_level, dict) and flight_level.get("enabled"):
            parts.append(
                f"Flight levels {flight_level.get('mode')}: "
                f"{flight_level.get('lower')} - {flight_level.get('upper')}"
            )
        for attribute in filter_state.get("attributes", []):
            if isinstance(attribute, dict):
                label = attribute.get("label") or attribute.get("column")
                value = attribute.get("value", "")
                if label and value:
                    parts.append(f"{label}: {value}")
        return "; ".join(parts) or "None"

    @staticmethod
    def _saved_view_grouping_text(view: SavedLayerView) -> str:
        grouping = view.grouping
        if grouping.get("kind") == "field":
            return f"By {grouping.get('field', '')}"
        return str(grouping.get("kind", "none")).replace("_", " ")

    def _on_project_basemap_clicked(self) -> None:
        if not self._updating_basemap:
            self.basemap_selected.emit(str(self.basemap_combo.currentData() or ""))

    def _toggle_categories(self) -> None:
        should_expand = any(
            not self.layers_tree.topLevelItem(index).isExpanded()
            for index in range(self.layers_tree.topLevelItemCount())
        )
        for index in range(self.layers_tree.topLevelItemCount()):
            self.layers_tree.topLevelItem(index).setExpanded(should_expand)

    @staticmethod
    def _geometry_icon_kind(geometry_type: str | None) -> str:
        normalized_type = str(geometry_type or "").strip().casefold()
        if normalized_type in {"point", "multipoint"} or normalized_type.startswith("point"):
            return "point"
        if normalized_type == "circle" or normalized_type.startswith("circle"):
            return "circle"
        if normalized_type in {"line", "linestring", "multilinestring"} or normalized_type.startswith(
            ("line", "circularstring", "compoundcurve", "curve")
        ):
            return "line"
        return "polygon"

    @classmethod
    def _geometry_icon(cls, geometry_kind: str) -> QIcon:
        cached_icon = cls._GEOMETRY_ICON_CACHE.get(geometry_kind)
        if cached_icon is not None:
            return cached_icon
        icon_names = {
            "point": "mIconPointLayer.svg",
            "line": "mIconLineLayer.svg",
            "circle": "mIconCircle.svg",
            "polygon": "mIconPolygonLayer.svg",
        }
        icon = QIcon(f":/images/themes/default/{icon_names.get(geometry_kind, icon_names['polygon'])}")
        cls._GEOMETRY_ICON_CACHE[geometry_kind] = icon
        return icon

    @classmethod
    def _layer_icon(cls, layer: LayerDefinition) -> QIcon | None:
        """Return the geometry icon, retained for callers using the old helper."""
        if not str(layer.geometry_type or "").strip():
            return None
        return cls._geometry_icon(cls._geometry_icon_kind(layer.geometry_type))

    @staticmethod
    def _datasource_icon(source_type: str) -> QIcon:
        normalized_type = str(source_type or "").strip().casefold()
        if normalized_type == "oracle":
            return QIcon(":/images/themes/default/mIconDbSchema.svg")
        if normalized_type in {"geojson", "kml"}:
            return QIcon(":/images/themes/default/mIconFile.svg")
        if normalized_type == "rest":
            return QIcon(":/images/themes/default/mActionAddWmsLayer.svg")
        return QIcon(":/images/themes/default/mActionAddLayer.svg")

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().casefold()
        for index in range(self.layers_tree.topLevelItemCount()):
            category_item = self.layers_tree.topLevelItem(index)
            visible_children = 0
            for child_index in range(category_item.childCount()):
                item = category_item.child(child_index)
                visible = (
                    not needle
                    or needle in item.text(0).casefold()
                    or needle in item.toolTip(0).casefold()
                )
                item.setHidden(not visible)
                visible_children += int(visible)
            category_item.setHidden(visible_children == 0)
            if needle and visible_children:
                category_item.setExpanded(True)
