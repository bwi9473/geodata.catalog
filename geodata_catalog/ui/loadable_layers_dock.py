from __future__ import annotations

from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.models.saved_layer_view import SavedLayerView

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QTreeWidget,
    QTreeWidgetItem,
)


USER_ROLE = getattr(Qt, "UserRole", Qt.ItemDataRole.UserRole)


def _display_category_label(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value:
        return "Miscellaneous"
    if value.casefold() == "file sources":
        return "Uncategorized"
    return value


class LoadableLayersDockWidget(QDockWidget):
    """Dock for selecting visible catalog layers and the active basemap."""

    load_layer_requested = pyqtSignal(str, str)
    basemap_selected = pyqtSignal(str)
    saved_view_requested = pyqtSignal(str)
    saved_view_details_requested = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__("Data Panel", parent)
        self._rows: list[dict[str, str | LayerDefinition]] = []
        self._updating_tree = False
        self._updating_basemap = False
        self._theme_primary = "#59A947"
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
        self.filter_button.setToolTip("Alle categorieen in- of uitklappen")
        self.filter_button.clicked.connect(self._toggle_categories)
        search_row.addWidget(self.filter_button)
        root.addLayout(search_row)

        self.layers_tree = QTreeWidget()
        self.layers_tree.setColumnCount(1)
        self.layers_tree.setHeaderHidden(True)
        self.layers_tree.setRootIsDecorated(True)
        self.layers_tree.setAlternatingRowColors(False)
        self.layers_tree.setUniformRowHeights(True)
        self.layers_tree.setIndentation(19)
        self.layers_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
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
                    f"QTreeWidget::item:selected {{ background: {primary}; color: {primary_text}; }}",
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
                item.setIcon(0, self._layer_icon(layer))
                item.setData(0, USER_ROLE, (datasource_id, layer.layer_name, layer_key, loadable))
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
                    view_item = QTreeWidgetItem(item, [""])
                    view_item.setIcon(0, QIcon(":/images/themes/default/mActionFileSave.svg"))
                    view_item.setData(0, USER_ROLE, ("saved_view", view.id))
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
                    view_row = QWidget(self.layers_tree)
                    view_row.setToolTip(tooltip)
                    view_layout = QHBoxLayout(view_row)
                    view_layout.setContentsMargins(0, 0, 0, 0)
                    view_layout.setSpacing(4)
                    view_label = QLabel(view.name, view_row)
                    view_label.setToolTip(tooltip)
                    view_layout.addWidget(view_label)
                    view_layout.addStretch(1)
                    self.layers_tree.setItemWidget(view_item, 0, view_row)

            category_item.setExpanded(True)
            category_item.setText(0, f"{category.upper()}   ({category_item.childCount()})")

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

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        payload = item.data(0, USER_ROLE)
        if payload and len(payload) == 2 and payload[0] == "saved_view":
            self.saved_view_requested.emit(str(payload[1]))
        elif payload and len(payload) == 4 and bool(payload[3]):
            self.load_layer_requested.emit(str(payload[0]), str(payload[1]))

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
    def _layer_icon(layer: LayerDefinition) -> QIcon:
        if (layer.geometry_type or "").casefold() in {"point", "multipoint"}:
            return QIcon(":/images/themes/default/mIconPointLayer.svg")
        if (layer.geometry_type or "").casefold() in {"line", "linestring", "multilinestring"}:
            return QIcon(":/images/themes/default/mIconLineLayer.svg")
        return QIcon(":/images/themes/default/mIconPolygonLayer.svg")

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().casefold()
        for index in range(self.layers_tree.topLevelItemCount()):
            category_item = self.layers_tree.topLevelItem(index)
            visible_children = 0
            for child_index in range(category_item.childCount()):
                item = category_item.child(child_index)
                visible = not needle or needle in item.text(0).casefold() or needle in item.toolTip(0).casefold()
                item.setHidden(not visible)
                visible_children += int(visible)
            category_item.setHidden(visible_children == 0)
            if needle and visible_children:
                category_item.setExpanded(True)
