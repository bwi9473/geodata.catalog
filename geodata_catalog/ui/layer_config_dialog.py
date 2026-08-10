from __future__ import annotations

from geodata_catalog.metadata.layer_config_repository import LayerConfig

try:
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
    )
except ImportError:  # pragma: no cover
    Qt = None
    QCheckBox = None
    QComboBox = None
    QDialog = object
    QFormLayout = None
    QGroupBox = None
    QHBoxLayout = None
    QLabel = None
    QLineEdit = None
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
    ) -> None:
        if QDialog is object:  # pragma: no cover
            raise RuntimeError("QGIS runtime is not available.")
        super().__init__(parent)
        self._datasource_id = datasource_id
        self._layer_name = layer_name
        self.setWindowTitle("Layer Configuration")
        self.setModal(True)
        self.resize(560, 400)
        self._build_ui(display_name or layer_name)
        if existing_config is not None:
            self._populate(existing_config)

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
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g. ROUTE_NAME  (leave empty to disable)")
        self._label_edit.setClearButtonEnabled(True)
        self._enable_fl_filter_check = QCheckBox("Enable Flight Level Filter")
        self._enable_fl_filter_check.setChecked(True)
        label_form.addRow("Layer name", self._layername_edit)
        label_form.addRow("Field name", self._label_edit)
        label_form.addRow("", self._enable_fl_filter_check)
        layout.addWidget(label_group)

        # -- Searchable columns --
        search_group = QGroupBox("Searchable Columns")
        search_layout = QVBoxLayout(search_group)

        self._search_table = QTableWidget(0, 5)
        self._search_table.setHorizontalHeaderLabels(
            ["Field Name", "Display Label", "Data Type", "Use Distinct", "Filter By"]
        )
        self._search_table.horizontalHeader().setStretchLastSection(True)
        self._search_table.setColumnWidth(0, 150)
        self._search_table.setColumnWidth(1, 130)
        self._search_table.setColumnWidth(2, 90)
        self._search_table.setColumnWidth(3, 80)
        self._search_table.setColumnWidth(4, 120)
        self._search_table.setMinimumHeight(140)
        search_layout.addWidget(self._search_table)

        tbl_buttons = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        remove_btn = QPushButton("Remove Row")
        add_btn.clicked.connect(self._add_search_row)
        remove_btn.clicked.connect(self._remove_search_row)
        tbl_buttons.addWidget(add_btn)
        tbl_buttons.addWidget(remove_btn)
        tbl_buttons.addStretch(1)
        search_layout.addLayout(tbl_buttons)

        layout.addWidget(search_group)

        # -- Custom view columns --
        view_group = QGroupBox("Custom View Columns")
        view_layout = QVBoxLayout(view_group)

        self._view_table = QTableWidget(0, 3)
        self._view_table.setHorizontalHeaderLabels(["Field Name", "Display Label", "Data Type"])
        self._view_table.horizontalHeader().setStretchLastSection(True)
        self._view_table.setColumnWidth(0, 200)
        self._view_table.setColumnWidth(1, 170)
        self._view_table.setMinimumHeight(140)
        view_layout.addWidget(self._view_table)

        view_buttons = QHBoxLayout()
        add_view_btn = QPushButton("Add Row")
        remove_view_btn = QPushButton("Remove Row")
        add_view_btn.clicked.connect(self._add_view_row)
        remove_view_btn.clicked.connect(self._remove_view_row)
        view_buttons.addWidget(add_view_btn)
        view_buttons.addWidget(remove_view_btn)
        view_buttons.addStretch(1)
        view_layout.addLayout(view_buttons)

        layout.addWidget(view_group)

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

    def _add_search_row(self) -> None:
        row = self._search_table.rowCount()
        self._search_table.insertRow(row)
        self._set_type_combo_at_row(self._search_table, row, "varchar")
        # Add checkbox widget for "Use Distinct" in column 3
        checkbox = QCheckBox()
        checkbox.setChecked(False)
        self._search_table.setCellWidget(row, 3, checkbox)
        # Add free-text field for "Filter By" in column 4
        filter_by_edit = QLineEdit()
        filter_by_edit.setPlaceholderText("parent field name (optional)")
        filter_by_edit.setClearButtonEnabled(True)
        self._search_table.setCellWidget(row, 4, filter_by_edit)

    def _remove_search_row(self) -> None:
        current = self._search_table.currentRow()
        if current >= 0:
            self._search_table.removeRow(current)

    def _add_view_row(self) -> None:
        row = self._view_table.rowCount()
        self._view_table.insertRow(row)
        self._set_type_combo_at_row(self._view_table, row, "varchar")

    def _remove_view_row(self) -> None:
        current = self._view_table.currentRow()
        if current >= 0:
            self._view_table.removeRow(current)

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def get_config(self) -> LayerConfig:
        """Return the dialog state as a new :class:`LayerConfig`."""
        layername = self._layername_edit.text().strip() or None
        label_col = self._label_edit.text().strip() or None

        searchable_columns: list[dict[str, str | bool]] = []
        for row in range(self._search_table.rowCount()):
            name_item = self._search_table.item(row, 0)
            label_item = self._search_table.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            label = label_item.text().strip() if label_item else ""
            type_combo = self._search_table.cellWidget(row, 2)
            data_type = "varchar"
            if type_combo is not None and hasattr(type_combo, "currentText"):
                data_type = type_combo.currentText().strip().lower() or "varchar"
            # Get "Use Distinct" checkbox value
            use_distinct_widget = self._search_table.cellWidget(row, 3)
            use_distinct = False
            if use_distinct_widget is not None and hasattr(use_distinct_widget, "isChecked"):
                use_distinct = use_distinct_widget.isChecked()
            # Get "Filter By" value
            filter_by_widget = self._search_table.cellWidget(row, 4)
            filter_by = ""
            if filter_by_widget is not None and hasattr(filter_by_widget, "text"):
                filter_by = filter_by_widget.text().strip()
            col_entry: dict[str, str | bool] = {
                "name": name,
                "label": label or name,
                "type": data_type,
                "use_distinct": use_distinct,
            }
            if filter_by:
                col_entry["filter_by"] = filter_by
            searchable_columns.append(col_entry)

        view_columns: list[dict[str, str]] = []
        for row in range(self._view_table.rowCount()):
            name_item = self._view_table.item(row, 0)
            label_item = self._view_table.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            label = label_item.text().strip() if label_item else ""
            type_combo = self._view_table.cellWidget(row, 2)
            data_type = "varchar"
            if type_combo is not None and hasattr(type_combo, "currentText"):
                data_type = type_combo.currentText().strip().lower() or "varchar"
            view_columns.append({
                "name": name,
                "label": label or name,
                "type": data_type,
            })

        return LayerConfig(
            datasource_id=self._datasource_id,
            layer_name=self._layer_name,
            layername=layername,
            label_column=label_col,
            enable_fl_filter=bool(self._enable_fl_filter_check.isChecked()),
            searchable_columns=searchable_columns,
            view_columns=view_columns,
        )

    # ------------------------------------------------------------------ #
    # Pre-populate                                                        #
    # ------------------------------------------------------------------ #

    def _populate(self, config: LayerConfig) -> None:
        self._layername_edit.setText(config.layername or "")
        self._label_edit.setText(config.label_column or "")
        self._enable_fl_filter_check.setChecked(bool(config.enable_fl_filter))
        self._search_table.setRowCount(0)
        for col in config.searchable_columns:
            row = self._search_table.rowCount()
            self._search_table.insertRow(row)
            self._search_table.setItem(row, 0, QTableWidgetItem(col.get("name", "")))
            self._search_table.setItem(row, 1, QTableWidgetItem(col.get("label", "")))
            self._set_type_combo_at_row(self._search_table, row, col.get("type", "varchar"))
            # Restore "Use Distinct" checkbox value
            checkbox = QCheckBox()
            checkbox.setChecked(bool(col.get("use_distinct", False)))
            self._search_table.setCellWidget(row, 3, checkbox)
            # Restore "Filter By" value
            filter_by_edit = QLineEdit()
            filter_by_edit.setPlaceholderText("parent field name (optional)")
            filter_by_edit.setClearButtonEnabled(True)
            filter_by_edit.setText(col.get("filter_by", "") or "")
            self._search_table.setCellWidget(row, 4, filter_by_edit)

        self._view_table.setRowCount(0)
        for col in config.view_columns:
            row = self._view_table.rowCount()
            self._view_table.insertRow(row)
            self._view_table.setItem(row, 0, QTableWidgetItem(col.get("name", "")))
            self._view_table.setItem(row, 1, QTableWidgetItem(col.get("label", "")))
            self._set_type_combo_at_row(self._view_table, row, col.get("type", "varchar"))

    def _set_type_combo_at_row(self, table, row: int, value: str) -> None:
        combo = QComboBox()
        combo.addItem("varchar")
        combo.addItem("numeric")
        selected = (value or "varchar").strip().lower()
        idx = combo.findText(selected)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        table.setCellWidget(row, 2, combo)
