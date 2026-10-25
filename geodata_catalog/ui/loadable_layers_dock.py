from __future__ import annotations

from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.models.saved_layer_view import SavedLayerView

from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QIcon, QPalette
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QSplitter,
    QStyle,
    QSizePolicy,
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
        self._saved_views: list[SavedLayerView] = []
        self._detail_layer: LayerDefinition | None = None
        self._detail_loadable = False
        self._selected_saved_view_id = ""
        self._highlighted_preset_widget = None
        self._highlighted_preset_indicator = None
        self._updating_accordion = False
        self._theme_primary = "#59A947"
        self._theme_primary_text = "#FFFFFF"
        self._theme_text = "#1E293B"
        self._theme_selection_background = "#CFE8D1"
        self._theme_selection_text = "#172A1B"
        self._theme_category_text = "#2E7D32"
        self._theme_dataset_text = "#2B2B2B"
        self._theme_preset_text = "#607D8B"
        self._build_ui()

    def _build_ui(self) -> None:
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        basemap_toolbox = QFrame()
        basemap_toolbox.setProperty("groupingToolbox", True)
        basemap_row = QHBoxLayout(basemap_toolbox)
        basemap_row.setContentsMargins(6, 3, 6, 3)
        basemap_row.setSpacing(6)
        basemap_row.addWidget(QLabel("Basemap"))
        self.basemap_combo = QComboBox()
        self.basemap_combo.setToolTip("Choose the map background")
        basemap_row.addWidget(self.basemap_combo)
        self.project_basemap_button = QToolButton()
        self.project_basemap_button.setFixedSize(28, 28)
        self.project_basemap_button.setAutoRaise(True)
        self.project_basemap_button.setIcon(QIcon(":/images/themes/default/mActionAddRasterLayer.svg"))
        self.project_basemap_button.setToolTip("Load the selected basemap as the map background")
        self.project_basemap_button.clicked.connect(self._on_project_basemap_clicked)
        basemap_row.addWidget(self.project_basemap_button)
        basemap_row.addStretch(1)
        root.addWidget(basemap_toolbox)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Search in panel...")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.filter_edit, stretch=1)
        self.filter_button = QToolButton()
        self.filter_button.setFixedSize(28, 28)
        self.filter_button.setAutoRaise(True)
        self.filter_button.setIcon(QIcon(":/images/themes/default/mActionFilter.svg"))
        self.filter_button.setToolTip("Open the first category")
        self.filter_button.clicked.connect(self._toggle_categories)
        search_row.addWidget(self.filter_button)
        root.addLayout(search_row)

        content_splitter = QSplitter(self._orientation("Horizontal"))

        self.layers_tree = QTreeWidget()
        self.layers_tree.setColumnCount(2)
        self.layers_tree.setHeaderHidden(True)
        self.layers_tree.setRootIsDecorated(True)
        self.layers_tree.setAlternatingRowColors(False)
        self.layers_tree.setUniformRowHeights(True)
        self.layers_tree.setIndentation(19)
        self.layers_tree.setSelectionMode(self._selection_mode("SingleSelection"))
        self.layers_tree.setMinimumWidth(380)
        header = self.layers_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, self._header_resize_mode("Stretch"))
        header.setSectionResizeMode(1, self._header_resize_mode("Fixed"))
        self.layers_tree.setColumnWidth(1, 24)
        self.layers_tree.itemClicked.connect(self._on_item_clicked)
        self.layers_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.layers_tree.itemExpanded.connect(self._on_category_expanded)
        context_policy = getattr(Qt, "CustomContextMenu", None)
        if context_policy is None:
            context_policy = Qt.ContextMenuPolicy.CustomContextMenu
        self.layers_tree.setContextMenuPolicy(context_policy)
        self.layers_tree.customContextMenuRequested.connect(self._on_context_menu_requested)
        content_splitter.addWidget(self.layers_tree)
        content_splitter.addWidget(self._build_details_panel())
        content_splitter.setStretchFactor(0, 2)
        content_splitter.setStretchFactor(1, 3)
        content_splitter.setSizes([450, 670])
        root.addWidget(content_splitter, stretch=1)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.load_button = QPushButton("Load")
        self.load_button.setEnabled(False)
        self.load_button.clicked.connect(self._on_load_button_clicked)
        action_row.addWidget(self.load_button)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        action_row.addWidget(self.close_button)
        root.addLayout(action_row)

        self._show_layer_details(None)
        self.setWidget(body)
        self.setMinimumWidth(1140)

    def _build_details_panel(self) -> QWidget:
        panel = QWidget()
        panel.setProperty("detailsPanel", True)
        panel.setAutoFillBackground(True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        overview = QFrame()
        overview.setProperty("detailPanel", True)
        overview.setFrameShape(self._frame_shape("StyledPanel"))
        overview.setFrameShadow(self._frame_shadow("Plain"))
        overview.setAutoFillBackground(True)
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(8, 8, 8, 8)
        self.detail_title = QLabel("Select a default layer")
        self.detail_title.setProperty("detailTitle", True)
        self.detail_title.setWordWrap(True)
        overview_layout.addWidget(self.detail_title)
        self.detail_form = QFormLayout()
        self.detail_form.setRowWrapPolicy(self._form_row_wrap_policy("DontWrapRows"))
        overview_layout.addLayout(self.detail_form)
        layout.addWidget(overview)

        self.presets_group = QFrame()
        self.presets_group.setProperty("detailPanel", True)
        self.presets_group.setFrameShape(self._frame_shape("StyledPanel"))
        self.presets_group.setFrameShadow(self._frame_shadow("Plain"))
        self.presets_group.setAutoFillBackground(True)
        presets_layout = QVBoxLayout(self.presets_group)
        presets_layout.setContentsMargins(8, 8, 8, 8)
        presets_layout.setSpacing(4)
        presets_title = QLabel("Saved views and presets")
        presets_title.setProperty("sectionLabel", True)
        presets_layout.addWidget(presets_title)
        self.preset_hint = QLabel("Select a default layer to view its saved views.")
        self.preset_hint.setWordWrap(True)
        presets_layout.addWidget(self.preset_hint)
        self.presets_list = QListWidget()
        self.presets_list.setContextMenuPolicy(self._context_menu_policy())
        self.presets_list.itemDoubleClicked.connect(self._on_preset_double_clicked)
        self.presets_list.itemClicked.connect(self._on_preset_clicked)
        self.presets_list.customContextMenuRequested.connect(self._on_preset_context_menu)
        presets_layout.addWidget(self.presets_list, stretch=1)
        layout.addWidget(self.presets_group)
        layout.addStretch(1)
        return panel

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
        preset_text = str(ui_colors.get("preset_text", "#607D8B"))
        selection_background = str(ui_colors.get("selection_background", "#CFE8D1"))
        selection_text = str(ui_colors.get("selection_text", "#172A1B"))
        self._theme_primary = primary
        self._theme_primary_text = primary_text
        self._theme_text = text
        self._theme_selection_background = selection_background
        self._theme_selection_text = selection_text
        self._theme_category_text = category_text
        self._theme_dataset_text = dataset_text
        self._theme_preset_text = preset_text
        self.setStyleSheet(
            "\n".join(
                [
                    f"QDockWidget {{ background: {window_background}; color: {text}; }}",
                    f"QWidget {{ background: {window_background}; color: {text}; }}",
                    f"QWidget[detailsPanel='true'] {{ background: {panel_background}; color: {text}; }}",
                    f"QLineEdit, QComboBox {{ background: {window_background}; color: {text}; border: 1px solid {border}; border-radius: 4px; min-height: 30px; padding: 2px 8px; }}",
                    f"QLineEdit:focus, QComboBox:focus {{ border: 1px solid {primary}; }}",
                    f"QToolButton {{ border: 1px solid {border}; border-radius: 4px; background: {window_background}; color: {text}; min-width: 30px; min-height: 30px; }}",
                    f"QToolButton:hover {{ border-color: {primary}; background: {hover_background}; color: {header_text}; }}",
                    f"QPushButton {{ background: {window_background}; color: {text}; border: 1px solid {border}; border-radius: 4px; min-height: 28px; padding: 2px 12px; }}",
                    f"QPushButton:hover {{ border-color: {primary}; background: {hover_background}; color: {header_text}; }}",
                    f"QPushButton:pressed {{ background: {primary}; color: {primary_text}; }}",
                    f"QPushButton:disabled {{ color: {border}; background: {panel_background}; }}",
                    f"QTreeWidget {{ background: {panel_background}; color: {dataset_text}; border: 1px solid {border}; border-radius: 4px; outline: 0; }}",
                    f"QTreeWidget::item {{ color: {dataset_text}; }}",
                    f"QTreeWidget::item:has-children {{ color: {category_text}; }}",
                    f"QTreeWidget::item {{ min-height: 30px; padding: 2px 6px; border-bottom: 1px solid {header_background}; }}",
                    "QTreeWidget::item:column(1) { padding-right: 6px; padding-left: 0px; }",
                    f"QTreeWidget::item:selected {{ background: {selection_background}; color: {selection_text}; }}",
                    f"QTreeWidget::item:selected:active {{ background: {selection_background}; color: {selection_text}; }}",
                    f"QTreeWidget::item:selected:!active {{ background: {selection_background}; color: {selection_text}; }}",
                    f"QTreeWidget::branch:selected {{ background: {selection_background}; }}",
                    f"QTreeWidget::branch:has-children:closed, QTreeWidget::branch:has-children:open {{ color: {primary}; }}",
                    f"QFrame[basemapFooter='true'] {{ background: {panel_background}; border: 1px solid {border}; border-radius: 4px; }}",
                    f"QFrame[groupingToolbox='true'] {{ background: {panel_background}; border: 1px solid {border}; border-radius: 3px; }}",
                    f"QFrame[groupingToolbox='true'] QLabel {{ color: {header_text}; font-weight: 600; }}",
                    f"QFrame[groupingToolbox='true'] QComboBox {{ min-height: 24px; padding: 1px 22px 1px 6px; background: {window_background}; color: {text}; border: 1px solid {border}; border-radius: 3px; }}",
                    f"QGroupBox {{ background: {panel_background}; border: 1px solid {border}; border-radius: 4px; margin-top: 8px; padding-top: 8px; }}",
                    f"QGroupBox::title {{ color: {primary}; font-size: 10px; font-weight: 700; subcontrol-origin: margin; left: 8px; padding: 0 3px; }}",
                    f"QFrame[detailPanel='true'] {{ background: {panel_background}; color: {text}; border: 1px solid {border}; border-radius: 4px; }}",
                    f"QFrame[detailPanel='true'] QLabel {{ color: {text}; }}",
                    f"QLabel[detailTitle='true'] {{ color: {header_text}; font-size: 11px; font-weight: 700; padding-bottom: 4px; }}",
                    f"QLabel[detailValue='true'] {{ color: {text}; }}",
                    f"QListWidget {{ background: {window_background}; color: {preset_text}; border: 1px solid {border}; border-radius: 4px; outline: 0; }}",
                    f"QListWidget::item {{ color: {preset_text}; }}",
                    f"QListWidget::item {{ min-height: 30px; padding: 2px 6px; border-bottom: 1px solid {header_background}; }}",
                    f"QListWidget::item:selected {{ background: {selection_background}; color: {selection_text}; }}",
                    f"QListWidget::item {{ min-height: 22px; padding: 1px 4px; border-bottom: 1px solid {header_background}; }}",
                    f"QListWidget QWidget[presetSelected='false'] {{ background: transparent; border-bottom: 1px solid {header_background}; }}",
                    f"QListWidget QWidget[presetSelected='true'] {{ background: {selection_background}; color: {selection_text}; border-bottom: 1px solid {border}; }}",
                    f"QListWidget QWidget[presetSelected='true'] {{ background: {selection_background}; color: {selection_text}; border-radius: 3px; }}",
                    f"QListWidget QWidget QLabel {{ background: transparent; color: {preset_text}; }}",
                    f"QListWidget QWidget[presetSelected='true'] QLabel {{ background: transparent; color: {selection_text}; }}",
                    f"QListWidget QWidget[presetSelected='true'] QToolButton {{ background: transparent; color: {selection_text}; }}",
                    "QListWidget QToolButton { min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px; padding: 0px; border: 0px; }",
                    f"QListWidget QToolButton#presetInfoButton {{ background: transparent; border: 0px; border-radius: 9px; }}",
                    f"QListWidget QToolButton#presetInfoButton:hover {{ background: {hover_background}; border: 0px; }}",
                    f"QLabel[sectionLabel='true'] {{ color: {header_text}; font-size: 11px; font-weight: 700; }}",
                ]
            )
        )
        self._apply_selection_palette(self.layers_tree, selection_background, selection_text)
        self._apply_selection_palette(self.presets_list, selection_background, selection_text)
        if self._highlighted_preset_indicator is not None:
            self._set_preset_indicator_color(self._highlighted_preset_indicator, True)

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

    def set_rows(
        self,
        rows: list[dict[str, str | LayerDefinition]],
        loaded_layer_keys: set[str],
        _active_color: str,
        saved_views: list[SavedLayerView] | None = None,
    ) -> None:
        self._rows = list(rows)
        self._saved_views = list(saved_views or [])
        self._updating_tree = True
        self._highlighted_item = None
        self.layers_tree.clear()
        grouped_rows: dict[str, list[dict[str, str | LayerDefinition]]] = {}
        for row in rows:
            datasource_id = str(row.get("datasource_id", ""))
            display_group = str(row.get("business_group", "")).strip()
            category = _display_category_label(display_group)
            layer = row.get("layer")
            if not datasource_id or layer is None or not isinstance(layer, LayerDefinition):
                continue
            grouped_rows.setdefault(category, []).append(row)

        for category in sorted(grouped_rows.keys(), key=str.casefold):
            category_rows = grouped_rows[category]
            category_item = QTreeWidgetItem(
                [f"{category} (COUNT = {len(category_rows)})"]
            )
            category_item.setFirstColumnSpanned(True)
            category_item.setIcon(0, QIcon(":/images/themes/default/mActionAddGroup.svg"))
            category_font = category_item.font(0)
            category_font.setBold(True)
            category_item.setFont(0, category_font)
            category_item.setForeground(0, QColor(self._theme_category_text))
            self.layers_tree.addTopLevelItem(category_item)

            category_rows = sorted(
                category_rows,
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
                saved_count = sum(
                    1 for view in self._saved_views
                    if view.datasource_id == layer.datasource_id
                    and view.layer_name == layer.layer_name
                )
                item = QTreeWidgetItem(
                    category_item,
                    [f"{layer.display_name} ({saved_count} saved layer{'s' if saved_count != 1 else ''})"],
                )
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

            category_item.setExpanded(False)

        if self.layers_tree.topLevelItemCount():
            self.layers_tree.topLevelItem(0).setExpanded(True)
        self._updating_tree = False
        self._populate_presets()
        self._show_layer_details(None)
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

    @staticmethod
    def _size_policy(name: str):
        policy = getattr(QSizePolicy, "Policy", None)
        if policy is not None:
            return getattr(policy, name)
        return getattr(QSizePolicy, name)

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
            self._detail_layer = self._layer_for_payload(payload)
            self._detail_loadable = bool(payload[3])
            self._selected_saved_view_id = ""
            self._set_item_highlight(item)
        elif payload and len(payload) == 2 and payload[0] == "saved_view":
            self._highlighted_identity = payload
            self._select_saved_view(str(payload[1]))
        else:
            self._highlighted_identity = None
            self._detail_layer = None
            self._detail_loadable = False
        self._set_item_highlight(item)
        self._show_layer_details(self._detail_layer)

    def _set_item_highlight(self, item: QTreeWidgetItem) -> None:
        if self._highlighted_item is not None and self._highlighted_item is not item:
            self._highlighted_item.setSelected(False)
        item.setSelected(True)
        self.layers_tree.setCurrentItem(item)
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

    def _on_preset_double_clicked(self, item: QListWidgetItem) -> None:
        view_id = item.data(USER_ROLE)
        if view_id:
            self.saved_view_requested.emit(str(view_id))

    def _on_preset_clicked(self, item: QListWidgetItem) -> None:
        view_id = str(item.data(USER_ROLE) or "")
        if view_id:
            self._set_preset_highlight(item)
            self._select_saved_view(view_id)

    def _select_saved_view(self, view_id: str) -> None:
        view = next((value for value in self._saved_views if value.id == view_id), None)
        if view is None:
            return
        self._selected_saved_view_id = view.id
        self._detail_layer = next(
            (
                layer for row in self._rows
                for layer in [row.get("layer")]
                if isinstance(layer, LayerDefinition)
                and layer.datasource_id == view.datasource_id
                and layer.layer_name == view.layer_name
            ),
            None,
        )
        self._detail_loadable = self._detail_layer is not None
        self._select_tree_layer(view.datasource_id, view.layer_name)
        self._show_layer_details(self._detail_layer)

    def _select_tree_layer(self, datasource_id: str, layer_name: str) -> None:
        for category_index in range(self.layers_tree.topLevelItemCount()):
            category_item = self.layers_tree.topLevelItem(category_index)
            for layer_index in range(category_item.childCount()):
                item = category_item.child(layer_index)
                payload = item.data(0, USER_ROLE)
                if (
                    payload and len(payload) == 4
                    and str(payload[0]) == datasource_id
                    and str(payload[1]) == layer_name
                ):
                    self._highlighted_identity = payload[:3]
                    self._highlighted_item = item
                    self._set_item_highlight(item)
                    return

    def _on_preset_context_menu(self, position) -> None:
        item = self.presets_list.itemAt(position)
        if item is None:
            return
        view_id = str(item.data(USER_ROLE) or "")
        if not view_id:
            return
        menu = QMenu(self.presets_list)
        rename_action = menu.addAction("Rename Layer View")
        delete_action = menu.addAction("Delete Layer View")
        selected_action = menu.exec(self.presets_list.viewport().mapToGlobal(position))
        if selected_action == rename_action:
            self.saved_view_rename_requested.emit(view_id)
        elif selected_action == delete_action:
            self.saved_view_delete_requested.emit(view_id)

    def _populate_presets(self) -> None:
        self.presets_list.clear()
        self._highlighted_preset_widget = None
        self._highlighted_preset_indicator = None
        if self._detail_layer is None:
            self.presets_group.setVisible(False)
            return
        self.presets_group.setVisible(True)
        layer_views = [
            view for view in self._saved_views
            if view.datasource_id == self._detail_layer.datasource_id
            and view.layer_name == self._detail_layer.layer_name
        ]
        has_views = bool(layer_views)
        self.presets_list.setVisible(has_views)
        self.presets_list.setMaximumHeight(16777215 if has_views else 0)
        for view in sorted(layer_views, key=lambda value: value.name.casefold()):
            filter_text = self._saved_view_filter_text(view)
            grouping_text = self._saved_view_grouping_text(view)
            item = QListWidgetItem(view.name)
            item.setData(USER_ROLE, view.id)
            details = (
                f"Layer: {view.layer_display_name}\n"
                f"Filter: {filter_text}\n"
                f"Grouping/preset: {grouping_text}\n"
                f"Last updated: {view.updated_at}\n"
                "Double-click to apply this saved view."
            )
            item.setToolTip(details)
            self.presets_list.addItem(item)
            row_widget = QWidget(self.presets_list)
            row_widget.setProperty("presetSelected", view.id == self._selected_saved_view_id)
            row_widget.setAutoFillBackground(True)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(2, 2, 4, 2)
            row_layout.setSpacing(4)
            highlight_indicator = QFrame(row_widget)
            highlight_indicator.setFixedWidth(6)
            highlight_indicator.setMinimumHeight(20)
            highlight_indicator.setSizePolicy(
                self._size_policy("Fixed"),
                self._size_policy("Expanding"),
            )
            self._set_preset_indicator_color(
                highlight_indicator,
                view.id == self._selected_saved_view_id,
            )
            row_layout.addWidget(highlight_indicator)
            name_label = QLabel(view.name, row_widget)
            name_label.setToolTip(details)
            row_layout.addWidget(name_label, stretch=1)
            info_button = QToolButton(row_widget)
            info_button.setObjectName("presetInfoButton")
            info_button.setAutoRaise(True)
            info_button.setFixedSize(18, 18)
            info_button.setIconSize(QSize(12, 12))
            info_button.setIcon(self.presets_list.style().standardIcon(self._standard_pixmap("SP_MessageBoxInformation")))
            info_button.setToolTip(details)
            info_button.clicked.connect(lambda _checked=False, text=details: self._show_preset_info(text))
            row_layout.addWidget(info_button)
            item.setSizeHint(row_widget.sizeHint())
            self.presets_list.setItemWidget(item, row_widget)
            if view.id == self._selected_saved_view_id:
                self.presets_list.setCurrentItem(item)
                self._highlighted_preset_widget = row_widget
                self._highlighted_preset_indicator = highlight_indicator
        self.preset_hint.setText(f"{len(layer_views)} saved view(s) for this layer.")

    def _set_preset_highlight(self, item: QListWidgetItem) -> None:
        previous_widget = self._highlighted_preset_widget
        if previous_widget is not None:
            previous_widget.setProperty("presetSelected", False)
            previous_widget.style().unpolish(previous_widget)
            previous_widget.style().polish(previous_widget)
        previous_indicator = self._highlighted_preset_indicator
        if previous_indicator is not None:
            self._set_preset_indicator_color(previous_indicator, False)

        row_widget = self.presets_list.itemWidget(item)
        if row_widget is None:
            return
        row_layout = row_widget.layout()
        indicator = row_layout.itemAt(0).widget() if row_layout is not None else None
        if indicator is not None:
            self._set_preset_indicator_color(indicator, True)
        row_widget.setProperty("presetSelected", True)
        row_widget.style().unpolish(row_widget)
        row_widget.style().polish(row_widget)
        self.presets_list.setCurrentItem(item)
        self._highlighted_preset_widget = row_widget
        self._highlighted_preset_indicator = indicator

    def _set_preset_indicator_color(self, indicator: QFrame, selected: bool) -> None:
        color = self._theme_selection_background if selected else "transparent"
        indicator.setAutoFillBackground(True)
        indicator.setStyleSheet(
            f"QFrame {{ background-color: {color}; border: 0px; }}"
        )
        indicator.update()

    def _show_layer_details(self, layer: LayerDefinition | None) -> None:
        self.detail_title.setText(layer.display_name if layer else "Select a default layer")
        has_layer = layer is not None and self._detail_loadable
        if not has_layer:
            self.load_button.setText("Load")
            self.load_button.setToolTip("Select a default layer to load.")
        elif self._selected_saved_view_id:
            self.load_button.setText("Load saved view")
            self.load_button.setToolTip(
                "Load the selected saved view. Select the default layer to load it without a saved view."
            )
        else:
            self.load_button.setText("Load default layer")
            self.load_button.setToolTip("Load the selected default layer without applying a saved view.")
        self.load_button.setEnabled(has_layer)
        while self.detail_form.rowCount():
            self.detail_form.removeRow(0)
        if layer is None:
            self._populate_presets()
            return
        values = [
            ("Technical name", layer.technical_name or layer.object_name or layer.layer_name),
            ("Geometry", layer.geometry_type or "Unknown"),
            ("CRS", layer.default_crs or "Not set"),
            ("Features", str(layer.feature_count) if layer.feature_count is not None else "Unknown"),
            ("Geometry column", layer.geometry_column or "Not set"),
        ]
        for label, value in values:
            value_label = QLabel(value)
            value_label.setProperty("detailValue", True)
            value_label.setWordWrap(True)
            self.detail_form.addRow(QLabel(label), value_label)
        self._populate_presets()

    def _on_load_button_clicked(self) -> None:
        if self._selected_saved_view_id:
            self.saved_view_requested.emit(self._selected_saved_view_id)
        elif self._detail_layer is not None and self._detail_loadable:
            self.load_layer_requested.emit(
                self._detail_layer.datasource_id,
                self._detail_layer.layer_name,
            )

    def _show_preset_info(self, details: str) -> None:
        QMessageBox.information(self, "Saved view details", details)

    @staticmethod
    def _standard_pixmap(name: str):
        standard_pixmap = getattr(QStyle, name, None)
        if standard_pixmap is not None:
            return standard_pixmap
        return getattr(QStyle.StandardPixmap, name)

    @staticmethod
    def _frame_shape(name: str):
        shape = getattr(QFrame, "Shape", None)
        if shape is not None:
            return getattr(shape, name)
        return getattr(QFrame, name)

    @staticmethod
    def _frame_shadow(name: str):
        shadow = getattr(QFrame, "Shadow", None)
        if shadow is not None:
            return getattr(shadow, name)
        return getattr(QFrame, name)

    def _layer_for_payload(self, payload) -> LayerDefinition | None:
        datasource_id, layer_name = str(payload[0]), str(payload[1])
        for row in self._rows:
            layer = row.get("layer")
            if (
                isinstance(layer, LayerDefinition)
                and str(row.get("datasource_id", "")) == datasource_id
                and layer.layer_name == layer_name
            ):
                return layer
        return None

    def _on_category_expanded(self, expanded_item: QTreeWidgetItem) -> None:
        if self._updating_accordion:
            return
        self._updating_accordion = True
        for index in range(self.layers_tree.topLevelItemCount()):
            category_item = self.layers_tree.topLevelItem(index)
            if category_item is not expanded_item:
                category_item.setExpanded(False)
        self._updating_accordion = False

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
        if self.layers_tree.topLevelItemCount() == 0:
            return
        current = self.layers_tree.indexOfTopLevelItem(self._expanded_category())
        target = 0 if current < 0 else min(current + 1, self.layers_tree.topLevelItemCount() - 1)
        self.layers_tree.topLevelItem(target).setExpanded(True)

    def _expanded_category(self) -> QTreeWidgetItem | None:
        for index in range(self.layers_tree.topLevelItemCount()):
            item = self.layers_tree.topLevelItem(index)
            if item.isExpanded():
                return item
        return None

    @staticmethod
    def _orientation(name: str):
        orientation = getattr(Qt, "Orientation", None)
        if orientation is not None:
            return getattr(orientation, name)
        return getattr(Qt, name)

    @staticmethod
    def _context_menu_policy():
        policy = getattr(Qt, "ContextMenuPolicy", None)
        if policy is not None:
            return policy.CustomContextMenu
        return Qt.CustomContextMenu

    @staticmethod
    def _form_row_wrap_policy(name: str):
        policy = getattr(QFormLayout, "RowWrapPolicy", None)
        if policy is not None:
            return getattr(policy, name)
        return getattr(QFormLayout, name)

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
