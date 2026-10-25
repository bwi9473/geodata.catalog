from __future__ import annotations

from pathlib import Path

from geodata_catalog.models.datasource import Datasource, DatasourceType
from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.services.style_service import generate_style_preview_icon

from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFrame,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qgis.PyQt.QtGui import QIcon, QColor, QPalette


USER_ROLE = getattr(Qt, "UserRole", Qt.ItemDataRole.UserRole)
_CUSTOM_CTX = getattr(Qt, "CustomContextMenu", None) or Qt.ContextMenuPolicy.CustomContextMenu


def _resolve_no_item_flags():
    no_item_flags = getattr(Qt, "NoItemFlags", None)
    if no_item_flags is not None:
        return no_item_flags

    item_flag_enum = getattr(Qt, "ItemFlag", None)
    if item_flag_enum is not None:
        no_item_flags = getattr(item_flag_enum, "NoItemFlags", None)
        if no_item_flags is not None:
            return no_item_flags

    item_flags_type = getattr(Qt, "ItemFlags", None)
    if callable(item_flags_type):
        try:
            return item_flags_type()
        except Exception:
            return None

    return None


_NO_ITEM_FLAGS = _resolve_no_item_flags()


def _display_category_label(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value:
        return "Miscellaneous"
    if value.casefold() == "file sources":
        return "Uncategorized"
    return value


def _style_display_name(style_file: str) -> str:
    return Path(style_file).stem or style_file


class CatalogDockWidget(QDockWidget):
    """Developer dock for managing datasources and layer configuration."""

    add_source_requested = pyqtSignal()
    export_requested = pyqtSignal()
    edit_source_requested = pyqtSignal(str)
    delete_source_requested = pyqtSignal(str)
    refresh_requested = pyqtSignal(str)
    edit_layer_config_requested = pyqtSignal(str, str)  # datasource_id, layer_name

    def __init__(self, parent=None) -> None:
        super().__init__("Data Source Configuration", parent)
        self._datasource_items: dict[str, QTreeWidgetItem] = {}
        self._datasources: list[Datasource] = []
        self._layers_by_datasource: dict[str, list[LayerDefinition]] = {}
        self._grouping_mode = "datasource"
        self._rendering_tree = False
        self._all_layers_mode = False
        self._build_ui()

    def _build_ui(self) -> None:
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        hint = QLabel("Manage data sources and configure their layers.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(4, 0, 4, 0)
        action_row.setSpacing(3)
        self.add_btn = self._toolbar_button(
            ":/images/themes/default/mActionAddLayer.svg", "Add Source"
        )
        self.edit_btn = self._toolbar_button(
            ":/images/themes/default/mActionOptions.svg", "Edit Source"
        )
        self.delete_btn = self._toolbar_button(
            ":/images/themes/default/mActionDeleteSelected.svg", "Delete Source"
        )
        self.refresh_btn = self._toolbar_button(
            ":/images/themes/default/mActionRefresh.svg", "Refresh Source"
        )
        self.export_btn = self._toolbar_button(
            ":/images/themes/default/mActionFileSave.svg",
            "Export Layer Configuration",
        )
        self.add_btn.clicked.connect(self.add_source_requested.emit)
        self.edit_btn.clicked.connect(self._emit_edit)
        self.delete_btn.clicked.connect(self._emit_delete)
        self.refresh_btn.clicked.connect(self._emit_refresh)
        self.export_btn.clicked.connect(self.export_requested.emit)
        for button in (
            self.add_btn,
            self.edit_btn,
            self.delete_btn,
            self.refresh_btn,
            self.export_btn,
        ):
            action_row.addWidget(button)
        action_row.addStretch(1)
        root.addLayout(action_row)

        grouping_toolbox = QFrame()
        grouping_toolbox.setProperty("groupingToolbox", True)
        grouping_row = QHBoxLayout(grouping_toolbox)
        grouping_row.setContentsMargins(6, 3, 6, 3)
        grouping_row.setSpacing(6)
        grouping_row.addWidget(QLabel("Group by"))
        self.grouping_combo = QComboBox()
        self.grouping_combo.addItems(["Datasource", "Category"])
        self.grouping_combo.setToolTip("Choose how sources and layers are grouped")
        self.grouping_combo.currentTextChanged.connect(self._on_grouping_changed)
        grouping_row.addWidget(self.grouping_combo)
        grouping_row.addStretch(1)
        root.addWidget(grouping_toolbox)

        explore_group = QGroupBox("Configuration")
        explore_layout = QVBoxLayout(explore_group)
        explore_layout.setSpacing(8)

        self.datasource_tree = QTreeWidget()
        self.datasource_tree.setColumnCount(2)
        self.datasource_tree.setHeaderHidden(True)
        tree_header = self.datasource_tree.header()
        resize_mode = getattr(QHeaderView, "ResizeMode", QHeaderView)
        tree_header.setStretchLastSection(False)
        tree_header.setSectionResizeMode(0, getattr(resize_mode, "Stretch"))
        tree_header.setSectionResizeMode(1, getattr(resize_mode, "Fixed"))
        self.datasource_tree.setColumnWidth(1, 96)
        self.datasource_tree.itemSelectionChanged.connect(self._on_datasource_changed)
        self.datasource_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        explore_layout.addWidget(self.datasource_tree, stretch=2)

        self.layers_list = QListWidget()

        root.addWidget(explore_group)

        self.setWidget(body)

    def _toolbar_button(self, icon_path: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setIcon(QIcon(icon_path))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(28, 28)
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        return button

    def _on_grouping_changed(self, value: str) -> None:
        self._set_grouping_mode("category" if value == "Category" else "datasource")

    def apply_theme(self, ui_colors: dict[str, str]) -> None:
        primary = str(ui_colors.get("primary", "#59A947"))
        primary_text = str(ui_colors.get("primary_text", "#FFFFFF"))
        panel_background = str(ui_colors.get("panel_background", "#F7F9FC"))
        window_background = str(ui_colors.get("window_background", "#FFFFFF"))
        border = str(ui_colors.get("border", "#D7DEE8"))
        text = str(ui_colors.get("text", "#1E293B"))
        header_background = str(ui_colors.get("header_background", "#EEF3FA"))
        header_text = str(ui_colors.get("header_text", "#0F172A"))
        hover_background = str(ui_colors.get("hover_background", "#F3F9F4"))
        category_text = str(ui_colors.get("category_text", "#2E7D32"))
        dataset_text = str(ui_colors.get("dataset_text", "#2B2B2B"))
        selection_background = str(ui_colors.get("selection_background", "#CFE8D1"))
        selection_text = str(ui_colors.get("selection_text", "#172A1B"))
        self.setStyleSheet(
            "\n".join(
                [
                    f"QDockWidget {{ background: {window_background}; color: {text}; }}",
                    f"QWidget {{ background: {window_background}; color: {text}; }}",
                    f"QGroupBox {{ background: {panel_background}; color: {header_text}; border: 1px solid {border}; border-radius: 4px; margin-top: 12px; padding: 8px; font-weight: 700; }}",
                    "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }",
                    f"QTreeWidget, QListWidget {{ background: {panel_background}; color: {dataset_text}; border: 1px solid {border}; border-radius: 4px; outline: 0; }}",
                    f"QTreeWidget::item {{ color: {dataset_text}; }}",
                    f"QTreeWidget::item:has-children {{ color: {category_text}; }}",
                    f"QTreeWidget::item, QListWidget::item {{ min-height: 30px; padding: 2px 6px; border-bottom: 1px solid {header_background}; }}",
                    f"QTreeWidget::item:selected, QListWidget::item:selected {{ background: {selection_background}; color: {selection_text}; }}",
                    f"QFrame[groupingToolbox='true'] {{ background: {panel_background}; border: 1px solid {border}; border-radius: 3px; }}",
                    f"QFrame[groupingToolbox='true'] QLabel {{ color: {header_text}; font-weight: 600; }}",
                    f"QFrame[groupingToolbox='true'] QComboBox {{ min-height: 24px; padding: 1px 22px 1px 6px; background: {window_background}; color: {text}; border: 1px solid {border}; border-radius: 3px; }}",
                    f"QPushButton {{ background: {window_background}; color: {text}; border: 1px solid {border}; border-radius: 4px; min-height: 30px; padding: 2px 8px; }}",
                    f"QPushButton:hover {{ border-color: {primary}; background: {hover_background}; color: {header_text}; }}",
                    f"QPushButton:pressed {{ background: {primary}; color: {primary_text}; }}",
                    f"QPushButton:disabled {{ color: {border}; background: {panel_background}; }}",
                    f"QToolButton {{ color: {text}; border: 1px solid transparent; border-radius: 3px; padding: 2px; }}",
                    f"QToolButton:hover {{ background: {hover_background}; border-color: {border}; }}",
                    f"QToolButton:pressed {{ background: {primary}; border-color: {primary}; }}",
                    f"QToolButton:checked {{ background: {primary}; color: {primary_text}; border-color: {primary}; }}",
                ]
            )
        )
        self._apply_selection_palette(self.datasource_tree, selection_background, selection_text)

    @staticmethod
    def _apply_selection_palette(widget, background: str, text: str) -> None:
        palette = widget.palette()
        color_role = getattr(QPalette, "ColorRole", None)
        highlight_role = getattr(color_role, "Highlight", None) if color_role else getattr(QPalette, "Highlight")
        highlighted_text_role = (
            getattr(color_role, "HighlightedText", None)
            if color_role
            else getattr(QPalette, "HighlightedText")
        )
        palette.setColor(highlight_role, QColor(background))
        palette.setColor(highlighted_text_role, QColor(text))
        widget.setPalette(palette)

    def set_datasources(
        self,
        datasources: list[Datasource],
        layers_by_datasource: dict[str, list[LayerDefinition]] | None = None,
    ) -> None:
        self._datasources = list(datasources)
        self._layers_by_datasource = {
            datasource_id: list(layers)
            for datasource_id, layers in (layers_by_datasource or {}).items()
        }
        self._render_tree()

    def _set_grouping_mode(self, mode: str) -> None:
        if mode not in {"datasource", "category"}:
            return
        self._grouping_mode = mode
        self._render_tree()

    def _render_tree(self) -> None:
        self._rendering_tree = True
        try:
            self.datasource_tree.clear()
            self._datasource_items.clear()
            if self._grouping_mode == "category":
                self._render_category_tree()
            else:
                self._render_datasource_tree()
        finally:
            self._rendering_tree = False

    def _render_datasource_tree(self) -> None:
        file_layers: dict[DatasourceType, list[LayerDefinition]] = {
            DatasourceType.KML: [],
            DatasourceType.GEOJSON: [],
        }
        for datasource in self._datasources:
            layers = self._layers_by_datasource.get(datasource.id, [])
            if datasource.datasource_type in file_layers:
                file_layers[datasource.datasource_type].extend(layers)
                continue
            self._add_datasource_item(datasource, layers)

        for datasource_type, layers in file_layers.items():
            if not any(
                datasource.datasource_type is datasource_type for datasource in self._datasources
            ):
                continue
            type_label = datasource_type.value.upper()
            type_item = QTreeWidgetItem([f"{type_label} (COUNT = {len(layers)})"])
            type_item.setIcon(0, self._datasource_icon(datasource_type))
            self.datasource_tree.addTopLevelItem(type_item)
            self._add_layer_items(type_item, layers)
            type_item.setExpanded(False)

    def _render_category_tree(self) -> None:
        grouped_layers: dict[str, list[tuple[LayerDefinition, DatasourceType]]] = {}
        for datasource in self._datasources:
            datasource_type = datasource.datasource_type
            for layer in self._layers_by_datasource.get(datasource.id, []):
                category = _display_category_label(layer.business_group or "")
                grouped_layers.setdefault(category, []).append((layer, datasource_type))

        for category in sorted(grouped_layers, key=str.casefold):
            category_layers = grouped_layers[category]
            category_item = QTreeWidgetItem(
                [f"{category} (COUNT = {len(category_layers)})"]
            )
            self.datasource_tree.addTopLevelItem(category_item)
            for layer, datasource_type in sorted(
                category_layers, key=lambda value: value[0].display_name.casefold()
            ):
                self._add_layer_item(
                    category_item,
                    layer,
                    category,
                    self._datasource_icon(datasource_type),
                )
            category_item.setExpanded(False)

    def _add_datasource_item(
        self,
        datasource: Datasource,
        layers: list[LayerDefinition],
        parent_item: QTreeWidgetItem | None = None,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([f"{datasource.name} (COUNT = {len(layers)})"])
        item.setData(0, USER_ROLE, datasource.id)
        item.setIcon(0, self._datasource_icon(datasource.datasource_type))
        self._datasource_items[datasource.id] = item
        if parent_item is None:
            self.datasource_tree.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
        self._add_layer_items(item, layers)
        item.setExpanded(False)
        return item

    @staticmethod
    def _datasource_icon(datasource_type: DatasourceType) -> QIcon:
        icon_paths = {
            DatasourceType.ORACLE: ":/images/themes/default/mIconDbSchema.svg",
            DatasourceType.GEOJSON: ":/images/themes/default/mIconFile.svg",
            DatasourceType.KML: ":/images/themes/default/mIconFile.svg",
            DatasourceType.REST: ":/images/themes/default/mActionAddWmsLayer.svg",
        }
        return QIcon(icon_paths.get(datasource_type, ":/images/themes/default/mActionAddLayer.svg"))

    def set_layers(self, datasource_id: str, layers: list[LayerDefinition]) -> None:
        self._all_layers_mode = False
        self.layers_list.clear()
        self._layers_by_datasource[datasource_id] = list(layers)
        if self._grouping_mode == "category":
            self._render_tree()
            return
        datasource_item = self._datasource_items.get(datasource_id)
        if datasource_item is None:
            return
        datasource_item.setText(0, self._datasource_label(datasource_item, len(layers)))
        self._remove_layer_items(datasource_item)
        self._add_layer_items(datasource_item, layers)

    def _datasource_label(self, item: QTreeWidgetItem, count: int) -> str:
        label = item.text(0)
        if " (COUNT = " in label:
            label = label.split(" (COUNT = ", 1)[0]
        return f"{label} (COUNT = {count})"

    def _remove_layer_items(self, datasource_item: QTreeWidgetItem) -> None:
        while datasource_item.childCount():
            datasource_item.takeChild(0)

    def _add_layer_items(
        self, datasource_item: QTreeWidgetItem, layers: list[LayerDefinition]
    ) -> None:
        grouped_layers: dict[str, list[LayerDefinition]] = {}
        for layer in layers:
            category = _display_category_label(layer.business_group or "")
            grouped_layers.setdefault(category, []).append(layer)

        for category in sorted(grouped_layers, key=str.casefold):
            category_layers = grouped_layers[category]
            category_item = QTreeWidgetItem([f"{category} (COUNT = {len(category_layers)})"])
            datasource_item.addChild(category_item)
            for layer in sorted(category_layers, key=lambda value: value.display_name.casefold()):
                self._add_layer_item(category_item, layer, category)

    def _add_layer_item(
        self,
        parent_item: QTreeWidgetItem,
        layer: LayerDefinition,
        category: str,
        icon: QIcon | None = None,
    ) -> None:
        item = QTreeWidgetItem([layer.display_name, ""])
        item.setData(0, USER_ROLE, (layer.datasource_id, layer.layer_name))
        if icon is None:
            icon = generate_style_preview_icon(layer.default_style_file)
        if icon is not None:
            item.setIcon(0, icon)
        item.setToolTip(0,
            f"Category: {category}\n{layer.display_name}\n"
            f"Geometry: {layer.geometry_type or 'Unknown'}\n"
            f"CRS: {layer.default_crs or 'Not set'}\n"
            f"Count: {layer.feature_count if layer.feature_count is not None else 'Unknown'}"
            + (f"\nStyle: {_style_display_name(layer.default_style_file)}" if layer.default_style_file else "")
        )
        parent_item.addChild(item)
        edit_button = QToolButton(self.datasource_tree)
        edit_button.setAutoRaise(True)
        edit_button.setFixedSize(90, 28)
        edit_button.setIconSize(QSize(16, 16))
        edit_button.setText("Edit Layer")
        tool_button_style = getattr(Qt, "ToolButtonTextBesideIcon", None)
        if tool_button_style is None:
            tool_button_style = Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        edit_button.setToolButtonStyle(tool_button_style)
        edit_button.setToolTip("Edit the layer configuration")
        edit_button.setIcon(self._edit_icon())
        edit_button.clicked.connect(
            lambda _checked=False, datasource_id=layer.datasource_id, layer_name=layer.layer_name:
            self.edit_layer_config_requested.emit(datasource_id, layer_name)
        )
        self.datasource_tree.setItemWidget(item, 1, edit_button)

    @staticmethod
    def _edit_icon():
        icon = QIcon(":/images/themes/default/mActionOptions.svg")
        if icon.isNull():
            standard_pixmap = getattr(QStyle, "SP_FileDialogDetailedView", None)
            if standard_pixmap is None:
                standard_pixmap = getattr(
                    getattr(QStyle, "StandardPixmap", None),
                    "SP_FileDialogDetailedView",
                    None,
                )
            if standard_pixmap is not None:
                icon = QApplication.style().standardIcon(standard_pixmap)
        return icon

    def set_all_layers(self, rows: list[dict[str, str | LayerDefinition]]) -> None:
        """Render one combined list with loadable layers from all datasources."""
        self._all_layers_mode = True
        self.layers_list.clear()
        unavailable_header_added = False
        grouped_rows: dict[str, list[dict[str, str | LayerDefinition]]] = {}
        for row in rows:
            datasource_id = str(row.get("datasource_id", ""))
            source_name = str(row.get("source_name", ""))
            source_type = str(row.get("source_type", ""))
            loadable = bool(row.get("loadable", True))
            availability_reason = str(row.get("availability_reason", "")).strip()
            layer = row.get("layer")
            if not datasource_id or layer is None:
                continue
            if not isinstance(layer, LayerDefinition):
                continue

            if not loadable and availability_reason and not unavailable_header_added:
                header_item = QListWidgetItem("Database not available")
                header_item.setToolTip(
                    "These layers are visible from configuration, but cannot be loaded right now."
                )
                header_font = header_item.font()
                header_font.setBold(True)
                header_item.setFont(header_font)
                if _NO_ITEM_FLAGS is not None:
                    header_item.setFlags(_NO_ITEM_FLAGS)
                self.layers_list.addItem(header_item)
                unavailable_header_added = True

            display_group = str(row.get("business_group", layer.business_group)).strip()
            category = _display_category_label(display_group)
            grouped_rows.setdefault(category, []).append(row)

        for category in sorted(grouped_rows.keys(), key=str.casefold):
            header_item = QListWidgetItem(f"Category: {category}")
            header_font = header_item.font()
            header_font.setBold(True)
            header_item.setFont(header_font)
            if _NO_ITEM_FLAGS is not None:
                header_item.setFlags(_NO_ITEM_FLAGS)
            self.layers_list.addItem(header_item)

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

                display_name = layer.display_name if loadable else f"{layer.display_name} (unavailable)"
                item = QListWidgetItem(f"  [{source_name}] {display_name}")
                item.setData(USER_ROLE, (datasource_id, layer.layer_name, loadable))
                style_icon = generate_style_preview_icon(layer.default_style_file)
                if style_icon is not None:
                    item.setIcon(style_icon)
                item.setToolTip(
                    f"Category: {category}\n"
                    f"Source: {source_name} ({source_type})\n"
                    f"Layer: {layer.display_name}\n"
                    f"Geometry: {layer.geometry_type or 'Unknown'}\n"
                    f"CRS: {layer.default_crs or 'Not set'}\n"
                    f"Count: {layer.feature_count if layer.feature_count is not None else 'Unknown'}\n"
                    f"Loadable: {'Yes' if loadable else 'No'}"
                    + (f"\nStyle: {_style_display_name(layer.default_style_file)}" if layer.default_style_file else "")
                )
                if not loadable and availability_reason:
                    item.setToolTip(f"{item.toolTip()}\nReason: {availability_reason}")
                self.layers_list.addItem(item)

    def is_show_all_layers_enabled(self) -> bool:
        return self._all_layers_mode

    def selected_datasource_id(self) -> str | None:
        item = self.datasource_tree.currentItem()
        if item is None:
            return None
        payload = item.data(0, USER_ROLE)
        if isinstance(payload, str):
            return payload
        if isinstance(payload, tuple) and payload:
            return payload[0]
        parent = item.parent()
        while parent is not None:
            parent_payload = parent.data(0, USER_ROLE)
            if isinstance(parent_payload, str):
                return parent_payload
            parent = parent.parent()
        return None

    def _on_datasource_changed(self) -> None:
        if self._all_layers_mode or self._rendering_tree:
            return
        item = self.datasource_tree.currentItem()
        datasource_id = item.data(0, USER_ROLE) if item is not None else None
        if isinstance(datasource_id, str):
            self.refresh_requested.emit(datasource_id)

    def _emit_edit(self) -> None:
        datasource_id = self.selected_datasource_id()
        if datasource_id:
            self.edit_source_requested.emit(datasource_id)

    def _emit_delete(self) -> None:
        datasource_id = self.selected_datasource_id()
        if datasource_id:
            self.delete_source_requested.emit(datasource_id)

    def _emit_refresh(self) -> None:
        datasource_id = self.selected_datasource_id()
        if datasource_id:
            self.refresh_requested.emit(datasource_id)

    def _emit_edit_layer_config(self) -> None:
        self._emit_selected_layer_config()

    def _emit_selected_layer_config(self) -> None:
        item = self.datasource_tree.currentItem()
        payload = item.data(0, USER_ROLE) if item is not None else None
        if isinstance(payload, tuple) and len(payload) >= 2:
            self.edit_layer_config_requested.emit(payload[0], payload[1])

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        payload = item.data(0, USER_ROLE)
        if isinstance(payload, tuple) and len(payload) >= 2:
            self.edit_layer_config_requested.emit(payload[0], payload[1])

    def _on_layer_double_clicked(self, item: QListWidgetItem) -> None:
        payload = item.data(USER_ROLE)
        if not payload or len(payload) < 2:
            return
        datasource_id, layer_name = payload[0], payload[1]
        self.edit_layer_config_requested.emit(datasource_id, layer_name)

    def _on_layers_context_menu(self, pos) -> None:
        item = self.layers_list.itemAt(pos)
        if item is None:
            return
        payload = item.data(USER_ROLE)
        if not payload or len(payload) < 2:
            return
        datasource_id, layer_name = payload[0], payload[1]
        loadable = True if len(payload) < 3 else bool(payload[2])
        menu = QMenu(self)
        edit_config_action = menu.addAction("Edit Layer Config…")
        chosen = menu.exec(self.layers_list.viewport().mapToGlobal(pos))
        if chosen == edit_config_action:
            self.edit_layer_config_requested.emit(datasource_id, layer_name)
