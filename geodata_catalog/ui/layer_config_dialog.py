from __future__ import annotations

from collections.abc import Callable

from geodata_catalog.metadata.layer_config_repository import LayerConfig

try:
    from qgis.PyQt.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
    )
except ImportError:  # pragma: no cover
    QCheckBox = None
    QComboBox = None
    QDialog = object
    QFormLayout = None
    QGroupBox = None
    QHBoxLayout = None
    QLabel = None
    QLineEdit = None
    QMessageBox = None
    QPushButton = None
    QTableWidget = None
    QTableWidgetItem = None
    QVBoxLayout = None


class LayerConfigDialog(QDialog):
    """Dialog for editing per-layer display and search configuration.

    Stores its result as a :class:`LayerConfig` object that is persisted in
    the separate ``layer_config.json`` file by the calling plugin handler.

    Parameters
    ----------
    parent:
        Qt parent widget.
    datasource_id:
        ID of the owning datasource.
    layer_name:
        Technical layer name (used as the unique key).
    display_name:
        Human-readable layer name shown in the dialog title.
    existing_config:
        Pre-existing ``LayerConfig`` to pre-populate the controls, or ``None``
        for a blank/default state.
    """

    def __init__(
        self,
        parent=None,
        datasource_id: str = "",
        layer_name: str = "",
        display_name: str = "",
        existing_config: LayerConfig | None = None,
        available_fields: list[dict[str, str]] | None = None,
        refresh_fields: Callable[[], list[dict[str, str]]] | None = None,
    ) -> None:
        if QDialog is object:  # pragma: no cover
            raise RuntimeError("QGIS runtime is not available.")
        super().__init__(parent)
        self._datasource_id = datasource_id
        self._layer_name = layer_name
        self._refresh_fields = refresh_fields
        self._field_positions: dict[int, int] = {}
        self.setWindowTitle("Layer Configuration")
        self.setModal(True)
        self.resize(800, 540)
        self._build_ui(display_name or layer_name)
        if existing_config is not None:
            self._populate(existing_config, available_fields or [])
        else:
            self._populate_field_columns(available_fields or [])

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self, display_name: str) -> None:
        layout = QVBoxLayout(self)

        title = QLabel(f"<b>{display_name}</b>")
        layout.addWidget(title)

        # -- Label column --
        label_group = QGroupBox("Label Column")
        label_form = QFormLayout(label_group)
        self._layername_edit = QLineEdit()
        self._layername_edit.setPlaceholderText(
            "Name shown in QGIS Layers panel (leave empty to use default source name)"
        )
        self._layername_edit.setClearButtonEnabled(True)
        self._category_label_edit = QLineEdit()
        self._category_label_edit.setPlaceholderText(
            "Category shown in catalog (leave empty to use Miscellaneous)"
        )
        self._category_label_edit.setClearButtonEnabled(True)
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g. ROUTE_NAME  (leave empty to disable)")
        self._label_edit.setClearButtonEnabled(True)
        self._enable_fl_filter_check = QCheckBox("Enable Flight Level Filter")
        self._enable_fl_filter_check.setChecked(True)
        label_form.addRow("Layer name", self._layername_edit)
        label_form.addRow("Category", self._category_label_edit)
        label_form.addRow("Field name", self._label_edit)
        label_form.addRow("", self._enable_fl_filter_check)
        layout.addWidget(label_group)

        fields_group = QGroupBox("Layer Attributes")
        fields_layout = QVBoxLayout(fields_group)
        self._fields_table = QTableWidget(0, 8)
        self._fields_table.setHorizontalHeaderLabels(
            ["Field Name", "Display Label", "Data Type", "Search", "Export", "Key Column", "Use Distinct", "Filter By"]
        )
        self._fields_table.horizontalHeader().setStretchLastSection(True)
        for column, width in enumerate([150, 150, 90, 60, 60, 85, 80]):
            self._fields_table.setColumnWidth(column, width)
        self._fields_table.setMinimumHeight(250)
        fields_layout.addWidget(self._fields_table)

        field_buttons = QHBoxLayout()
        refresh_btn = QPushButton("Refresh Attributes")
        refresh_btn.clicked.connect(self._on_refresh_fields)
        field_buttons.addWidget(refresh_btn)
        field_buttons.addStretch(1)
        fields_layout.addLayout(field_buttons)
        layout.addWidget(fields_group)

        # -- Buttons --
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        save_btn = QPushButton("Save")
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------ #
    # Slot handlers                                                        #
    # ------------------------------------------------------------------ #

    def _on_refresh_fields(self) -> None:
        if self._refresh_fields is None:
            return
        standard_button = getattr(QMessageBox, "StandardButton", QMessageBox)
        yes_button = standard_button.Yes
        no_button = standard_button.No
        response = QMessageBox.warning(
            self,
            "Refresh Attributes",
            "Refreshing attributes will clear the existing field configuration. Continue?",
            yes_button | no_button,
            no_button,
        )
        if response != yes_button:
            return
        self._populate_field_columns(self._refresh_fields())

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def get_config(self) -> LayerConfig:
        """Return the dialog state as a new :class:`LayerConfig`."""
        layername = self._layername_edit.text().strip() or None
        category_label = self._category_label_edit.text().strip() or None
        label_col = self._label_edit.text().strip() or None

        field_columns = self._field_columns_from_table()
        key_column = next((column["name"] for column in field_columns if column["key"]), None)

        return LayerConfig(
            datasource_id=self._datasource_id,
            layer_name=self._layer_name,
            layername=layername,
            category_label=category_label,
            label_column=label_col,
            enable_fl_filter=bool(self._enable_fl_filter_check.isChecked()),
            field_columns=field_columns,
            key_column=key_column,
        )

    # ------------------------------------------------------------------ #
    # Pre-populate                                                        #
    # ------------------------------------------------------------------ #

    def _populate(self, config: LayerConfig, available_fields: list[dict[str, str]]) -> None:
        self._layername_edit.setText(config.layername or "")
        self._category_label_edit.setText(config.category_label or "")
        self._label_edit.setText(config.label_column or "")
        self._enable_fl_filter_check.setChecked(bool(config.enable_fl_filter))
        field_columns = self._merge_field_columns(config.field_columns, available_fields)
        self._populate_field_columns(field_columns)

    @staticmethod
    def _runtime_column(column: dict[str, str | bool]) -> dict[str, str | bool]:
        runtime = {key: column[key] for key in ("name", "label", "type", "use_distinct", "filter_by") if key in column}
        return runtime

    @staticmethod
    def _merge_field_columns(
        configured_columns: list[dict[str, str | bool]],
        available_fields: list[dict[str, str]],
    ) -> list[dict[str, str | bool]]:
        configured_by_name = {
            str(column.get("name", "")).casefold(): dict(column)
            for column in configured_columns
            if column.get("name")
        }
        merged: list[dict[str, str | bool]] = []
        for position, field in enumerate(available_fields):
            name = str(field.get("name", "")).strip()
            if not name:
                continue
            column = configured_by_name.pop(name.casefold(), {})
            merged.append({
                "name": name,
                "label": str(column.get("label", field.get("label", name))),
                "type": str(column.get("type", field.get("type", "varchar"))),
                "position": position,
                "search": bool(column.get("search", False)),
                "export": bool(column.get("export", False)),
                "key": bool(column.get("key", False)),
                "use_distinct": bool(column.get("use_distinct", False)),
                **({"filter_by": str(column["filter_by"])} if column.get("filter_by") else {}),
            })
        return merged or list(configured_by_name.values())

    def _populate_field_columns(self, columns: list[dict[str, str | bool]]) -> None:
        ordered = sorted(
            enumerate(columns),
            key=lambda value: (
                not any(bool(value[1].get(key, False)) for key in ("search", "export", "key")),
                int(value[1].get("position", value[0])),
            ),
        )
        self._fields_table.setRowCount(0)
        self._field_positions = {}
        for fallback_position, column in ordered:
            row = self._fields_table.rowCount()
            self._fields_table.insertRow(row)
            name = str(column.get("name", ""))
            name_item = QTableWidgetItem(name)
            self._field_positions[row] = int(column.get("position", fallback_position))
            self._fields_table.setItem(row, 0, name_item)
            self._fields_table.setItem(row, 1, QTableWidgetItem(str(column.get("label", name))))
            self._set_type_combo_at_row(self._fields_table, row, str(column.get("type", "varchar")))
            for index, key in ((3, "search"), (4, "export"), (5, "key"), (6, "use_distinct")):
                checkbox = QCheckBox()
                checkbox.setChecked(bool(column.get(key, False)))
                self._fields_table.setCellWidget(row, index, checkbox)
                if key == "key":
                    checkbox.toggled.connect(
                        lambda checked, current_row=row: self._on_key_column_toggled(current_row, checked)
                    )
            filter_by_edit = QLineEdit(str(column.get("filter_by", "") or ""))
            filter_by_edit.setPlaceholderText("parent field name (optional)")
            filter_by_edit.setClearButtonEnabled(True)
            self._fields_table.setCellWidget(row, 7, filter_by_edit)

    def _on_key_column_toggled(self, selected_row: int, checked: bool) -> None:
        if not checked:
            return
        for row in range(self._fields_table.rowCount()):
            if row != selected_row:
                self._fields_table.cellWidget(row, 5).setChecked(False)

    def _field_columns_from_table(self) -> list[dict[str, str | bool]]:
        columns: list[dict[str, str | bool]] = []
        for row in range(self._fields_table.rowCount()):
            name_item = self._fields_table.item(row, 0)
            label_item = self._fields_table.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            type_combo = self._fields_table.cellWidget(row, 2)
            filter_by_edit = self._fields_table.cellWidget(row, 7)
            entry: dict[str, str | bool] = {
                "name": name,
                "label": label_item.text().strip() if label_item and label_item.text().strip() else name,
                "type": type_combo.currentText().strip().lower() if type_combo else "varchar",
                "search": bool(self._fields_table.cellWidget(row, 3).isChecked()),
                "export": bool(self._fields_table.cellWidget(row, 4).isChecked()),
                "key": bool(self._fields_table.cellWidget(row, 5).isChecked()),
                "use_distinct": bool(self._fields_table.cellWidget(row, 6).isChecked()),
                "position": self._field_positions.get(row, row),
            }
            if filter_by_edit and filter_by_edit.text().strip():
                entry["filter_by"] = filter_by_edit.text().strip()
            columns.append(entry)
        return columns

    def _set_type_combo_at_row(self, table, row: int, value: str) -> None:
        combo = QComboBox()
        combo.addItem("varchar")
        combo.addItem("numeric")
        selected = (value or "varchar").strip().lower()
        idx = combo.findText(selected)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        table.setCellWidget(row, 2, combo)
