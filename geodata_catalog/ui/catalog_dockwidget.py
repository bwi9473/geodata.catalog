from __future__ import annotations

from geodata_catalog.models.datasource import Datasource, DatasourceType
from geodata_catalog.models.layer_definition import LayerDefinition

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


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


class CatalogDockWidget(QDockWidget):
    """Unified workflow dock for exploring, displaying and analyzing GeoData layers."""

    add_source_requested = pyqtSignal()
    edit_source_requested = pyqtSignal(str)
    delete_source_requested = pyqtSignal(str)
    refresh_requested = pyqtSignal(str)
    load_layer_requested = pyqtSignal(str, str)
    edit_layer_config_requested = pyqtSignal(str, str)  # datasource_id, layer_name
    show_all_layers_toggled = pyqtSignal(bool)
    basemap_selected = pyqtSignal(str)
    focus_muac_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__("GeoData Explorer", parent)
        self._datasource_items: dict[str, QTreeWidgetItem] = {}
        self._all_layers_mode = False
        self._updating_basemap = False
        self._build_ui()

    def _build_ui(self) -> None:
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        hint = QLabel("One workflow for Explore, Display and Analyze.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        explore_group = QGroupBox("Explore")
        explore_layout = QVBoxLayout(explore_group)
        explore_layout.setSpacing(8)

        self.datasource_tree = QTreeWidget()
        self.datasource_tree.setHeaderHidden(True)
        self.datasource_tree.itemSelectionChanged.connect(self._on_datasource_changed)
        explore_layout.addWidget(self.datasource_tree, stretch=2)

        self.layers_list = QListWidget()
        self.layers_list.itemDoubleClicked.connect(self._on_layer_double_clicked)
        self.layers_list.setContextMenuPolicy(_CUSTOM_CTX)
        self.layers_list.customContextMenuRequested.connect(self._on_layers_context_menu)
        explore_layout.addWidget(self.layers_list, stretch=3)

        self.show_all_layers_check = QCheckBox("Show all loadable layers")
        self.show_all_layers_check.toggled.connect(self._on_show_all_layers_toggled)
        explore_layout.addWidget(self.show_all_layers_check)

        source_buttons = QHBoxLayout()
        self.add_btn = QPushButton("Add Source")
        self.edit_btn = QPushButton("Edit Source")
        self.delete_btn = QPushButton("Delete Source")
        self.refresh_btn = QPushButton("Refresh")
        self.load_btn = QPushButton("Load")
        self.configure_btn = QPushButton("Configure")

        self.add_btn.clicked.connect(self.add_source_requested.emit)
        self.edit_btn.clicked.connect(self._emit_edit)
        self.delete_btn.clicked.connect(self._emit_delete)
        self.refresh_btn.clicked.connect(self._emit_refresh)
        self.load_btn.clicked.connect(self._emit_load)
        self.configure_btn.clicked.connect(self._emit_edit_layer_config)

        source_buttons.addWidget(self.add_btn)
        source_buttons.addWidget(self.edit_btn)
        source_buttons.addWidget(self.delete_btn)
        source_buttons.addWidget(self.refresh_btn)
        explore_layout.addLayout(source_buttons)

        layer_buttons = QHBoxLayout()
        layer_buttons.addWidget(self.load_btn)
        layer_buttons.addWidget(self.configure_btn)
        explore_layout.addLayout(layer_buttons)

        root.addWidget(explore_group)

        display_group = QGroupBox("Display")
        display_layout = QFormLayout(display_group)
        display_layout.setContentsMargins(8, 8, 8, 8)
        display_layout.setSpacing(8)

        self.basemap_combo = QComboBox()
        self.show_basemap_btn = QPushButton("Show Map")
        self.show_basemap_btn.clicked.connect(self._emit_selected_basemap)
        display_layout.addRow("Map", self.basemap_combo)

        self.focus_muac_btn = QPushButton("Focus MUAC")
        self.focus_muac_btn.clicked.connect(self.focus_muac_requested.emit)
        map_tools = QHBoxLayout()
        map_tools.addWidget(self.focus_muac_btn)
        map_tools.addWidget(self.show_basemap_btn)
        display_layout.addRow("Map Tools", map_tools)

        root.addWidget(display_group)

        self.setWidget(body)

    def set_basemap_options(self, options: list[dict[str, str]], selected_name: str) -> None:
        self._updating_basemap = True
        try:
            self.basemap_combo.clear()
            for option in options:
                name = str(option.get("name", "")).strip()
                if not name:
                    continue
                self.basemap_combo.addItem(name, name)

            self.set_selected_basemap(selected_name)
        finally:
            self._updating_basemap = False

    def set_selected_basemap(self, basemap_name: str) -> None:
        if not basemap_name:
            return
        index = self.basemap_combo.findData(basemap_name)
        if index < 0:
            return
        self._updating_basemap = True
        try:
            self.basemap_combo.setCurrentIndex(index)
        finally:
            self._updating_basemap = False

    def set_datasources(self, datasources: list[Datasource]) -> None:
        self.datasource_tree.clear()
        self._datasource_items.clear()

        database_root = QTreeWidgetItem(["Database Sources"])
        oracle_root = QTreeWidgetItem(["Oracle"])
        database_root.addChild(oracle_root)

        rest_root = QTreeWidgetItem(["REST Sources"])
        file_root = QTreeWidgetItem(["File Sources"])
        geojson_root = QTreeWidgetItem(["GeoJSON"])
        kml_root = QTreeWidgetItem(["KML"])
        file_root.addChild(geojson_root)
        file_root.addChild(kml_root)

        self.datasource_tree.addTopLevelItem(database_root)
        self.datasource_tree.addTopLevelItem(rest_root)
        self.datasource_tree.addTopLevelItem(file_root)

        for datasource in datasources:
            item = QTreeWidgetItem([datasource.name])
            item.setData(0, USER_ROLE, datasource.id)
            self._datasource_items[datasource.id] = item

            if datasource.datasource_type is DatasourceType.ORACLE:
                oracle_root.addChild(item)
            elif datasource.datasource_type is DatasourceType.REST:
                rest_root.addChild(item)
            elif datasource.datasource_type is DatasourceType.GEOJSON:
                geojson_root.addChild(item)
            elif datasource.datasource_type is DatasourceType.KML:
                kml_root.addChild(item)

        self.datasource_tree.expandAll()

    def set_layers(self, datasource_id: str, layers: list[LayerDefinition]) -> None:
        if self._all_layers_mode:
            return
        self.layers_list.clear()
        grouped_layers: dict[str, list[LayerDefinition]] = {}
        for layer in layers:
            category = _display_category_label(layer.business_group or "")
            grouped_layers.setdefault(category, []).append(layer)

        for category in sorted(grouped_layers.keys(), key=str.casefold):
            header_item = QListWidgetItem(f"Category: {category}")
            header_font = header_item.font()
            header_font.setBold(True)
            header_item.setFont(header_font)
            if _NO_ITEM_FLAGS is not None:
                header_item.setFlags(_NO_ITEM_FLAGS)
            self.layers_list.addItem(header_item)
            for layer in sorted(grouped_layers[category], key=lambda l: l.display_name.casefold()):
                item = QListWidgetItem(f"  {layer.display_name}")
                item.setData(USER_ROLE, (datasource_id, layer.layer_name))
                item.setToolTip(
                    f"Category: {category}\n"
                    f"{layer.display_name}\nGeometry: {layer.geometry_type or 'Unknown'}\n"
                    f"CRS: {layer.default_crs or 'Not set'}\n"
                    f"Count: {layer.feature_count if layer.feature_count is not None else 'Unknown'}"
                )
                self.layers_list.addItem(item)

    def set_all_layers(self, rows: list[dict[str, str | LayerDefinition]]) -> None:
        """Render one combined list with loadable layers from all datasources."""
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
                item.setToolTip(
                    f"Category: {category}\n"
                    f"Source: {source_name} ({source_type})\n"
                    f"Layer: {layer.display_name}\n"
                    f"Geometry: {layer.geometry_type or 'Unknown'}\n"
                    f"CRS: {layer.default_crs or 'Not set'}\n"
                    f"Count: {layer.feature_count if layer.feature_count is not None else 'Unknown'}\n"
                    f"Loadable: {'Yes' if loadable else 'No'}"
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
        return item.data(0, USER_ROLE)

    def _on_datasource_changed(self) -> None:
        if self._all_layers_mode:
            return
        datasource_id = self.selected_datasource_id()
        if datasource_id:
            self.refresh_requested.emit(datasource_id)

    def _on_show_all_layers_toggled(self, checked: bool) -> None:
        self._all_layers_mode = checked
        self.show_all_layers_toggled.emit(checked)

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

    def _emit_load(self) -> None:
        item = self.layers_list.currentItem()
        if item is None:
            return
        payload = item.data(USER_ROLE)
        if not payload or len(payload) < 2:
            return
        datasource_id, layer_name = payload[0], payload[1]
        loadable = True if len(payload) < 3 else bool(payload[2])
        if not loadable:
            return
        self.load_layer_requested.emit(datasource_id, layer_name)

    def _emit_edit_layer_config(self) -> None:
        item = self.layers_list.currentItem()
        if item is None:
            return
        payload = item.data(USER_ROLE)
        if not payload or len(payload) < 2:
            return
        datasource_id, layer_name = payload[0], payload[1]
        self.edit_layer_config_requested.emit(datasource_id, layer_name)

    def _emit_selected_basemap(self) -> None:
        name = str(self.basemap_combo.currentData() or "").strip()
        if not name:
            return
        self.basemap_selected.emit(name)

    def _on_layer_double_clicked(self, item: QListWidgetItem) -> None:
        payload = item.data(USER_ROLE)
        if not payload or len(payload) < 2:
            return
        datasource_id, layer_name = payload[0], payload[1]
        loadable = True if len(payload) < 3 else bool(payload[2])
        if not loadable:
            return
        self.load_layer_requested.emit(datasource_id, layer_name)

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
        load_action = menu.addAction("Load Layer")
        load_action.setEnabled(loadable)
        menu.addSeparator()
        edit_config_action = menu.addAction("Edit Layer Config…")
        chosen = menu.exec(self.layers_list.viewport().mapToGlobal(pos))
        if chosen == load_action:
            self.load_layer_requested.emit(datasource_id, layer_name)
        elif chosen == edit_config_action:
            self.edit_layer_config_requested.emit(datasource_id, layer_name)
