from __future__ import annotations

from typing import Any

from geodata_catalog.models.layer_definition import LayerDefinition

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


USER_ROLE = getattr(Qt, "UserRole", Qt.ItemDataRole.UserRole)


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


class LoadableLayersDockWidget(QDockWidget):
    """Transparent dock that shows all loadable layers with load state indicators."""

    load_layer_requested = pyqtSignal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__("GeoData Catalog Layers", parent)
        self._rows: list[dict[str, str | LayerDefinition]] = []
        self._active_color = "#59A947"
        self._build_ui()

    def _build_ui(self) -> None:
        body = QWidget(self)
        root = QVBoxLayout(body)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self._hint = QLabel("Double-click a layer to load it.")
        root.addWidget(self._hint)

        self.layers_list = QListWidget()
        self.layers_list.itemDoubleClicked.connect(self._on_layer_double_clicked)
        root.addWidget(self.layers_list, stretch=1)

        self.setWidget(body)

    def apply_theme(self, ui_colors: dict[str, str]) -> None:
        self._active_color = str(ui_colors.get("primary", "#59A947"))
        border = str(ui_colors.get("border", "#D7DEE8"))
        text = str(ui_colors.get("text", "#1E293B"))
        self.setStyleSheet(
            "\n".join(
                [
                    f"QDockWidget {{ background: rgba(255, 255, 255, 170); color: {text}; }}",
                    f"QLabel {{ color: {text}; }}",
                    f"QListWidget {{ background: rgba(255, 255, 255, 160); border: 1px solid {border}; border-radius: 6px; }}",
                ]
            )
        )

    def set_rows(
        self,
        rows: list[dict[str, str | LayerDefinition]],
        loaded_layer_keys: set[str],
        active_color: str,
    ) -> None:
        self._rows = list(rows)
        self._active_color = active_color or self._active_color
        self.layers_list.clear()
        unavailable_header_added = False
        grouped_rows: dict[str, list[dict[str, str | LayerDefinition]]] = {}

        for row in rows:
            datasource_id = str(row.get("datasource_id", ""))
            source_name = str(row.get("source_name", ""))
            source_type = str(row.get("source_type", ""))
            loadable = bool(row.get("loadable", True))
            availability_reason = str(row.get("availability_reason", "")).strip()
            display_group = str(row.get("business_group", "")).strip()
            category = _display_category_label(display_group)
            layer = row.get("layer")
            if not datasource_id or layer is None or not isinstance(layer, LayerDefinition):
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

            grouped_rows.setdefault(category, []).append(row)

        for category in sorted(grouped_rows.keys(), key=str.casefold):
            category_header = QListWidgetItem(category)
            category_font = category_header.font()
            category_font.setBold(True)
            category_header.setFont(category_font)
            if _NO_ITEM_FLAGS is not None:
                category_header.setFlags(_NO_ITEM_FLAGS)
            self.layers_list.addItem(category_header)

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
                loaded = layer_key in loaded_layer_keys
                status_icon = self._build_status_icon(loaded and loadable)

                item = QListWidgetItem(f"  {layer.display_name}  [{source_name}]")
                item.setData(USER_ROLE, (datasource_id, layer.layer_name, layer_key, loadable))
                item.setToolTip(
                    f"Category: {category}\n"
                    f"Source: {source_name} ({source_type})\n"
                    f"Layer: {layer.display_name}\n"
                    f"Geometry: {layer.geometry_type or 'Unknown'}\n"
                    f"CRS: {layer.default_crs or 'Not set'}\n"
                    f"Loadable: {'Yes' if loadable else 'No'}\n"
                    f"Loaded: {'Yes' if loaded else 'No'}"
                )
                if not loadable and availability_reason:
                    item.setToolTip(f"{item.toolTip()}\nReason: {availability_reason}")
                item.setIcon(status_icon)
                self.layers_list.addItem(item)

    def refresh_loaded_state(self, loaded_layer_keys: set[str]) -> None:
        for index in range(self.layers_list.count()):
            item = self.layers_list.item(index)
            payload = item.data(USER_ROLE)
            if not payload or len(payload) < 3:
                continue
            layer_key = str(payload[2])
            loadable = True if len(payload) < 4 else bool(payload[3])
            loaded = (layer_key in loaded_layer_keys) and loadable
            item.setIcon(self._build_status_icon(loaded))
            tooltip = item.toolTip() or ""
            if "Loaded:" in tooltip:
                tooltip = tooltip.rsplit("Loaded:", 1)[0].rstrip() + f"\nLoaded: {'Yes' if loaded else 'No'}"
            item.setToolTip(tooltip)

    def _build_status_icon(self, loaded: bool) -> Any:
        try:
            from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
        except ImportError:  # pragma: no cover - test fallback
            try:
                from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
            except ImportError:  # pragma: no cover
                return None

        size = 10
        pix = QPixmap(size, size)
        transparent = getattr(Qt, "transparent", None)
        if transparent is not None:
            pix.fill(transparent)

        painter = QPainter(pix)
        antialiasing = getattr(QPainter, "Antialiasing", None)
        if antialiasing is None:
            render_hint = getattr(QPainter, "RenderHint", None)
            if render_hint is not None:
                antialiasing = getattr(render_hint, "Antialiasing", None)
        if antialiasing is not None:
            painter.setRenderHint(antialiasing)

        color = QColor(self._active_color if loaded else "#A8B3C4")
        pen = QPen(color)
        pen.setWidth(1)
        painter.setPen(pen)

        if loaded:
            painter.setBrush(color)
        else:
            no_brush = getattr(Qt, "NoBrush", None)
            if no_brush is not None:
                painter.setBrush(no_brush)

        painter.drawEllipse(1, 1, size - 2, size - 2)
        painter.end()
        return QIcon(pix)

    def _on_layer_double_clicked(self, item: QListWidgetItem) -> None:
        payload = item.data(USER_ROLE)
        if not payload:
            return
        datasource_id, layer_name = payload[0], payload[1]
        loadable = True if len(payload) < 4 else bool(payload[3])
        if not loadable:
            return
        self.load_layer_requested.emit(str(datasource_id), str(layer_name))
