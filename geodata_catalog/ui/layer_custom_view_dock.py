from __future__ import annotations

import csv
from pathlib import Path

from geodata_catalog.logging_utils import PluginLogger

try:
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import (
        QComboBox,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover
    Qt = None
    QComboBox = None
    QFileDialog = None
    QHBoxLayout = None
    QLabel = None
    QMainWindow = object
    QMessageBox = None
    QPushButton = None
    QSpinBox = None
    QTableWidget = None
    QTableWidgetItem = None
    QVBoxLayout = None
    QWidget = None


def _get_item_flags():
    """Get PyQt5/PyQt6 compatible item flags."""
    if Qt is None:
        return None
    # PyQt5: Qt.ItemIsEnabled, PyQt6: Qt.ItemFlag.ItemIsEnabled
    item_enabled = getattr(Qt, "ItemIsEnabled", None)
    if item_enabled is not None:
        # PyQt5 path
        item_enabled_val = item_enabled
        item_checkable = Qt.ItemIsUserCheckable
        item_selectable = Qt.ItemIsSelectable
        check_state_checked = Qt.Checked
        check_state_unchecked = Qt.Unchecked
        user_role = Qt.UserRole
    else:
        # PyQt6 path
        item_enabled_val = getattr(Qt.ItemFlag, "ItemIsEnabled", 1)
        item_checkable = getattr(Qt.ItemFlag, "ItemIsUserCheckable", 8)
        item_selectable = getattr(Qt.ItemFlag, "ItemIsSelectable", 32)
        # For CheckState in PyQt6
        check_state_obj = getattr(Qt, "CheckState", None)
        if check_state_obj is not None:
            check_state_checked = getattr(check_state_obj, "Checked", 2)
            check_state_unchecked = getattr(check_state_obj, "Unchecked", 0)
        else:
            check_state_checked = 2
            check_state_unchecked = 0
        user_role = getattr(Qt, "UserRole", 32)
    return {
        "enabled": item_enabled_val,
        "checkable": item_checkable,
        "selectable": item_selectable,
        "checked": check_state_checked,
        "unchecked": check_state_unchecked,
        "user_role": user_role,
    }


_ITEM_FLAGS = _get_item_flags() if Qt is not None else None


def _get_widget_attribute_delete_on_close():
    """Get PyQt5/PyQt6 compatible WA_DeleteOnClose enum value."""
    if Qt is None:
        return None
    attr = getattr(Qt, "WA_DeleteOnClose", None)
    if attr is not None:
        return attr
    widget_attr = getattr(Qt, "WidgetAttribute", None)
    if widget_attr is not None:
        return getattr(widget_attr, "WA_DeleteOnClose", None)
    return None


_WA_DELETE_ON_CLOSE = _get_widget_attribute_delete_on_close()


class LayerCustomViewWindow(QMainWindow):
    """Excel-like custom view window for loaded layer features."""

    def __init__(
        self,
        parent=None,
        layer=None,
        layer_name: str = "",
        columns: list[dict[str, str]] | None = None,
        records: list[dict[str, object]] | None = None,
        logger: PluginLogger | None = None,
    ) -> None:
        if QMainWindow is object:  # pragma: no cover
            raise RuntimeError("QGIS runtime is not available.")
        super().__init__(parent)
        self.setWindowTitle(f"Custom View - {layer_name or 'Layer'}")
        if _WA_DELETE_ON_CLOSE is not None:
            self.setAttribute(_WA_DELETE_ON_CLOSE, True)
        self._logger = logger
        self._layer = layer
        self._columns = [c for c in (columns or []) if c.get("name")]
        self._all_records = records or []
        self._current_records: list[dict[str, object]] = []
        self._current_fids: list[int] = []
        self._checked_fids: set[int] = set()
        self._current_page = 1
        self._updating_table = False

        # Create central widget with layout
        body = QWidget(self)
        self.setCentralWidget(body)
        self._root = QVBoxLayout(body)

        self._build_controls()
        self._build_table()
        self._apply_view_state()
        
        # Set reasonable default window size
        self.resize(900, 600)

    def _build_controls(self) -> None:
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Sort by"))

        self._sort_column_combo = QComboBox()
        for col in self._columns:
            self._sort_column_combo.addItem(col.get("label", col["name"]), col["name"])

        self._sort_order_combo = QComboBox()
        self._sort_order_combo.addItem("Ascending", "asc")
        self._sort_order_combo.addItem("Descending", "desc")

        self._page_size_spin = QSpinBox()
        self._page_size_spin.setRange(1, 500)
        self._page_size_spin.setValue(50)
        self._page_size_spin.setPrefix("Page size: ")

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._on_apply_clicked)

        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self._on_export_csv)

        export_excel_btn = QPushButton("Export Excel")
        export_excel_btn.clicked.connect(self._on_export_excel)

        controls.addWidget(self._sort_column_combo)
        controls.addWidget(self._sort_order_combo)
        controls.addWidget(self._page_size_spin)
        controls.addWidget(apply_btn)
        controls.addStretch(1)
        controls.addWidget(export_csv_btn)
        controls.addWidget(export_excel_btn)
        self._root.addLayout(controls)

        nav = QHBoxLayout()
        self._prev_btn = QPushButton("Previous")
        self._next_btn = QPushButton("Next")
        self._prev_btn.clicked.connect(self._on_prev_page)
        self._next_btn.clicked.connect(self._on_next_page)
        self._summary_label = QLabel("")
        nav.addWidget(self._prev_btn)
        nav.addWidget(self._next_btn)
        nav.addWidget(self._summary_label, stretch=1)
        self._root.addLayout(nav)

    def _build_table(self) -> None:
        column_count = len(self._columns) + 1
        self._table = QTableWidget(0, column_count)
        headers = [" "] + [c.get("label", c["name"]) for c in self._columns]
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setSelectionBehavior(self._table.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(self._table.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._on_row_selection_changed)
        self._table.itemChanged.connect(self._on_item_changed)

        self._table.setColumnWidth(0, 28)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._root.addWidget(self._table)

    def _on_apply_clicked(self) -> None:
        self._current_page = 1
        self._apply_view_state()

    def _on_prev_page(self) -> None:
        if self._current_page > 1:
            self._current_page -= 1
            self._apply_view_state()

    def _on_next_page(self) -> None:
        _, _, total_pages = self._paginate(self._sorted_records())
        if self._current_page < total_pages:
            self._current_page += 1
            self._apply_view_state()

    def _apply_view_state(self) -> None:
        page_records, page_fids, total_pages = self._paginate(self._sorted_records())
        self._current_records = page_records
        self._current_fids = page_fids
        self._fill_table()

        total = len(self._all_records)
        shown = len(self._current_records)
        self._summary_label.setText(
            f"Showing {shown} of {total} records - Page {self._current_page}/{total_pages}"
        )
        self._prev_btn.setEnabled(self._current_page > 1)
        self._next_btn.setEnabled(self._current_page < total_pages)

    def _sorted_records(self) -> list[dict[str, object]]:
        entries = list(self._all_records)
        if not entries or self._sort_column_combo.count() == 0:
            return entries

        col_name = self._sort_column_combo.currentData()
        reverse = self._sort_order_combo.currentData() == "desc"
        data_type = self._column_type(col_name)

        def _key(rec: dict[str, object]):
            val = rec.get(col_name)
            if val is None:
                return (1, 0)
            if data_type == "numeric":
                try:
                    return (0, float(val))
                except Exception:
                    return (1, 0)
            return (0, str(val).lower())

        entries.sort(key=_key, reverse=reverse)
        return entries

    def _paginate(self, entries: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[int], int]:
        page_size = max(1, int(self._page_size_spin.value()))
        total = len(entries)
        total_pages = max(1, (total + page_size - 1) // page_size)
        if self._current_page > total_pages:
            self._current_page = total_pages
        start = (self._current_page - 1) * page_size
        end = start + page_size
        page = entries[start:end]
        return page, [int(r.get("__fid", -1)) for r in page], total_pages

    def _column_type(self, col_name: str) -> str:
        for col in self._columns:
            if col.get("name") == col_name:
                return (col.get("type", "varchar") or "varchar").strip().lower()
        return "varchar"

    def _fill_table(self) -> None:
        self._updating_table = True
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._current_records))

        for row_idx, record in enumerate(self._current_records):
            check_item = QTableWidgetItem("")
            check_item.setFlags(
                _ITEM_FLAGS["enabled"] | _ITEM_FLAGS["checkable"] | _ITEM_FLAGS["selectable"]
            )
            fid = self._current_fids[row_idx]
            check_item.setCheckState(_ITEM_FLAGS["checked"] if fid in self._checked_fids else _ITEM_FLAGS["unchecked"])
            check_item.setData(_ITEM_FLAGS["user_role"], fid)
            self._table.setItem(row_idx, 0, check_item)

            for col_idx, col in enumerate(self._columns, start=1):
                key = col["name"]
                value = record.get(key, "")
                item = QTableWidgetItem("" if value is None else str(value))
                item.setFlags(_ITEM_FLAGS["enabled"] | _ITEM_FLAGS["selectable"])
                self._table.setItem(row_idx, col_idx, item)

        self._table.blockSignals(False)
        self._updating_table = False

    def _on_item_changed(self, item) -> None:
        if self._updating_table:
            return
        if item.column() != 0:
            return
        fid = item.data(_ITEM_FLAGS["user_role"])
        if fid is None or fid < 0 or self._layer is None:
            return

        if item.checkState() == _ITEM_FLAGS["checked"]:
            self._checked_fids.add(fid)
        else:
            self._checked_fids.discard(fid)

        try:
            if self._checked_fids:
                self._layer.selectByIds(sorted(self._checked_fids))
            else:
                self._layer.removeSelection()
        except Exception as exc:
            if self._logger is not None:
                self._logger.warning(f"Unable to apply checkbox selection on map: {exc}")

    def _on_row_selection_changed(self) -> None:
        if self._layer is None:
            return
        selected = self._table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        if row < 0 or row >= len(self._current_fids):
            return
        fid = self._current_fids[row]
        if fid < 0:
            return
        try:
            self._layer.selectByIds([fid])
        except Exception as exc:
            if self._logger is not None:
                self._logger.warning(f"Unable to select feature on map: {exc}")

    def _on_export_csv(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Custom View as CSV",
            str(Path.home() / "custom_view.csv"),
            "CSV Files (*.csv)",
        )
        if not file_path:
            return
        try:
            self._write_csv(Path(file_path))
            QMessageBox.information(self, "Export", f"CSV exported to:\n{file_path}")
        except Exception as exc:
            if self._logger is not None:
                self._logger.error(f"CSV export failed: {exc}")
            QMessageBox.warning(self, "Export", f"CSV export failed:\n{exc}")

    def _on_export_excel(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Custom View as Excel",
            str(Path.home() / "custom_view.xlsx"),
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return
        try:
            self._write_xlsx(Path(file_path))
            QMessageBox.information(self, "Export", f"Excel exported to:\n{file_path}")
        except Exception as exc:
            if self._logger is not None:
                self._logger.error(f"Excel export failed: {exc}")
            QMessageBox.warning(
                self,
                "Export",
                "Excel export failed. Install 'openpyxl' in QGIS Python environment, "
                f"or use CSV export.\n\nDetails:\n{exc}",
            )

    def _write_csv(self, file_path: Path) -> None:
        headers = [col.get("label", col["name"]) for col in self._columns]
        keys = [col["name"] for col in self._columns]
        with file_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for record in self._all_records:
                writer.writerow([record.get(key, "") for key in keys])

    def _write_xlsx(self, file_path: Path) -> None:
        try:
            from openpyxl import Workbook
        except ImportError as exc:
            raise RuntimeError("openpyxl is not installed") from exc

        wb = Workbook()
        ws = wb.active
        ws.title = "Custom View"

        headers = [col.get("label", col["name"]) for col in self._columns]
        keys = [col["name"] for col in self._columns]
        ws.append(headers)
        for record in self._all_records:
            ws.append([record.get(key, "") for key in keys])

        wb.save(str(file_path))


# Backward compatibility alias
LayerCustomViewDock = LayerCustomViewWindow
