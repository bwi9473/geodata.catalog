from __future__ import annotations

from pathlib import Path

from geodata_catalog.models.datasource import Datasource, DatasourceType
from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.services.style_service import generate_style_preview_icon
from geodata_catalog.ui.catalog_layout import (
    CatalogNavigation,
    CollapsibleSection,
    catalog_styles,
)

from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFrame,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSplitter,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qgis.PyQt.QtGui import QIcon, QColor, QPalette


_ITEM_DATA_ROLE = getattr(Qt, "ItemDataRole", None)
USER_ROLE = getattr(Qt, "UserRole", None)
if USER_ROLE is None and _ITEM_DATA_ROLE is not None:
    USER_ROLE = _ITEM_DATA_ROLE.UserRole

_CONTEXT_MENU_POLICY = getattr(Qt, "ContextMenuPolicy", None)
_CUSTOM_CTX = getattr(Qt, "CustomContextMenu", None)
if _CUSTOM_CTX is None and _CONTEXT_MENU_POLICY is not None:
    _CUSTOM_CTX = _CONTEXT_MENU_POLICY.CustomContextMenu


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
        self._selected_group = ""
        self._build_ui()

    def _build_ui(self) -> None:
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        workspace = QSplitter(self._orientation("Horizontal"))
        self.navigation = CatalogNavigation("Manage catalog")
        self.navigation.selection_changed.connect(self._on_navigation_changed)
        workspace.addWidget(self.navigation)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 0, 0, 0)
        content_layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Search layers, sources, or categories...")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.filter_edit, stretch=1)

        self.grouping_combo = QComboBox()
        self.grouping_combo.addItems(["Datasource", "Category"])
        self.grouping_combo.setToolTip("Choose how sources and layers are grouped")
        self.grouping_combo.currentTextChanged.connect(self._on_grouping_changed)
        toolbar.addWidget(self.grouping_combo)
        self.add_btn = QPushButton("Add source")
        self.add_btn.setIcon(QIcon(":/images/themes/default/mActionAddLayer.svg"))
        toolbar.addWidget(self.add_btn)
        content_layout.addLayout(toolbar)

        content_splitter = QSplitter(self._orientation("Vertical"))

        self.datasource_tree = QTreeWidget()
        self.datasource_tree.setColumnCount(2)
        self.datasource_tree.setHeaderLabels(["Layer or source", "Action"])
        tree_header = self.datasource_tree.header()
        resize_mode = getattr(QHeaderView, "ResizeMode", QHeaderView)
        tree_header.setStretchLastSection(False)
        tree_header.setSectionResizeMode(0, getattr(resize_mode, "Stretch"))
        tree_header.setSectionResizeMode(1, getattr(resize_mode, "Fixed"))
        self.datasource_tree.setColumnWidth(1, 96)
        self.datasource_tree.itemSelectionChanged.connect(self._on_datasource_changed)
        self.datasource_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        content_splitter.addWidget(self.datasource_tree)

        details = QFrame()
        details.setProperty("detailsPanel", True)
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(10, 8, 10, 10)
        self.detail_title = QLabel("Select a source or layer")
        self.detail_title.setProperty("detailTitle", True)
        details_layout.addWidget(self.detail_title)
        self.detail_form = QFormLayout()
        details_layout.addLayout(self.detail_form)
        details_layout.addStretch(1)
        self.details_section = CollapsibleSection("Configuration details", details)
        content_splitter.addWidget(self.details_section)
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 1)
        content_splitter.setSizes([430, 170])
        content_layout.addWidget(content_splitter, stretch=1)

        self.edit_btn = QPushButton("Edit source")
        self.edit_btn.setIcon(QIcon(":/images/themes/default/mActionOptions.svg"))
        self.delete_btn = QToolButton()
        self.delete_btn.setIcon(QIcon(":/images/themes/default/mActionDeleteSelected.svg"))
        self.delete_btn.setToolTip("Delete source")
        self.refresh_btn = QToolButton()
        self.refresh_btn.setIcon(QIcon(":/images/themes/default/mActionRefresh.svg"))
        self.refresh_btn.setToolTip("Refresh source")
        self.export_btn = QPushButton("Export")
        self.export_btn.setIcon(QIcon(":/images/themes/default/mActionFileSave.svg"))
        self.add_btn.clicked.connect(self.add_source_requested.emit)
        self.edit_btn.clicked.connect(self._emit_edit)
        self.delete_btn.clicked.connect(self._emit_delete)
        self.refresh_btn.clicked.connect(self._emit_refresh)
        self.export_btn.clicked.connect(self.export_requested.emit)

        self.layers_list = QListWidget()

        footer = QHBoxLayout()
        footer.setSpacing(6)
        footer.addWidget(self.edit_btn)
        footer.addWidget(self.delete_btn)
        footer.addWidget(self.refresh_btn)
        footer.addStretch(1)
        footer.addWidget(self.export_btn)
        content_layout.addLayout(footer)

        workspace.addWidget(content)
        workspace.setStretchFactor(0, 0)
        workspace.setStretchFactor(1, 1)
        workspace.setSizes([180, 700])
        root.addWidget(workspace, stretch=1)

        self.setWidget(body)
        self.setMinimumWidth(720)

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
            catalog_styles(ui_colors)
            + "\n"
            + "\n".join(
                [
                    f"QFrame[detailsPanel='true'] {{ background: {panel_background}; color: {text}; }}",
                    f"QLabel[detailTitle='true'] {{ color: {header_text}; font-weight: 700; }}",
                    f"QTreeWidget, QListWidget {{ background: {window_background}; color: {dataset_text}; border: 1px solid {border}; border-radius: 4px; outline: 0; }}",
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
            groups = self._navigation_groups()
            self._rebuild_navigation(groups)
            selected_layers = next(
                (
                    layers
                    for key, _label, layers, _icon in groups
                    if key == self._selected_group
                ),
                None,
            )
            layers = (
                selected_layers
                if selected_layers is not None
                else [
                    layer
                    for _key, _label, group_layers, _icon in groups
                    for layer in group_layers
                ]
            )
            for layer in sorted(layers, key=lambda value: value.display_name.casefold()):
                self._add_layer_item(
                    self.datasource_tree,
                    layer,
                    _display_category_label(layer.business_group),
                )
        finally:
            self._rendering_tree = False
        self._apply_filter(self.filter_edit.text())
        self._show_selection_details()

    def _navigation_groups(
        self,
    ) -> list[tuple[str, str, list[LayerDefinition], QIcon]]:
        if self._grouping_mode == "category":
            grouped_layers: dict[str, list[LayerDefinition]] = {}
            for layers in self._layers_by_datasource.values():
                for layer in layers:
                    category = _display_category_label(layer.business_group)
                    grouped_layers.setdefault(category, []).append(layer)
            return [
                (
                    category,
                    category,
                    grouped_layers[category],
                    QIcon(":/images/themes/default/mIconLayerGroup.svg"),
                )
                for category in sorted(grouped_layers, key=str.casefold)
            ]

        groups: list[tuple[str, str, list[LayerDefinition], QIcon]] = []
        file_layers: dict[DatasourceType, list[LayerDefinition]] = {
            DatasourceType.KML: [],
            DatasourceType.GEOJSON: [],
        }
        for datasource in self._datasources:
            layers = self._layers_by_datasource.get(datasource.id, [])
            if datasource.datasource_type in file_layers:
                file_layers[datasource.datasource_type].extend(layers)
                continue
            groups.append(
                (
                    datasource.id,
                    datasource.name,
                    layers,
                    self._datasource_icon(datasource.datasource_type),
                )
            )
        for datasource_type, layers in file_layers.items():
            if any(
                datasource.datasource_type is datasource_type
                for datasource in self._datasources
            ):
                groups.append(
                    (
                        datasource_type.value,
                        datasource_type.value.upper(),
                        layers,
                        self._datasource_icon(datasource_type),
                    )
                )
        return groups

    def _rebuild_navigation(
        self,
        groups: list[tuple[str, str, list[LayerDefinition], QIcon]] | None = None,
    ) -> None:
        groups = self._navigation_groups() if groups is None else groups
        entries = [
            (
                "",
                "All layers",
                sum(len(layers) for _key, _label, layers, _icon in groups),
                QIcon(":/images/themes/default/mIconLayerGroup.svg"),
            )
        ]
        available_keys = {key for key, _label, _layers, _icon in groups}
        entries.extend(
            (key, label, len(layers), icon)
            for key, label, layers, icon in groups
        )
        if self._selected_group not in available_keys:
            self._selected_group = ""
        self.navigation.set_entries(entries, self._selected_group)

    @staticmethod
    def _group_label(item: QTreeWidgetItem) -> str:
        return item.text(0).split(" (COUNT = ", 1)[0]

    def _group_key(self, item: QTreeWidgetItem) -> str:
        payload = item.data(0, USER_ROLE)
        if isinstance(payload, str):
            return payload
        return self._group_label(item)

    def _leaf_count(self, item: QTreeWidgetItem) -> int:
        if not item.childCount():
            return int(isinstance(item.data(0, USER_ROLE), tuple))
        return sum(self._leaf_count(item.child(index)) for index in range(item.childCount()))

    def _on_navigation_changed(self, group_key: str) -> None:
        self._selected_group = group_key
        self._render_tree()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().casefold()
        for index in range(self.datasource_tree.topLevelItemCount()):
            item = self.datasource_tree.topLevelItem(index)
            visible = self._filter_item(item, needle)
            item.setHidden(not visible)
            if needle and visible:
                item.setExpanded(True)

    def _filter_item(self, item: QTreeWidgetItem, needle: str) -> bool:
        own_match = (
            not needle
            or needle in item.text(0).casefold()
            or needle in item.toolTip(0).casefold()
        )
        child_match = False
        for index in range(item.childCount()):
            child = item.child(index)
            child_visible = self._filter_item(child, needle)
            child.setHidden(not child_visible)
            child_match = child_match or child_visible
        return own_match or child_match

    @staticmethod
    def _orientation(name: str):
        orientation = getattr(Qt, "Orientation", None)
        if orientation is not None:
            return getattr(orientation, name)
        return getattr(Qt, name)

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
        self._render_tree()

    def _add_layer_item(
        self,
        parent_item: QTreeWidgetItem | QTreeWidget,
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
        if isinstance(parent_item, QTreeWidget):
            parent_item.addTopLevelItem(item)
        else:
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
            return (
                self._selected_group
                if any(
                    datasource.id == self._selected_group
                    for datasource in self._datasources
                )
                else None
            )
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
        self._show_selection_details()
        if self._all_layers_mode or self._rendering_tree:
            return
        item = self.datasource_tree.currentItem()
        datasource_id = item.data(0, USER_ROLE) if item is not None else None
        if isinstance(datasource_id, str):
            self.refresh_requested.emit(datasource_id)

    def _show_selection_details(self) -> None:
        while self.detail_form.rowCount():
            self.detail_form.removeRow(0)
        item = self.datasource_tree.currentItem()
        payload = item.data(0, USER_ROLE) if item is not None else None
        datasource_id = self.selected_datasource_id()
        datasource = next(
            (value for value in self._datasources if value.id == datasource_id),
            None,
        )
        self.edit_btn.setEnabled(datasource is not None)
        self.delete_btn.setEnabled(datasource is not None)
        self.refresh_btn.setEnabled(datasource is not None)
        if isinstance(payload, tuple) and len(payload) >= 2:
            layer = next(
                (
                    value
                    for value in self._layers_by_datasource.get(str(payload[0]), [])
                    if value.layer_name == str(payload[1])
                ),
                None,
            )
            if layer is not None:
                self.detail_title.setText(layer.display_name)
                self._add_detail_row("Category", _display_category_label(layer.business_group))
                self._add_detail_row("Technical name", layer.technical_name or layer.layer_name)
                self._add_detail_row("Geometry", layer.geometry_type or "Unknown")
                self._add_detail_row("CRS", layer.default_crs or "Not set")
                return
        if datasource is not None:
            self.detail_title.setText(datasource.name)
            self._add_detail_row("Type", datasource.datasource_type.value.upper())
            self._add_detail_row(
                "Status", "Enabled" if datasource.enabled else "Disabled"
            )
            self._add_detail_row(
                "Layers",
                str(len(self._layers_by_datasource.get(datasource.id, []))),
            )
            return
        self.detail_title.setText("Select a source or layer")

    def _add_detail_row(self, label: str, value: str) -> None:
        value_label = QLabel(value)
        value_label.setWordWrap(True)
        self.detail_form.addRow(QLabel(label), value_label)

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
