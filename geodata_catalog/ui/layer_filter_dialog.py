from __future__ import annotations

import re
from typing import Any

from geodata_catalog.services.layer_filter_service import (
    AttributeSearchFilter,
    FlightLevelFilter,
    LayerFilter,
    LayerFilterService,
)

try:
    from qgis.PyQt.QtCore import QRect, QSize, Qt, pyqtSignal
    from qgis.PyQt import QtGui
    from qgis.PyQt.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLayout,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )
    QBrush = QtGui.QBrush
    QColor = QtGui.QColor
    QPainter = QtGui.QPainter
    QPen = QtGui.QPen
except ImportError:  # pragma: no cover
    QRect = None
    QSize = None
    Qt = None
    pyqtSignal = None
    QBrush = None
    QColor = None
    QPainter = None
    QPen = None
    QCheckBox = None
    QComboBox = None
    QDialog = object
    QFormLayout = None
    QGroupBox = None
    QHBoxLayout = None
    QLabel = None
    QLayout = None
    QLineEdit = None
    QMessageBox = None
    QPushButton = None
    QSpinBox = None
    QVBoxLayout = None
    QWidget = None


if QDialog is not object:
    _MOUSE_BUTTON_ENUM = getattr(Qt, "MouseButton", None)
    _MOUSE_LEFT_FALLBACK = getattr(_MOUSE_BUTTON_ENUM, "LeftButton", None)
    MOUSE_LEFT = getattr(Qt, "LeftButton", _MOUSE_LEFT_FALLBACK)
else:  # pragma: no cover
    MOUSE_LEFT = None

# Sentinel for when pyqtSignal is unavailable (non-QGIS test environments).
_Signal = pyqtSignal if pyqtSignal is not None else object


if QWidget is not None:
    _ANTIALIAS_HINT = getattr(QPainter, "Antialiasing", None)
    if _ANTIALIAS_HINT is None and hasattr(QPainter, "RenderHint"):
        _ANTIALIAS_HINT = getattr(QPainter.RenderHint, "Antialiasing", None)
    _NO_PEN = getattr(Qt, "NoPen", None)
    if _NO_PEN is None and hasattr(Qt, "PenStyle"):
        _NO_PEN = getattr(Qt.PenStyle, "NoPen", None)
    _FIXED_SIZE_CONSTRAINT = getattr(QLayout, "SetFixedSize", None)
    if _FIXED_SIZE_CONSTRAINT is None and hasattr(QLayout, "SizeConstraint"):
        _FIXED_SIZE_CONSTRAINT = getattr(QLayout.SizeConstraint, "SetFixedSize", None)

    class FlightLevelRangeSlider(QWidget):
        """Simple dual-handle slider for selecting a FL interval."""

        rangeChanged = _Signal(int, int)
        rangeReleased = _Signal(int, int)

        def __init__(self, minimum: int = 0, maximum: int = 999, parent=None) -> None:
            super().__init__(parent)
            self._minimum = int(minimum)
            self._maximum = max(int(maximum), self._minimum)
            self._lower = self._minimum
            self._upper = self._maximum
            self._active_handle: str | None = None
            self._handle_radius = 8
            self._track_height = 4
            self.setMinimumHeight(30)

        def sizeHint(self):
            return QSize(320, 30)

        def setRange(self, minimum: int, maximum: int) -> None:
            self._minimum = int(minimum)
            self._maximum = max(int(maximum), self._minimum)
            self.setValues(self._lower, self._upper)

        def setValues(self, lower: int, upper: int) -> None:
            lower_val = max(self._minimum, min(int(lower), self._maximum))
            upper_val = max(self._minimum, min(int(upper), self._maximum))
            if lower_val > upper_val:
                lower_val, upper_val = upper_val, lower_val
            changed = lower_val != self._lower or upper_val != self._upper
            self._lower = lower_val
            self._upper = upper_val
            if changed:
                self.rangeChanged.emit(self._lower, self._upper)
            self.update()

        def setLowerValue(self, lower: int) -> None:
            self.setValues(lower, self._upper)

        def setUpperValue(self, upper: int) -> None:
            self.setValues(self._lower, upper)

        def lowerValue(self) -> int:
            return int(self._lower)

        def upperValue(self) -> int:
            return int(self._upper)

        def paintEvent(self, _event) -> None:
            painter = QPainter(self)
            if _ANTIALIAS_HINT is not None:
                painter.setRenderHint(_ANTIALIAS_HINT, True)

            left = self._handle_radius
            right = max(left + 1, self.width() - self._handle_radius)
            y = self.height() // 2

            track_rect = QRect(
                left,
                y - self._track_height // 2,
                right - left,
                self._track_height,
            )
            if _NO_PEN is not None:
                painter.setPen(_NO_PEN)
            painter.setBrush(QBrush(QColor("#d8dde6")))
            painter.drawRoundedRect(track_rect, 2, 2)

            lower_x = self._value_to_pos(self._lower)
            upper_x = self._value_to_pos(self._upper)
            selected_rect = QRect(
                lower_x,
                y - self._track_height // 2,
                max(1, upper_x - lower_x),
                self._track_height,
            )
            painter.setBrush(QBrush(QColor("#3572a5")))
            painter.drawRoundedRect(selected_rect, 2, 2)

            painter.setPen(QPen(QColor("#2f3b4a"), 1))
            painter.setBrush(QBrush(QColor("white")))
            painter.drawEllipse(lower_x - self._handle_radius, y - self._handle_radius, self._handle_radius * 2, self._handle_radius * 2)
            painter.drawEllipse(upper_x - self._handle_radius, y - self._handle_radius, self._handle_radius * 2, self._handle_radius * 2)

        def mousePressEvent(self, event) -> None:
            if event.button() != MOUSE_LEFT:
                return
            lower_x = self._value_to_pos(self._lower)
            upper_x = self._value_to_pos(self._upper)
            x = event.position().x() if hasattr(event, "position") else event.x()
            self._active_handle = "lower" if abs(x - lower_x) <= abs(x - upper_x) else "upper"
            self._set_active_from_pos(x)

        def mouseMoveEvent(self, event) -> None:
            if self._active_handle is None:
                return
            x = event.position().x() if hasattr(event, "position") else event.x()
            self._set_active_from_pos(x)

        def mouseReleaseEvent(self, _event) -> None:
            had_active_handle = self._active_handle is not None
            self._active_handle = None
            if had_active_handle:
                self.rangeReleased.emit(self._lower, self._upper)

        def _set_active_from_pos(self, x_pos: float) -> None:
            value = self._pos_to_value(x_pos)
            if self._active_handle == "lower":
                self.setLowerValue(min(value, self._upper))
            else:
                self.setUpperValue(max(value, self._lower))

        def _value_to_pos(self, value: int) -> int:
            span = max(1, self._maximum - self._minimum)
            ratio = (value - self._minimum) / span
            left = self._handle_radius
            right = max(left + 1, self.width() - self._handle_radius)
            return int(round(left + ratio * (right - left)))

        def _pos_to_value(self, x_pos: float) -> int:
            left = self._handle_radius
            right = max(left + 1, self.width() - self._handle_radius)
            x = max(left, min(int(round(x_pos)), right))
            ratio = (x - left) / max(1, right - left)
            return int(round(self._minimum + ratio * (self._maximum - self._minimum)))
else:  # pragma: no cover
    class FlightLevelRangeSlider:
        pass


class LayerFilterDialog(QDialog):
    """Dialog for applying flight level and attribute filters on a loaded layer."""

    filter_applied = _Signal(object)  # emits LayerFilter

    MODE_BETWEEN = LayerFilterService.MODE_BETWEEN
    MODE_NONE = LayerFilterService.MODE_NONE

    _NUMERIC_VALUE_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

    def __init__(
        self,
        parent=None,
        layer_name: str = "",
        initial_filter: LayerFilter | None = None,
        searchable_columns: list[dict[str, str | bool]] | None = None,
        distinct_values: dict[str, list[str]] | None = None,
        filtered_distinct_values: dict[str, dict[str, list[str]]] | None = None,
        show_flight_level: bool = True,
        flight_level_presets: list[dict[str, int | str]] | None = None,
    ) -> None:
        if QDialog is object:  # pragma: no cover
            raise RuntimeError("QGIS runtime is not available.")
        super().__init__(parent)
        self.setWindowTitle("Layer Filter")
        self.setModal(False)
        self._layer_name = layer_name
        self._show_flight_level = bool(show_flight_level)
        self._searchable_columns: list[dict[str, str | bool]] = searchable_columns or []
        self._distinct_values: dict[str, list[str]] = distinct_values or {}
        self._filtered_distinct_values: dict[str, dict[str, list[str]]] = filtered_distinct_values or {}
        self._attr_edits: dict[str, Any] = {}
        self._attr_combos: dict[str, Any] = {}
        self._attr_distinct_edits: dict[str, Any] = {}
        self._attr_types: dict[str, str] = {}
        self._filter_by_map: dict[str, str] = {}
        self._flight_level_presets = self._normalize_flight_level_presets(flight_level_presets)
        self._preset_buttons: list[tuple[Any, int, int]] = []

        self._enabled_check = None
        self._fl_range_slider = None
        self._lower_spin = None
        self._upper_spin = None
        self._fl_lower_field_name = "fl_lower"
        self._fl_upper_field_name = "fl_upper"

        self._build_ui()
        if initial_filter is not None:
            self._populate(initial_filter)
        self._apply_dynamic_size()

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

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        if _FIXED_SIZE_CONSTRAINT is not None:
            layout.setSizeConstraint(_FIXED_SIZE_CONSTRAINT)

        title = QLabel(f"Filter for layer: {self._layer_name or 'the selected layer'}")
        layout.addWidget(title)

        if self._searchable_columns:
            layout.addWidget(self._build_attribute_group())

        if self._show_flight_level:
            layout.addWidget(self._build_flight_level_group())

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_btn = QPushButton("Close")
        apply_btn = QPushButton("Apply")
        close_btn.clicked.connect(self.reject)
        apply_btn.clicked.connect(self._on_apply)
        button_row.addWidget(close_btn)
        button_row.addWidget(apply_btn)
        layout.addLayout(button_row)

        if self._show_flight_level:
            self._update_fl_controls_enabled()

    def _apply_dynamic_size(self) -> None:
        """Resize the dialog to fit only the controls that are currently visible."""
        self.setMinimumWidth(560)
        self.adjustSize()

    def _build_attribute_group(self):
        for col_def in self._searchable_columns:
            col_name = col_def.get("name", "")
            filter_by = col_def.get("filter_by", "")
            if col_name and filter_by:
                self._filter_by_map[col_name] = str(filter_by)

        attr_group = QGroupBox("Attribute Search")
        attr_form = QFormLayout(attr_group)

        for col_def in self._searchable_columns:
            col_name = col_def.get("name", "")
            label = col_def.get("label", col_name)
            data_type = (col_def.get("type", "varchar") or "varchar").strip().lower()
            use_distinct = bool(col_def.get("use_distinct", False))
            if not col_name:
                continue

            if use_distinct:
                combo = QComboBox()
                combo.addItem("(no filter)", "")
                distinct_vals = self._distinct_values.get(col_name, [])
                for val in sorted(set(v for v in distinct_vals if v)):
                    combo.addItem(str(val), str(val))
                attr_form.addRow(f"{label} - select", combo)
                self._attr_combos[col_name] = combo

                extra_edit = QLineEdit()
                extra_edit.setPlaceholderText("Or type values manually (comma-separated)")
                extra_edit.setClearButtonEnabled(True)
                attr_form.addRow(f"{label} - custom", extra_edit)
                self._attr_distinct_edits[col_name] = extra_edit
            else:
                edit = QLineEdit()
                edit.setPlaceholderText(f"Filter on {label} (comma-separated values)")
                edit.setClearButtonEnabled(True)
                attr_form.addRow(label, edit)
                self._attr_edits[col_name] = edit

            self._attr_types[col_name] = data_type

        parent_cols_with_children: set[str] = set(self._filter_by_map.values())
        for parent_col in parent_cols_with_children:
            if parent_col in self._attr_combos:
                parent_combo = self._attr_combos[parent_col]
                parent_combo.currentIndexChanged.connect(
                    lambda _, pc=parent_col: self._on_parent_filter_changed(pc)
                )

        return attr_group

    def _build_flight_level_group(self):
        fl_group = QGroupBox("Flight Level Filter")
        fl_form = QFormLayout(fl_group)

        self._enabled_check = QCheckBox("Enable flight level filter")
        self._enabled_check.setChecked(True)
        self._enabled_check.toggled.connect(lambda _checked: self._update_fl_controls_enabled())
        fl_form.addRow(self._enabled_check)

        if self._flight_level_presets:
            preset_row = QHBoxLayout()
            for preset in self._flight_level_presets:
                lower = int(preset["lower"])
                upper = int(preset["upper"])
                button = QPushButton(str(preset["name"]))
                button.setCheckable(True)
                button.setFlat(True)
                button.setToolTip(f"Set FL range to FL{lower} - FL{upper}")
                button.clicked.connect(
                    lambda _checked, lo=lower, hi=upper: self._on_preset_clicked(lo, hi)
                )
                preset_row.addWidget(button)
                self._preset_buttons.append((button, lower, upper))
            preset_row.addStretch(1)
            fl_form.addRow("Quick presets", preset_row)

        self._fl_range_slider = FlightLevelRangeSlider(0, 999)
        self._fl_range_slider.setValues(0, 600)
        self._fl_range_slider.rangeChanged.connect(self._on_fl_range_changed)
        self._fl_range_slider.rangeReleased.connect(self._on_fl_slider_released)
        fl_form.addRow("FL range", self._fl_range_slider)

        self._lower_spin = QSpinBox()
        self._lower_spin.setRange(0, 999)
        self._lower_spin.setValue(0)
        self._lower_spin.setPrefix("FL")
        self._lower_spin.valueChanged.connect(self._on_lower_spin_changed)

        self._upper_spin = QSpinBox()
        self._upper_spin.setRange(0, 999)
        self._upper_spin.setValue(600)
        self._upper_spin.setPrefix("FL")
        self._upper_spin.valueChanged.connect(self._on_upper_spin_changed)

        spin_row = QHBoxLayout()
        spin_row.addWidget(self._lower_spin)
        spin_row.addWidget(QLabel("to"))
        spin_row.addWidget(self._upper_spin)
        fl_form.addRow("Bounds", spin_row)

        return fl_group

    # ------------------------------------------------------------------ #
    # Signal handlers                                                     #
    # ------------------------------------------------------------------ #

    def _on_fl_range_changed(self, lower: int, upper: int) -> None:
        if self._lower_spin is not None:
            self._lower_spin.blockSignals(True)
            self._lower_spin.setValue(int(lower))
            self._lower_spin.blockSignals(False)
        if self._upper_spin is not None:
            self._upper_spin.blockSignals(True)
            self._upper_spin.setValue(int(upper))
            self._upper_spin.blockSignals(False)
        self._sync_preset_button_state(int(lower), int(upper))

    def _sync_preset_button_state(self, lower: int, upper: int) -> None:
        for button, preset_lower, preset_upper in self._preset_buttons:
            should_check = lower == preset_lower and upper == preset_upper
            button.blockSignals(True)
            button.setChecked(should_check)
            button.blockSignals(False)

    def _on_preset_clicked(self, lower: int, upper: int) -> None:
        if self._enabled_check is not None and not self._enabled_check.isChecked():
            self._enabled_check.setChecked(True)
        if self._fl_range_slider is not None:
            self._fl_range_slider.setValues(lower, upper)
        else:
            if self._lower_spin is not None:
                self._lower_spin.setValue(lower)
            if self._upper_spin is not None:
                self._upper_spin.setValue(upper)
        self._on_apply()

    def _on_lower_spin_changed(self, lower: int) -> None:
        if self._upper_spin is not None and lower > self._upper_spin.value():
            self._upper_spin.setValue(lower)
        if self._fl_range_slider is not None:
            self._fl_range_slider.setLowerValue(int(lower))

    def _on_upper_spin_changed(self, upper: int) -> None:
        if self._lower_spin is not None and upper < self._lower_spin.value():
            self._lower_spin.setValue(upper)
        if self._fl_range_slider is not None:
            self._fl_range_slider.setUpperValue(int(upper))

    def _on_fl_slider_released(self, _lower: int, _upper: int) -> None:
        """Apply current filters as soon as the user releases the FL slider handle."""
        self._on_apply()

    def _update_fl_controls_enabled(self) -> None:
        if not self._show_flight_level or self._enabled_check is None:
            return
        enabled = bool(self._enabled_check.isChecked())

        if self._fl_range_slider is not None:
            self._fl_range_slider.setEnabled(enabled)
        if self._lower_spin is not None:
            self._lower_spin.setEnabled(enabled)
        if self._upper_spin is not None:
            self._upper_spin.setEnabled(enabled)
        for button, _, _ in self._preset_buttons:
            button.setEnabled(enabled)

    def _on_parent_filter_changed(self, parent_col: str) -> None:
        """Repopulate child combo boxes when a parent dropdown selection changes."""
        parent_combo = self._attr_combos.get(parent_col)
        if parent_combo is None:
            return
        selected_parent_val: str = parent_combo.currentData() or ""

        for child_col, mapped_parent in self._filter_by_map.items():
            if mapped_parent != parent_col:
                continue
            child_combo = self._attr_combos.get(child_col)
            if child_combo is None:
                continue

            current_child_val: str = child_combo.currentData() or ""

            child_combo.blockSignals(True)
            child_combo.clear()
            child_combo.addItem("(no filter)", "")

            if selected_parent_val:
                per_parent = self._filtered_distinct_values.get(child_col, {})
                candidate_vals: list[str] = per_parent.get(selected_parent_val, [])
            else:
                candidate_vals = self._distinct_values.get(child_col, [])

            for val in sorted(set(v for v in candidate_vals if v)):
                child_combo.addItem(str(val), str(val))

            idx = child_combo.findData(current_child_val)
            child_combo.setCurrentIndex(idx if idx >= 0 else 0)
            child_combo.blockSignals(False)

    def _on_apply(self) -> None:
        """Validate inputs and emit filter_applied without closing the dialog."""
        invalid_inputs: list[str] = []

        for col_name, edit in self._attr_edits.items():
            data_type = self._attr_types.get(col_name, "varchar")
            if data_type != "numeric":
                continue
            raw_value = edit.text().strip()
            invalid_inputs.extend(self._invalid_numeric_tokens(col_name, raw_value))

        for col_name, edit in self._attr_distinct_edits.items():
            data_type = self._attr_types.get(col_name, "varchar")
            if data_type != "numeric":
                continue
            raw_value = edit.text().strip()
            invalid_inputs.extend(self._invalid_numeric_tokens(col_name, raw_value))

        if invalid_inputs:
            QMessageBox.warning(
                self,
                "Layer Filter",
                "Invalid numeric values found:\n- " + "\n- ".join(invalid_inputs),
            )
            return

        self.filter_applied.emit(self.get_filter())

    def _invalid_numeric_tokens(self, column_name: str, raw_value: str) -> list[str]:
        if not raw_value:
            return []
        tokens = [part.strip() for part in raw_value.split(",") if part.strip()]
        bad = [token for token in tokens if not self._NUMERIC_VALUE_RE.match(token)]
        if not bad:
            return []
        return [f"{column_name}: {', '.join(bad)}"]

    # ------------------------------------------------------------------ #
    # Public helpers                                                      #
    # ------------------------------------------------------------------ #

    def get_filter(self) -> LayerFilter:
        """Return the current dialog state as a LayerFilter."""
        if self._show_flight_level and self._enabled_check is not None:
            lower = int(self._lower_spin.value()) if self._lower_spin is not None else 0
            upper = int(self._upper_spin.value()) if self._upper_spin is not None else 600
            if lower > upper:
                lower, upper = upper, lower
            fl_enabled = bool(self._enabled_check.isChecked())
            fl_mode = self.MODE_BETWEEN if fl_enabled else self.MODE_NONE
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
                mode=self.MODE_NONE,
                lower=0,
                upper=600,
                enabled=False,
                lower_field="fl_lower",
                upper_field="fl_upper",
            )

        attrs = []
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
            combo_value = combo.currentData() or ""
            extra_edit = self._attr_distinct_edits.get(col_name)
            extra_value = extra_edit.text().strip() if extra_edit else ""
            parts: list[str] = []
            if combo_value:
                parts.append(combo_value)
            if extra_value:
                parts.extend(v.strip() for v in extra_value.split(",") if v.strip())
            if parts:
                merged = ", ".join(parts)
                attrs.append(
                    AttributeSearchFilter(
                        column=col_name,
                        value=merged,
                        label=col_name,
                        data_type=self._attr_types.get(col_name, "varchar"),
                    )
                )
        return LayerFilter(flight_level=fl_filter, attributes=attrs)

    def _populate(self, layer_filter: LayerFilter) -> None:
        """Pre-populate all dialog controls from an existing LayerFilter."""
        fl = layer_filter.flight_level

        if self._show_flight_level and self._enabled_check is not None:
            self._enabled_check.setChecked(bool(fl.enabled))

            if self._lower_spin is not None:
                self._lower_spin.setValue(int(fl.lower))
            if self._upper_spin is not None:
                self._upper_spin.setValue(int(fl.upper))
            if self._fl_range_slider is not None:
                self._fl_range_slider.setValues(int(fl.lower), int(fl.upper))
            self._fl_lower_field_name = fl.lower_field or "fl_lower"
            self._fl_upper_field_name = fl.upper_field or "fl_upper"

            self._update_fl_controls_enabled()

        for attr in layer_filter.attributes:
            if attr.column in self._attr_edits:
                self._attr_edits[attr.column].setText(attr.value)
            elif attr.column in self._attr_combos:
                stored_value = attr.value
                distinct_vals = [
                    self._attr_combos[attr.column].itemData(i)
                    for i in range(self._attr_combos[attr.column].count())
                ]
                if stored_value in distinct_vals:
                    idx = self._attr_combos[attr.column].findData(stored_value)
                    if idx >= 0:
                        self._attr_combos[attr.column].setCurrentIndex(idx)
                else:
                    extra_edit = self._attr_distinct_edits.get(attr.column)
                    if extra_edit is not None:
                        extra_edit.setText(stored_value)
