from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Callable

from geodata_catalog.logging_utils import PluginLogger
from geodata_catalog.services.layer_filter_service import (
    AttributeSearchFilter,
    FlightLevelFilter,
    LayerFilter,
    LayerFilterService,
)

try:
    from qgis.core import QgsCoordinateTransformContext, QgsVectorFileWriter
    from qgis.PyQt.QtCore import QEvent, Qt
    from qgis.PyQt.QtGui import QColor
    from qgis.gui import QgsRubberBand
    from qgis.PyQt.QtWidgets import (
        QAbstractItemView,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
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
    QgsCoordinateTransformContext = None
    QgsVectorFileWriter = None
    QColor = None
    QgsRubberBand = None
    QEvent = None
    Qt = None
    QAbstractItemView = None
    QCheckBox = None
    QComboBox = None
    QDialog = None
    QDialogButtonBox = None
    QFileDialog = None
    QFormLayout = None
    QGroupBox = None
    QHBoxLayout = None
    QLabel = None
    QLineEdit = None
    QListWidget = None
    QListWidgetItem = None
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

    item_enabled = getattr(Qt, "ItemIsEnabled", None)
    if item_enabled is not None:
        item_enabled_val = item_enabled
        item_checkable = Qt.ItemIsUserCheckable
        item_selectable = Qt.ItemIsSelectable
        check_state_checked = Qt.Checked
        check_state_unchecked = Qt.Unchecked
        user_role = Qt.UserRole
    else:
        item_enabled_val = getattr(Qt.ItemFlag, "ItemIsEnabled", 1)
        item_checkable = getattr(Qt.ItemFlag, "ItemIsUserCheckable", 8)
        item_selectable = getattr(Qt.ItemFlag, "ItemIsSelectable", 32)
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


DEFAULT_UI_COLORS: dict[str, str] = {
    "primary": "#59A947",
    "primary_text": "#FFFFFF",
    "panel_background": "#F7F9FC",
    "window_background": "#FFFFFF",
    "text": "#1E293B",
    "border": "#D7DEE8",
    "header_background": "#EEF3FA",
    "header_text": "#0F172A",
}


def _set_combo_box_no_insert(combo: Any) -> None:
    """Prevent editable combos from adding ad-hoc items to the dropdown."""
    if QComboBox is None:
        return
    insert_policy = getattr(QComboBox, "NoInsert", None)
    if insert_policy is None:
        insert_policy_enum = getattr(QComboBox, "InsertPolicy", None)
        if insert_policy_enum is not None:
            insert_policy = getattr(insert_policy_enum, "NoInsert", None)
    if insert_policy is not None:
        combo.setInsertPolicy(insert_policy)


class LayerCustomViewWindow(QMainWindow):
    """Combined filter and custom-view window for a loaded QGIS layer."""

    _NUMERIC_VALUE_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
    _FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
    _EXPORT_FORMAT_CSV = "csv"
    _EXPORT_FORMAT_XLSX = "xlsx"
    _EXPORT_FORMAT_GEOJSON = "geojson"
    _EXPORT_FORMAT_KML = "kml"
    _MAX_EXPORT_FILENAME_LENGTH = 140

    def __init__(
        self,
        parent=None,
        layer=None,
        map_canvas=None,
        layer_name: str = "",
        columns: list[dict[str, str]] | None = None,
        records: list[dict[str, object]] | None = None,
        logger: PluginLogger | None = None,
        initial_filter: LayerFilter | None = None,
        searchable_columns: list[dict[str, str | bool]] | None = None,
        distinct_values: dict[str, list[str]] | None = None,
        filtered_distinct_values: dict[str, dict[str, list[str]]] | None = None,
        show_flight_level: bool = True,
        flight_level_presets: list[dict[str, int | str]] | None = None,
        on_filter_applied: Callable[[LayerFilter], None] | None = None,
        ui_colors: dict[str, str] | None = None,
    ) -> None:
        if QMainWindow is object:  # pragma: no cover
            raise RuntimeError("QGIS runtime is not available.")
        super().__init__(parent)
        self.setWindowTitle(f"Layer Filter + Custom View - {layer_name or 'Layer'}")
        if _WA_DELETE_ON_CLOSE is not None:
            self.setAttribute(_WA_DELETE_ON_CLOSE, True)

        self._logger = logger
        self._layer = layer
        self._map_canvas = map_canvas
        self._map_highlights: list[Any] = []
        self._columns = [c for c in (columns or []) if c.get("name")]
        self._all_records = records or []
        self._current_records: list[dict[str, object]] = []
        self._current_fids: list[int] = []
        self._checked_fids: set[int] = set()
        self._current_page = 1
        self._updating_table = False
        self._on_filter_applied = on_filter_applied

        self._searchable_columns = searchable_columns or []
        self._distinct_values = distinct_values or {}
        self._filtered_distinct_values = filtered_distinct_values or {}
        self._show_flight_level = bool(show_flight_level)
        self._flight_level_presets = self._normalize_flight_level_presets(flight_level_presets)

        self._ui_colors = self._normalize_ui_colors(ui_colors)

        self._enabled_check = None
        self._lower_spin = None
        self._upper_spin = None
        self._fl_lower_field_name = "fl_lower"
        self._fl_upper_field_name = "fl_upper"
        self._preset_buttons: list[tuple[Any, int, int]] = []

        self._attr_edits: dict[str, Any] = {}
        self._attr_combos: dict[str, Any] = {}
        self._attr_combo_line_edits: dict[int, Any] = {}
        self._lov_enabled_columns: set[str] = set()
        self._attr_labels: dict[str, str] = {}
        self._attr_types: dict[str, str] = {}
        self._filter_by_map: dict[str, str] = {}

        body = QWidget(self)
        self.setCentralWidget(body)
        self._root = QVBoxLayout(body)

        self._build_filter_panel(initial_filter)
        self._build_controls()
        self._build_table()
        self._apply_theme()
        self._apply_view_state()

        self.resize(1024, 720)

    @staticmethod
    def _normalize_ui_colors(ui_colors: dict[str, str] | None) -> dict[str, str]:
        palette = dict(DEFAULT_UI_COLORS)
        if not isinstance(ui_colors, dict):
            return palette
        for key, value in ui_colors.items():
            if key not in palette:
                continue
            raw = str(value or "").strip()
            if re.match(r"^#[0-9A-Fa-f]{6}$", raw):
                palette[key] = raw
        return palette

    @staticmethod
    def _normalize_flight_level_presets(
        raw_presets: list[dict[str, int | str]] | None,
    ) -> list[dict[str, int | str]]:
        if not raw_presets:
            return []

        normalized: list[dict[str, int | str]] = []
        for item in raw_presets:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            try:
                lower = int(item.get("lower", 0))
                upper = int(item.get("upper", 999))
            except (TypeError, ValueError):
                continue
            lower = max(0, min(999, lower))
            upper = max(0, min(999, upper))
            if lower > upper:
                lower, upper = upper, lower
            normalized.append({"name": name, "lower": lower, "upper": upper})
        return normalized

    def _build_filter_panel(self, initial_filter: LayerFilter | None) -> None:
        panel = QGroupBox("Filter")
        self._filter_panel = panel
        panel_layout = QVBoxLayout(panel)

        toggle_row = QHBoxLayout()
        self._toggle_fl_btn = QPushButton("Flight Levels")
        self._toggle_attr_btn = QPushButton("Attributes")
        self._reset_btn = QPushButton("Reset")
        self._save_btn = QPushButton("Save")

        self._toggle_fl_btn.setObjectName("FilterToggleButton")
        self._toggle_attr_btn.setObjectName("FilterToggleButton")

        self._toggle_fl_btn.setCheckable(True)
        self._toggle_attr_btn.setCheckable(True)
        self._toggle_fl_btn.setChecked(True)
        self._toggle_attr_btn.setChecked(True)

        self._toggle_fl_btn.clicked.connect(self._toggle_filter_sections)
        self._toggle_attr_btn.clicked.connect(self._toggle_filter_sections)
        self._reset_btn.clicked.connect(self._on_reset_filters)
        self._save_btn.clicked.connect(self._on_save_filters)

        toggle_row.addWidget(self._toggle_fl_btn)
        toggle_row.addWidget(self._toggle_attr_btn)
        toggle_row.addWidget(self._reset_btn)
        toggle_row.addWidget(self._save_btn)
        toggle_row.addStretch(1)
        panel_layout.addLayout(toggle_row)

        self._flight_group = self._build_flight_level_group()
        self._attr_group = self._build_attribute_group()

        if self._flight_group is not None:
            panel_layout.addWidget(self._flight_group)
        if self._attr_group is not None:
            panel_layout.addWidget(self._attr_group)

        search_row = QHBoxLayout()
        search_row.addStretch(1)
        self._search_btn = QPushButton("Search")
        self._search_btn.clicked.connect(self._on_search_clicked)
        search_row.addWidget(self._search_btn)
        panel_layout.addLayout(search_row)

        self._root.addWidget(panel)

        self._init_filter_state(initial_filter)
        self._refresh_filter_toggle_buttons()

    def _build_attribute_group(self):
        if not self._searchable_columns:
            return None

        for col_def in self._searchable_columns:
            col_name = col_def.get("name", "")
            filter_by = col_def.get("filter_by", "")
            if col_name and filter_by:
                self._filter_by_map[col_name] = str(filter_by)

        parent_cols_with_children: set[str] = set(self._filter_by_map.values())

        attr_group = QGroupBox("Attributes")
        attr_form = QFormLayout(attr_group)
        attr_form.setContentsMargins(12, 16, 12, 12)
        attr_form.setHorizontalSpacing(14)
        attr_form.setVerticalSpacing(10)

        helper_label = QLabel(
            "Choose from the list or type multiple values separated by commas."
        )
        helper_label.setWordWrap(True)
        helper_label.setObjectName("FilterHintLabel")
        attr_form.addRow(helper_label)

        for col_def in self._searchable_columns:
            col_name = col_def.get("name", "")
            label = col_def.get("label", col_name)
            data_type = (col_def.get("type", "varchar") or "varchar").strip().lower()
            use_distinct = bool(col_def.get("use_distinct", False))
            if not col_name:
                continue

            if use_distinct:
                self._lov_enabled_columns.add(col_name)
                combo = QComboBox()
                combo.setEditable(True)
                _set_combo_box_no_insert(combo)
                combo.setMaxVisibleItems(14)
                combo.setMinimumContentsLength(24)
                combo.setObjectName("FilterInput")
                distinct_vals = self._distinct_values.get(col_name, [])
                for val in sorted(set(v for v in distinct_vals if v)):
                    combo.addItem(str(val), str(val))
                combo_line_edit = combo.lineEdit()
                if combo_line_edit is not None:
                    combo_line_edit.setObjectName("FilterInput")
                    combo_line_edit.setClearButtonEnabled(True)
                    combo_line_edit.setPlaceholderText(
                        f"Choose or type {label.lower()} (comma-separated)"
                    )
                    combo_line_edit.textEdited.connect(
                        lambda text, current_combo=combo: self._on_combo_text_edited(
                            current_combo,
                            text,
                        )
                    )
                    combo_line_edit.editingFinished.connect(
                        lambda current_combo=combo: self._normalize_combo_editor_value(current_combo)
                    )
                    combo_line_edit.installEventFilter(self)
                    self._attr_combo_line_edits[id(combo_line_edit)] = combo

                completer = combo.completer()
                if completer is not None and Qt is not None:
                    case_insensitive = getattr(Qt, "CaseInsensitive", None)
                    if case_insensitive is None:
                        case_sensitivity = getattr(Qt, "CaseSensitivity", None)
                        if case_sensitivity is not None:
                            case_insensitive = getattr(case_sensitivity, "CaseInsensitive", None)
                    if case_insensitive is not None:
                        completer.setCaseSensitivity(case_insensitive)

                    match_contains = getattr(Qt, "MatchContains", None)
                    if match_contains is None:
                        match_flag = getattr(Qt, "MatchFlag", None)
                        if match_flag is not None:
                            match_contains = getattr(match_flag, "MatchContains", None)
                    if match_contains is not None and hasattr(completer, "setFilterMode"):
                        completer.setFilterMode(match_contains)

                    popup_completion = getattr(completer, "PopupCompletion", None)
                    if popup_completion is None:
                        completion_mode = getattr(completer, "CompletionMode", None)
                        if completion_mode is not None:
                            popup_completion = getattr(completion_mode, "PopupCompletion", None)
                    if popup_completion is not None and hasattr(completer, "setCompletionMode"):
                        completer.setCompletionMode(popup_completion)

                    completer.activated.connect(
                        lambda value, current_combo=combo: self._on_combo_completion_activated(
                            current_combo,
                            value,
                        )
                    )

                combo.currentTextChanged.connect(
                    lambda _, pc=col_name: self._on_parent_filter_changed(pc)
                    if pc in parent_cols_with_children
                    else None
                )

                lov_btn = QPushButton("LOV")
                lov_btn.setObjectName("FilterLovButton")
                lov_btn.setToolTip(f"Open value list for {label}")
                lov_btn.setFixedWidth(44)
                lov_btn.clicked.connect(
                    lambda _checked=False, cn=col_name, cl=label: self._open_lov_selector(cn, cl)
                )

                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(6)
                row_layout.addWidget(combo, 1)
                row_layout.addWidget(lov_btn)

                attr_form.addRow(label, row_widget)
                self._attr_combos[col_name] = combo
            else:
                edit = QLineEdit()
                edit.setPlaceholderText(f"Filter by {label} (comma-separated)")
                edit.setClearButtonEnabled(True)
                edit.setObjectName("FilterInput")
                edit.returnPressed.connect(self._on_search_clicked)
                attr_form.addRow(label, edit)
                self._attr_edits[col_name] = edit

            self._attr_labels[col_name] = str(label)
            self._attr_types[col_name] = data_type

        return attr_group

    def _build_flight_level_group(self):
        if not self._show_flight_level:
            return None

        fl_group = QGroupBox("Flight Levels")
        fl_form = QFormLayout(fl_group)

        self._enabled_check = QCheckBox("Enable flight level filter")
        self._enabled_check.setChecked(True)
        self._enabled_check.toggled.connect(lambda _checked: self._update_fl_controls_enabled())
        fl_form.addRow(self._enabled_check)

        self._lower_spin = QSpinBox()
        self._lower_spin.setRange(0, 999)
        self._lower_spin.setValue(0)

        self._upper_spin = QSpinBox()
        self._upper_spin.setRange(0, 999)
        self._upper_spin.setValue(600)

        spin_row = QHBoxLayout()
        spin_row.addWidget(QLabel("Lower FL (>=)"))
        spin_row.addWidget(self._lower_spin)
        spin_row.addSpacing(20)
        spin_row.addWidget(QLabel("Upper FL (<=)"))
        spin_row.addWidget(self._upper_spin)
        fl_form.addRow(spin_row)

        if self._flight_level_presets:
            preset_row = QHBoxLayout()
            for preset in self._flight_level_presets:
                lower = int(preset["lower"])
                upper = int(preset["upper"])
                button = QPushButton(str(preset["name"]))
                button.setCheckable(True)
                button.setToolTip(f"Set FL range to FL{lower} - FL{upper}")
                button.clicked.connect(
                    lambda _checked, lo=lower, hi=upper: self._on_preset_clicked(lo, hi)
                )
                preset_row.addWidget(button)
                self._preset_buttons.append((button, lower, upper))
            preset_row.addStretch(1)
            fl_form.addRow("Quick presets", preset_row)

        return fl_group

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

        self._export_format_combo = QComboBox()
        self._export_format_combo.addItem("CSV", self._EXPORT_FORMAT_CSV)
        self._export_format_combo.addItem("Excel", self._EXPORT_FORMAT_XLSX)
        self._export_format_combo.addItem("GeoJSON", self._EXPORT_FORMAT_GEOJSON)
        self._export_format_combo.addItem("KML", self._EXPORT_FORMAT_KML)
        self._export_format_combo.setCurrentIndex(0)
        self._export_format_combo.setToolTip("Choose export format for selected records")

        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._on_export_selected_records)

        controls.addWidget(self._sort_column_combo)
        controls.addWidget(self._sort_order_combo)
        controls.addWidget(self._page_size_spin)
        controls.addWidget(apply_btn)
        controls.addStretch(1)
        controls.addWidget(self._export_format_combo)
        controls.addWidget(export_btn)
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

    def _apply_theme(self) -> None:
        palette = self._ui_colors
        self.setStyleSheet(
            "\n".join(
                [
                    f"QMainWindow {{ background: {palette['window_background']}; color: {palette['text']}; }}",
                    f"QGroupBox {{ background: {palette['panel_background']}; border: 1px solid {palette['border']}; border-radius: 8px; margin-top: 12px; padding: 8px; }}",
                    "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }",
                    f"QHeaderView::section {{ background: {palette['header_background']}; color: {palette['header_text']}; border: 1px solid {palette['border']}; padding: 4px; }}",
                    f"QTableWidget {{ border: 1px solid {palette['border']}; gridline-color: {palette['border']}; }}",
                    f"QLineEdit#FilterInput, QComboBox#FilterInput {{ background: #FFFFFF; border: 1px solid {palette['border']}; border-radius: 6px; padding: 6px 8px; min-height: 24px; }}",
                    f"QLineEdit#FilterInput:focus, QComboBox#FilterInput:focus {{ border: 1px solid {palette['primary']}; }}",
                    f"QComboBox#FilterInput::drop-down {{ border: 0; width: 26px; }}",
                    f"QComboBox#FilterInput QAbstractItemView {{ border: 1px solid {palette['border']}; background: #FFFFFF; selection-background-color: {palette['header_background']}; selection-color: {palette['header_text']}; }}",
                    f"QLabel#FilterHintLabel {{ color: #475569; padding-bottom: 4px; }}",
                    f"QPushButton {{ border: 1px solid {palette['border']}; border-radius: 6px; padding: 6px 10px; }}",
                    f"QPushButton#FilterLovButton {{ background: #FFFFFF; color: {palette['text']}; font-size: 11px; padding: 4px 8px; }}",
                    f"QPushButton#FilterLovButton:hover {{ border-color: {palette['primary']}; }}",
                    f"QPushButton#FilterToggleButton {{ background: #FFFFFF; color: {palette['text']}; font-weight: 600; border: 1px solid {palette['border']}; }}",
                    f"QPushButton#FilterToggleButton:checked {{ background: {palette['primary']}; color: {palette['primary_text']}; border-color: {palette['primary']}; }}",
                    f"QPushButton#PrimaryButton {{ background: {palette['primary']}; color: {palette['primary_text']}; border-color: {palette['primary']}; font-weight: 600; }}",
                ]
            )
        )
        if hasattr(self, "_search_btn") and self._search_btn is not None:
            self._search_btn.setObjectName("PrimaryButton")
            self._search_btn.style().unpolish(self._search_btn)
            self._search_btn.style().polish(self._search_btn)

    def _toggle_filter_sections(self) -> None:
        if self._flight_group is not None:
            self._flight_group.setVisible(self._toggle_fl_btn.isChecked())
        if self._attr_group is not None:
            self._attr_group.setVisible(self._toggle_attr_btn.isChecked())
        self._refresh_filter_toggle_buttons()

    def _refresh_filter_toggle_buttons(self) -> None:
        fl_active = bool(self._toggle_fl_btn.isChecked())
        attr_active = bool(self._toggle_attr_btn.isChecked())

        self._toggle_fl_btn.setText(
            f"Flight Levels ({'active' if fl_active else 'off'})"
        )
        self._toggle_attr_btn.setText(
            f"Attributes ({'active' if attr_active else 'off'})"
        )

        active_count = int(fl_active) + int(attr_active)
        if hasattr(self, "_filter_panel") and self._filter_panel is not None:
            self._filter_panel.setTitle(f"Filter - {active_count} active")

    def _init_filter_state(self, initial_filter: LayerFilter | None) -> None:
        if initial_filter is None:
            initial_filter = LayerFilter(
                flight_level=FlightLevelFilter(
                    mode=LayerFilterService.MODE_NONE,
                    lower=0,
                    upper=600,
                    enabled=False,
                    lower_field="fl_lower",
                    upper_field="fl_upper",
                ),
                attributes=[],
            )

        fl = initial_filter.flight_level
        self._fl_lower_field_name = fl.lower_field or "fl_lower"
        self._fl_upper_field_name = fl.upper_field or "fl_upper"

        if self._show_flight_level and self._enabled_check is not None:
            self._enabled_check.setChecked(bool(fl.enabled))
            if self._lower_spin is not None:
                self._lower_spin.setValue(int(fl.lower))
            if self._upper_spin is not None:
                self._upper_spin.setValue(int(fl.upper))
            self._update_fl_controls_enabled()
            self._sync_preset_button_state(int(fl.lower), int(fl.upper))

        for attr in initial_filter.attributes:
            if attr.column in self._attr_edits:
                self._attr_edits[attr.column].setText(attr.value)
            elif attr.column in self._attr_combos:
                combo = self._attr_combos[attr.column]
                self._set_combo_filter_text(combo, attr.value)

    def _on_parent_filter_changed(self, parent_col: str) -> None:
        parent_combo = self._attr_combos.get(parent_col)
        if parent_combo is None:
            return

        for child_col, mapped_parent in self._filter_by_map.items():
            if mapped_parent != parent_col:
                continue
            child_combo = self._attr_combos.get(child_col)
            if child_combo is None:
                continue

            current_child_val = child_combo.currentText().strip()
            child_combo.blockSignals(True)
            child_combo.clear()

            candidate_vals = self._candidate_values_for_column(child_col)

            for val in sorted(set(v for v in candidate_vals if v)):
                child_combo.addItem(str(val), str(val))

            self._set_combo_filter_text(child_combo, current_child_val)
            child_combo.blockSignals(False)

    def _on_search_clicked(self) -> None:
        self._normalize_all_combo_filters()
        invalid_inputs: list[str] = []

        for col_name, edit in self._attr_edits.items():
            data_type = self._attr_types.get(col_name, "varchar")
            if data_type != "numeric":
                continue
            invalid_inputs.extend(self._invalid_numeric_tokens(col_name, edit.text().strip()))

        for col_name, combo in self._attr_combos.items():
            data_type = self._attr_types.get(col_name, "varchar")
            if data_type != "numeric":
                continue
            invalid_inputs.extend(
                self._invalid_numeric_tokens(col_name, self._normalized_filter_text(combo.currentText()))
            )

        if invalid_inputs:
            QMessageBox.warning(
                self,
                "Layer Filter",
                "Invalid numeric values found:\n- " + "\n- ".join(invalid_inputs),
            )
            return

        layer_filter = self._current_filter()

        if self._on_filter_applied is not None:
            try:
                self._on_filter_applied(layer_filter)
            except Exception as exc:
                if self._logger is not None:
                    self._logger.error(f"Unable to apply layer filter: {exc}")
                QMessageBox.warning(self, "Layer Filter", f"Unable to apply filter:\n{exc}")
                return

        self._reload_records_from_layer()
        self._current_page = 1
        self._apply_view_state()

    def _current_filter(self) -> LayerFilter:
        if self._show_flight_level and self._enabled_check is not None:
            lower = int(self._lower_spin.value()) if self._lower_spin is not None else 0
            upper = int(self._upper_spin.value()) if self._upper_spin is not None else 600
            if lower > upper:
                lower, upper = upper, lower
            fl_enabled = bool(self._enabled_check.isChecked())
            fl_mode = LayerFilterService.MODE_BETWEEN if fl_enabled else LayerFilterService.MODE_NONE
            fl_filter = FlightLevelFilter(
                mode=fl_mode,
                lower=lower,
                upper=upper,
                enabled=fl_enabled,
                lower_field=self._fl_lower_field_name,
                upper_field=self._fl_upper_field_name,
            )
        else:
            fl_filter = FlightLevelFilter(
                mode=LayerFilterService.MODE_NONE,
                lower=0,
                upper=600,
                enabled=False,
                lower_field="fl_lower",
                upper_field="fl_upper",
            )

        attrs: list[AttributeSearchFilter] = []
        for col_name, edit in self._attr_edits.items():
            value = edit.text().strip()
            if value:
                attrs.append(
                    AttributeSearchFilter(
                        column=col_name,
                        value=value,
                        label=col_name,
                        data_type=self._attr_types.get(col_name, "varchar"),
                    )
                )

        for col_name, combo in self._attr_combos.items():
            combo_value = self._normalized_filter_text(combo.currentText())
            if combo_value:
                attrs.append(
                    AttributeSearchFilter(
                        column=col_name,
                        value=combo_value,
                        label=col_name,
                        data_type=self._attr_types.get(col_name, "varchar"),
                    )
                )

        return LayerFilter(flight_level=fl_filter, attributes=attrs)

    def _on_reset_filters(self) -> None:
        if self._enabled_check is not None:
            self._enabled_check.setChecked(False)
        if self._lower_spin is not None:
            self._lower_spin.setValue(0)
        if self._upper_spin is not None:
            self._upper_spin.setValue(600)

        for edit in self._attr_edits.values():
            edit.clear()
        for combo in self._attr_combos.values():
            self._set_combo_filter_text(combo, "")

        self._sync_preset_button_state(0, 600)
        self._on_search_clicked()

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if (
            QEvent is not None
            and watched is not None
            and event is not None
            and id(watched) in self._attr_combo_line_edits
        ):
            combo = self._attr_combo_line_edits[id(watched)]
            focus_in = getattr(QEvent, "FocusIn", None)
            if focus_in is None:
                event_type_enum = getattr(QEvent, "Type", None)
                if event_type_enum is not None:
                    focus_in = getattr(event_type_enum, "FocusIn", None)

            if focus_in is not None and event.type() == focus_in:
                if combo.count() > 0:
                    combo.showPopup()

            key_press = getattr(QEvent, "KeyPress", None)
            if key_press is None:
                event_type_enum = getattr(QEvent, "Type", None)
                if event_type_enum is not None:
                    key_press = getattr(event_type_enum, "KeyPress", None)

            if key_press is not None and event.type() == key_press:
                key_value = event.key() if hasattr(event, "key") else None
                key_enter = getattr(Qt, "Key_Enter", None) if Qt is not None else None
                key_return = getattr(Qt, "Key_Return", None) if Qt is not None else None
                if key_enter is None and Qt is not None:
                    key_enum = getattr(Qt, "Key", None)
                    if key_enum is not None:
                        key_enter = getattr(key_enum, "Key_Enter", None)
                        key_return = getattr(key_enum, "Key_Return", None)

                if key_value in {key_enter, key_return}:
                    self._on_combo_enter_pressed(combo)
                    return True

                if hasattr(event, "text") and event.text() == ";":
                    self._insert_combo_separator(watched)
                    return True

        base_event_filter = getattr(super(), "eventFilter", None)
        if callable(base_event_filter):
            return bool(base_event_filter(watched, event))
        return False

    @staticmethod
    def _split_multi_value_text(raw_value: str) -> list[str]:
        return [part.strip() for part in str(raw_value or "").split(",") if part.strip()]

    @classmethod
    def _normalized_filter_text(cls, raw_value: str) -> str:
        return ", ".join(cls._split_multi_value_text(raw_value))

    def _set_combo_filter_text(self, combo: Any, raw_value: str) -> None:
        normalized_value = self._normalized_filter_text(raw_value)
        combo.blockSignals(True)
        if not normalized_value:
            combo.setCurrentIndex(-1)
            if combo.lineEdit() is not None:
                combo.lineEdit().clear()
            combo.blockSignals(False)
            return

        idx = combo.findData(normalized_value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(-1)
            if combo.lineEdit() is not None:
                combo.lineEdit().setText(normalized_value)
            else:
                combo.setEditText(normalized_value)
        combo.blockSignals(False)

    def _on_combo_text_edited(self, combo: Any, raw_text: str) -> None:
        completer = combo.completer() if hasattr(combo, "completer") else None
        if completer is None:
            return
        token = self._last_filter_token(raw_text)
        if not token:
            if hasattr(combo, "showPopup") and combo.count() > 0:
                combo.showPopup()
            return
        if hasattr(completer, "setCompletionPrefix"):
            completer.setCompletionPrefix(token)
        if hasattr(completer, "complete"):
            completer.complete()

    def _on_combo_completion_activated(self, combo: Any, value: Any) -> None:
        completion_value = str(value or "").strip()
        if not completion_value and hasattr(value, "row") and hasattr(combo, "itemText"):
            row = value.row()
            if row >= 0:
                completion_value = str(combo.itemText(row)).strip()
        if not completion_value:
            return
        
        # Merge the completion value with existing text to support multi-value filters
        merged = self._merge_last_filter_token(combo.currentText(), completion_value)
        self._set_combo_filter_text(combo, merged)
        self._append_trailing_separator(combo)
        
        # Hide completer popup and clear its state to prevent Qt's default auto-fill
        completer = combo.completer() if hasattr(combo, "completer") else None
        if completer is not None:
            if hasattr(completer, "popup"):
                completer.popup().hide()
            # Clear completion prefix to prevent unwanted autocomplete behavior
            if hasattr(completer, "setCompletionPrefix"):
                completer.setCompletionPrefix("")

    @classmethod
    def _last_filter_token(cls, raw_text: str) -> str:
        if raw_text is None:
            return ""
        token = str(raw_text).rsplit(",", 1)[-1].strip()
        return token

    @classmethod
    def _merge_last_filter_token(cls, raw_text: str, replacement: str) -> str:
        source = str(raw_text or "")
        replacement_clean = str(replacement or "").strip()
        if not replacement_clean:
            return cls._normalized_filter_text(source)
        if "," not in source:
            return cls._normalized_filter_text(replacement_clean)
        prefix, _current = source.rsplit(",", 1)
        merged = f"{prefix}, {replacement_clean}"
        return cls._normalized_filter_text(merged)

    def _insert_combo_separator(self, combo_line_edit: Any) -> None:
        if not hasattr(combo_line_edit, "text") or not hasattr(combo_line_edit, "cursorPosition"):
            return
        text = combo_line_edit.text()
        cursor = combo_line_edit.cursorPosition()
        if text and cursor > 0 and text[cursor - 1] in {",", " ", ";"}:
            return
        updated = f"{text[:cursor]}, {text[cursor:]}"
        combo_line_edit.setText(updated)
        combo_line_edit.setCursorPosition(cursor + 2)

    def _normalize_combo_editor_value(self, combo: Any) -> None:
        self._set_combo_filter_text(combo, combo.currentText())

    def _on_combo_enter_pressed(self, combo: Any) -> None:
        self._normalize_combo_editor_value(combo)
        self._on_search_clicked()

    def _normalize_all_combo_filters(self) -> None:
        for combo in self._attr_combos.values():
            self._normalize_combo_editor_value(combo)

    def _open_lov_selector(self, column_name: str, label: str) -> None:
        if column_name not in self._lov_enabled_columns:
            return

        combo = self._attr_combos.get(column_name)
        if combo is None or QDialog is None or QListWidget is None:
            return

        candidates = self._combo_candidate_values(combo, column_name)
        if not candidates:
            QMessageBox.information(
                self,
                "Layer Filter",
                f"No available values for {label}.",
            )
            return

        current_selected = set(self._split_multi_value_text(combo.currentText()))

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Select values - {label}")
        dialog.resize(430, 480)

        root = QVBoxLayout(dialog)

        parent_col = self._filter_by_map.get(column_name, "")
        parent_info = QLabel()
        parent_info.setObjectName("FilterHintLabel")
        if parent_col:
            parent_combo = self._attr_combos.get(parent_col)
            parent_value = ""
            if parent_combo is not None:
                parent_value = self._resolve_single_parent_value(parent_col, parent_combo.currentText())
            parent_label = self._attr_labels.get(parent_col, parent_col)
            if parent_value:
                parent_info.setText(f"Filtered by {parent_label}: {parent_value}")
            else:
                parent_info.setText(f"Showing all values (no single parent selected for {parent_label}).")
        else:
            parent_info.setText("Showing all values.")
        root.addWidget(parent_info)

        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Search values...")
        search_edit.setClearButtonEnabled(True)
        root.addWidget(search_edit)

        values_list = QListWidget()
        selection_mode = getattr(QAbstractItemView, "ExtendedSelection", None)
        if selection_mode is None:
            mode_enum = getattr(QAbstractItemView, "SelectionMode", None)
            if mode_enum is not None:
                selection_mode = getattr(mode_enum, "ExtendedSelection", None)
        if selection_mode is not None:
            values_list.setSelectionMode(selection_mode)

        for value in candidates:
            item = QListWidgetItem(value)
            values_list.addItem(item)
            if value in current_selected:
                item.setSelected(True)

        root.addWidget(values_list, 1)

        helper = QLabel("Multi-select: Ctrl+click or Shift+click")
        helper.setObjectName("FilterHintLabel")
        root.addWidget(helper)

        ok_button = getattr(QDialogButtonBox, "Ok", None)
        cancel_button = getattr(QDialogButtonBox, "Cancel", None)
        if ok_button is None or cancel_button is None:
            standard_button_enum = getattr(QDialogButtonBox, "StandardButton", None)
            if standard_button_enum is not None:
                ok_button = getattr(standard_button_enum, "Ok", ok_button)
                cancel_button = getattr(standard_button_enum, "Cancel", cancel_button)

        if ok_button is not None and cancel_button is not None:
            buttons = QDialogButtonBox(ok_button | cancel_button)
        else:
            buttons = QDialogButtonBox()
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)

        def _apply_search_filter(search_text: str) -> None:
            needle = str(search_text or "").strip().lower()
            for index in range(values_list.count()):
                item = values_list.item(index)
                hay = item.text().lower()
                item.setHidden(bool(needle) and needle not in hay)

        search_edit.textChanged.connect(_apply_search_filter)

        accepted_value = getattr(QDialog, "Accepted", None)
        if accepted_value is None:
            dialog_code_enum = getattr(QDialog, "DialogCode", None)
            if dialog_code_enum is not None:
                accepted_value = getattr(dialog_code_enum, "Accepted", None)
        if accepted_value is None:
            accepted_value = 1

        if dialog.exec() != accepted_value:
            return

        selected_values = [
            item.text().strip()
            for item in values_list.selectedItems()
            if item is not None and item.text().strip()
        ]
        self._set_combo_filter_text(combo, ", ".join(selected_values))

    def _append_trailing_separator(self, combo: Any) -> None:
        editor = combo.lineEdit() if hasattr(combo, "lineEdit") else None
        if editor is None or not hasattr(editor, "text"):
            return
        text = str(editor.text() or "")
        if not text:
            return
        if text.endswith(", "):
            return
        if text.endswith(","):
            editor.setText(f"{text} ")
            if hasattr(editor, "setCursorPosition"):
                editor.setCursorPosition(len(editor.text()))
            return
        editor.setText(f"{text}, ")
        if hasattr(editor, "setCursorPosition"):
            editor.setCursorPosition(len(editor.text()))

    def _combo_candidate_values(self, combo: Any, column_name: str) -> list[str]:
        configured = self._candidate_values_for_column(column_name)
        if configured:
            return sorted({str(value).strip() for value in configured if str(value).strip()})

        values: list[str] = []
        for index in range(combo.count()):
            data = combo.itemData(index)
            text = str(data if data is not None else combo.itemText(index)).strip()
            if text:
                values.append(text)
        return sorted(set(values))

    def _candidate_values_for_column(self, column_name: str) -> list[str]:
        parent_col = self._filter_by_map.get(column_name, "")
        if parent_col:
            parent_combo = self._attr_combos.get(parent_col)
            if parent_combo is not None:
                selected_parent_val = self._resolve_single_parent_value(
                    parent_col,
                    parent_combo.currentText(),
                )
                if selected_parent_val:
                    per_parent = self._filtered_distinct_values.get(column_name, {})
                    return [
                        str(value).strip()
                        for value in per_parent.get(selected_parent_val, [])
                        if str(value).strip()
                    ]

        return [
            str(value).strip()
            for value in self._distinct_values.get(column_name, [])
            if str(value).strip()
        ]

    def _resolve_single_parent_value(self, parent_col: str, raw_value: str) -> str:
        values = self._split_multi_value_text(raw_value)
        if len(values) != 1:
            return ""
        value = values[0]
        distinct_values = {str(item) for item in self._distinct_values.get(parent_col, []) if item}
        return value if value in distinct_values else ""

    def _on_save_filters(self) -> None:
        self._on_search_clicked()

    def _update_fl_controls_enabled(self) -> None:
        if not self._show_flight_level or self._enabled_check is None:
            return
        enabled = bool(self._enabled_check.isChecked())
        if self._lower_spin is not None:
            self._lower_spin.setEnabled(enabled)
        if self._upper_spin is not None:
            self._upper_spin.setEnabled(enabled)
        for button, _, _ in self._preset_buttons:
            button.setEnabled(enabled)

    def _on_preset_clicked(self, lower: int, upper: int) -> None:
        if self._enabled_check is not None and not self._enabled_check.isChecked():
            self._enabled_check.setChecked(True)
        if self._lower_spin is not None:
            self._lower_spin.setValue(int(lower))
        if self._upper_spin is not None:
            self._upper_spin.setValue(int(upper))
        self._sync_preset_button_state(int(lower), int(upper))
        self._on_search_clicked()

    def _sync_preset_button_state(self, lower: int, upper: int) -> None:
        for button, preset_lower, preset_upper in self._preset_buttons:
            should_check = lower == preset_lower and upper == preset_upper
            button.blockSignals(True)
            button.setChecked(should_check)
            button.blockSignals(False)

    def _invalid_numeric_tokens(self, column_name: str, raw_value: str) -> list[str]:
        if not raw_value:
            return []
        tokens = [part.strip() for part in raw_value.split(",") if part.strip()]
        bad = [token for token in tokens if not self._NUMERIC_VALUE_RE.match(token)]
        if not bad:
            return []
        return [f"{column_name}: {', '.join(bad)}"]

    def _reload_records_from_layer(self) -> None:
        if self._layer is None:
            return

        col_names = [c.get("name", "") for c in self._columns if c.get("name", "")]
        layer_field_names = set(self._layer.fields().names()) if hasattr(self._layer, "fields") else set()

        records: list[dict[str, object]] = []
        try:
            for feat in self._layer.getFeatures():
                rec: dict[str, object] = {"__fid": int(feat.id()) if hasattr(feat, "id") else -1}
                for col_name in col_names:
                    rec[col_name] = feat[col_name] if col_name in layer_field_names else None
                records.append(rec)
        except Exception as exc:
            if self._logger is not None:
                self._logger.error(f"Unable to refresh records after filter apply: {exc}")
            return

        self._all_records = records

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
        if fid is None or fid < 0:
            return

        if item.checkState() == _ITEM_FLAGS["checked"]:
            self._checked_fids.add(fid)
        else:
            self._checked_fids.discard(fid)
        self._update_map_selection()

    def _on_row_selection_changed(self) -> None:
        self._update_map_selection()

    def _update_map_selection(self) -> None:
        if self._layer is None:
            return
        selected_fids = set(self._checked_fids)
        selected = self._table.selectedItems()
        if selected:
            row = selected[0].row()
            if 0 <= row < len(self._current_fids):
                fid = self._current_fids[row]
                if fid >= 0:
                    selected_fids.add(fid)
        try:
            selected_fid_list = sorted(selected_fids)
            self._layer.selectByIds(selected_fid_list)
            self._update_map_highlights(selected_fid_list)
        except Exception as exc:
            if self._logger is not None:
                self._logger.warning(f"Unable to select feature on map: {exc}")

    def _update_map_highlights(self, selected_fids: list[int]) -> None:
        self._clear_map_highlights()
        if QgsRubberBand is None or QColor is None or self._map_canvas is None:
            return
        if not hasattr(self._layer, "getFeature") or not hasattr(self._layer, "geometryType"):
            return

        for fid in selected_fids:
            try:
                feature = self._layer.getFeature(fid)
                if hasattr(feature, "isValid") and not feature.isValid():
                    continue
                rubber_band = QgsRubberBand(self._map_canvas, self._layer.geometryType())
                rubber_band.setToGeometry(feature.geometry(), self._layer)
                rubber_band.setStrokeColor(QColor("#FFD400"))
                rubber_band.setFillColor(QColor(255, 212, 0, 190))
                rubber_band.setWidth(2)
                rubber_band.show()
                self._map_highlights.append(rubber_band)
            except Exception as exc:
                if self._logger is not None:
                    self._logger.warning(f"Unable to highlight feature on map: {exc}")

    def _clear_map_highlights(self) -> None:
        for highlight in getattr(self, "_map_highlights", []):
            highlight.hide()
            highlight.reset()
        self._map_highlights = []

    def closeEvent(self, event) -> None:
        self._clear_map_highlights()
        super().closeEvent(event)

    def _on_export_selected_records(self) -> None:
        if self._layer is None:
            QMessageBox.warning(self, "Export", "No active layer is available for export.")
            return

        export_fids = self._export_record_fids()
        if not export_fids:
            QMessageBox.information(
                self,
                "Export",
                "No records match the current filter criteria.",
            )
            return

        export_format = str(
            self._export_format_combo.currentData() if self._export_format_combo is not None else ""
        ).strip().lower()
        if export_format not in {
            self._EXPORT_FORMAT_CSV,
            self._EXPORT_FORMAT_XLSX,
            self._EXPORT_FORMAT_GEOJSON,
            self._EXPORT_FORMAT_KML,
        }:
            QMessageBox.warning(self, "Export", "Unsupported export format selected.")
            return

        file_path = self._choose_export_path(export_format)
        if file_path is None:
            return

        try:
            if export_format in {self._EXPORT_FORMAT_GEOJSON, self._EXPORT_FORMAT_KML}:
                self._write_vector_export(file_path, export_format, export_fids)
            else:
                self._write_table_export(file_path, export_format, export_fids)
            QMessageBox.information(
                self,
                "Export",
                f"Exported {len(export_fids)} records to:\n{file_path}",
            )
        except Exception as exc:
            if self._logger is not None:
                self._logger.error(f"{export_format.upper()} export failed: {exc}")
            QMessageBox.warning(self, "Export", f"{export_format.upper()} export failed:\n{exc}")

    def _export_record_fids(self) -> list[int]:
        return sorted(
            int(record.get("__fid", -1))
            for record in self._all_records
            if int(record.get("__fid", -1)) >= 0
        )

    @classmethod
    def _export_format_spec(cls, export_format: str) -> tuple[str, str, str]:
        normalized = str(export_format or "").strip().lower()
        if normalized == cls._EXPORT_FORMAT_CSV:
            return "csv", "CSV Files (*.csv)", "CSV"
        if normalized == cls._EXPORT_FORMAT_XLSX:
            return "xlsx", "Excel Files (*.xlsx)", "XLSX"
        if normalized == cls._EXPORT_FORMAT_KML:
            return "kml", "KML Files (*.kml)", "KML"
        return "geojson", "GeoJSON Files (*.geojson)", "GeoJSON"

    @classmethod
    def _ensure_export_extension(cls, file_path: Path, extension: str) -> Path:
        ext = f".{str(extension or '').strip().lower().lstrip('.')}"
        if file_path.suffix.lower() == ext:
            return file_path
        return file_path.with_suffix(ext)

    def _choose_export_path(self, export_format: str) -> Path | None:
        extension, file_filter, _driver_name = self._export_format_spec(export_format)
        suggested_name = self._build_export_file_basename()
        suggested = Path.home() / f"{suggested_name}.{extension}"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Selected Records",
            str(suggested),
            file_filter,
        )
        if not file_path:
            return None
        return self._ensure_export_extension(Path(file_path), extension)

    def _build_export_file_basename(self) -> str:
        layer_name = self._safe_filename_token(self._layer_display_name())
        criteria_tokens = self._active_criteria_tokens()

        if criteria_tokens:
            base_name = "_".join([layer_name, *criteria_tokens])
        else:
            base_name = f"{layer_name}_all"

        if len(base_name) <= self._MAX_EXPORT_FILENAME_LENGTH:
            return base_name

        return base_name[: self._MAX_EXPORT_FILENAME_LENGTH].rstrip("._-") or "export"

    def _layer_display_name(self) -> str:
        if self._layer is not None and hasattr(self._layer, "name"):
            try:
                value = str(self._layer.name() or "").strip()
                if value:
                    return value
            except Exception:
                pass
        return "layer"

    def _active_criteria_tokens(self) -> list[str]:
        criteria: list[str] = []
        layer_filter = self._current_filter()

        for attr in layer_filter.attributes:
            value_token = self._safe_filename_token(attr.value)
            if value_token:
                criteria.append(value_token)

        fl = layer_filter.flight_level
        if getattr(fl, "enabled", False):
            criteria.append(f"fl-{int(fl.lower)}-{int(fl.upper)}")

        return criteria

    @classmethod
    def _safe_filename_token(cls, raw_value: str) -> str:
        normalized = cls._FILENAME_SAFE_RE.sub("_", str(raw_value or "").strip())
        normalized = re.sub(r"_+", "_", normalized).strip("._-")
        return normalized or "value"

    def _write_vector_export(self, file_path: Path, export_format: str, selected_fids: list[int]) -> None:
        if QgsVectorFileWriter is None:
            raise RuntimeError("QGIS vector writer is not available in this runtime.")
        if self._layer is None:
            raise RuntimeError("No active layer is available for export.")

        extension, _file_filter, driver_name = self._export_format_spec(export_format)
        target_path = self._ensure_export_extension(file_path, extension)

        if not hasattr(QgsVectorFileWriter, "SaveVectorOptions"):
            raise RuntimeError("QGIS runtime is too old for selected-record export.")

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = driver_name
        options.fileEncoding = "UTF-8"
        options.onlySelectedFeatures = True
        options.layerName = str(getattr(self._layer, "name", lambda: "selected_records")())

        previous_selected_ids: list[int] = []
        if hasattr(self._layer, "selectedFeatureIds"):
            try:
                previous_selected_ids = [int(fid) for fid in self._layer.selectedFeatureIds()]
            except Exception:
                previous_selected_ids = []

        try:
            self._layer.selectByIds(selected_fids)

            transform_context = None
            if hasattr(self._layer, "transformContext"):
                try:
                    transform_context = self._layer.transformContext()
                except Exception:
                    transform_context = None
            if transform_context is None and QgsCoordinateTransformContext is not None:
                transform_context = QgsCoordinateTransformContext()

            writer_fn = getattr(QgsVectorFileWriter, "writeAsVectorFormatV3", None)
            if callable(writer_fn):
                result = writer_fn(self._layer, str(target_path), transform_context, options)
                error_code = result[0] if isinstance(result, tuple) else result
                if error_code != QgsVectorFileWriter.NoError:
                    detail = ""
                    if isinstance(result, tuple) and len(result) > 1:
                        detail = str(result[1])
                    raise RuntimeError(detail or "QGIS writer returned an unknown error.")
                return

            raise RuntimeError("QGIS runtime does not support vector export API V3.")
        finally:
            try:
                self._layer.selectByIds(previous_selected_ids)
            except Exception:
                pass

    def _write_table_export(self, file_path: Path, export_format: str, selected_fids: list[int]) -> None:
        extension, _file_filter, _label = self._export_format_spec(export_format)
        target_path = self._ensure_export_extension(file_path, extension)
        selected_records = self._records_for_fids(selected_fids)

        if export_format == self._EXPORT_FORMAT_CSV:
            self._write_csv(target_path, selected_records)
            return

        if export_format == self._EXPORT_FORMAT_XLSX:
            self._write_xlsx(target_path, selected_records)
            return

        raise RuntimeError("Unsupported table export format.")

    def _records_for_fids(self, selected_fids: list[int]) -> list[dict[str, object]]:
        selected_set = set(selected_fids)
        return [
            record
            for record in self._all_records
            if int(record.get("__fid", -1)) in selected_set
        ]

    def _write_csv(self, file_path: Path, records: list[dict[str, object]]) -> None:
        headers = [col.get("label", col["name"]) for col in self._columns]
        keys = [col["name"] for col in self._columns]
        with file_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for record in records:
                writer.writerow([record.get(key, "") for key in keys])

    def _write_xlsx(self, file_path: Path, records: list[dict[str, object]]) -> None:
        try:
            from openpyxl import Workbook
        except ImportError as exc:
            raise RuntimeError(
                "openpyxl is not installed in the QGIS Python environment."
            ) from exc

        wb = Workbook()
        ws = wb.active
        ws.title = "Selected Records"

        headers = [col.get("label", col["name"]) for col in self._columns]
        keys = [col["name"] for col in self._columns]
        ws.append(headers)
        for record in records:
            ws.append([record.get(key, "") for key in keys])

        wb.save(str(file_path))


# Backward compatibility alias
LayerCustomViewDock = LayerCustomViewWindow
