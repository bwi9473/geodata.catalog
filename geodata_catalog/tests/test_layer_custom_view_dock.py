from typing import Any

from geodata_catalog.services.layer_filter_service import (
    AttributeSearchFilter,
    FlightLevelFilter,
    LayerFilter,
    LayerFilterService,
)
from geodata_catalog.ui.layer_custom_view_dock import LayerCustomViewWindow


def test_normalized_filter_text_trims_and_joins_values():
    assert (
        LayerCustomViewWindow._normalized_filter_text(" DEC365,DEC366 ,, DEC367 ")
        == "DEC365, DEC366, DEC367"
    )


def test_version_number_display_omits_decimal_for_integer_values():
    assert LayerCustomViewWindow._format_record_value("VERSION_NR", 2235.0) == "2235"
    assert LayerCustomViewWindow._format_record_value("version_nr", "2235.0") == "2235"


class _FilterToggleButton:
    def __init__(self):
        self.checked = True
        self.checkable = True
        self.enabled = True
        self.text = ""
        self.tooltip = ""

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setChecked(self, checked):
        self.checked = checked

    def setCheckable(self, checkable):
        self.checkable = checkable

    def setText(self, text):
        self.text = text

    def setToolTip(self, tooltip):
        self.tooltip = tooltip


def _filter_toggle_window(show_flight_level, enabled):
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    window._show_flight_level = show_flight_level
    window._enabled_check = type("_Check", (), {"isChecked": lambda self: enabled})()
    window._toggle_fl_btn = _FilterToggleButton()
    window._toggle_attr_btn = _FilterToggleButton()
    window._filter_panel = None
    window._has_active_attribute_filters = lambda: False
    return window


def test_flight_level_toggle_is_disabled_for_layers_without_flight_levels():
    window = _filter_toggle_window(False, True)

    window._refresh_filter_toggle_buttons()

    button = window._toggle_fl_btn
    assert button.enabled is False
    assert button.checked is False
    assert button.checkable is False
    assert button.text == "Flight Levels (not available)"
    assert "configured without flight levels" in button.tooltip
    assert window._toggle_attr_btn.enabled is True
    window._refresh_filter_toggle_buttons()
    assert button.enabled is False


def test_flight_level_toggle_stays_available_when_filter_is_off():
    window = _filter_toggle_window(True, False)

    window._refresh_filter_toggle_buttons()

    button = window._toggle_fl_btn
    assert button.enabled is True
    assert button.checkable is True
    assert button.text == "Flight Levels (off)"
    assert "Show or hide" in button.tooltip


def test_flight_level_toggle_shows_active_filter():
    window = _filter_toggle_window(True, True)

    window._refresh_filter_toggle_buttons()

    assert window._toggle_fl_btn.enabled is True
    assert window._toggle_fl_btn.text == "Flight Levels (active)"


def test_resolve_single_parent_value_accepts_one_known_value():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    window._distinct_values = {"sector_combination": ["DEC365", "DEC366"]}

    assert (
        window._resolve_single_parent_value("sector_combination", " DEC365 ")
        == "DEC365"
    )


def test_resolve_single_parent_value_rejects_multiple_or_unknown_values():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    window._distinct_values = {"sector_combination": ["DEC365", "DEC366"]}

    assert window._resolve_single_parent_value("sector_combination", "DEC365, DEC366") == ""
    assert window._resolve_single_parent_value("sector_combination", "DEC999") == ""


def test_last_filter_token_reads_only_last_segment():
    assert LayerCustomViewWindow._last_filter_token("DEC365, DEL") == "DEL"
    assert LayerCustomViewWindow._last_filter_token("DEC365, ") == ""


def test_merge_last_filter_token_replaces_last_segment_and_normalizes():
    merged = LayerCustomViewWindow._merge_last_filter_token("DEC365, DEL", "DELTA_H")
    assert merged == "DEC365, DELTA_H"


def test_merge_last_filter_token_without_prefix_returns_single_value():
    merged = LayerCustomViewWindow._merge_last_filter_token("DEL", "DELTA_H")
    assert merged == "DELTA_H"


class _DummyLineEdit:
    def __init__(self, text: str):
        self._text = text
        self.cursor = 0

    def text(self) -> str:
        return self._text

    def setText(self, value: str) -> None:
        self._text = value

    def setCursorPosition(self, position: int) -> None:
        self.cursor = position


class _DummyCombo:
    def __init__(self, text: str):
        self._editor = _DummyLineEdit(text)

    def lineEdit(self):
        return self._editor

    def currentText(self) -> str:
        return self._editor.text()


class _FieldBrowserWidget(_DummyLineEdit):
    def __init__(self, text="", checked=False):
        super().__init__(text)
        self.checked = checked
        self.visible = True

    def isChecked(self):
        return self.checked

    def setChecked(self, checked):
        self.checked = checked

    def clear(self):
        self.setText("")

    def setVisible(self, visible):
        self.visible = visible


class _FieldGrid:
    def __init__(self):
        self.items = []
        self.stretches = {}

    def count(self):
        return len(self.items)

    def takeAt(self, index):
        return self.items.pop(index)

    def setColumnStretch(self, column, stretch):
        self.stretches[column] = stretch

    def addWidget(self, widget, row, column):
        self.items.append((widget, row, column))


def _field_browser_window():
    from geodata_catalog.ui.layer_custom_view_dock import _UNCHECKED_STATE

    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    window._attr_edits = {
        "AERODROMEID": _FieldBrowserWidget("EHAM"),
        "AOI_SITUATION": _FieldBrowserWidget(),
    }
    window._attr_combos = {"TRAFFIC_CLASS": _DummyCombo(" CIVIL, MILITARY ")}
    window._attr_checks = {
        "ACTIVE": type("_Check", (), {"checkState": lambda self: _UNCHECKED_STATE})(),
    }
    window._checkbox_value_map = {}
    window._attr_labels = {
        "AERODROMEID": "Aerodrome",
        "AOI_SITUATION": "Situation",
        "TRAFFIC_CLASS": "Traffic category",
        "ACTIVE": "Active",
    }
    window._attr_types = {name: "varchar" for name in window._attr_labels}
    window._attribute_fields = [
        (name, _FieldBrowserWidget())
        for name in ("AERODROMEID", "AOI_SITUATION", "TRAFFIC_CLASS")
    ]
    window._checkbox_fields = [("ACTIVE", _FieldBrowserWidget())]
    window._attribute_grid = _FieldGrid()
    window._checkbox_grid = _FieldGrid()
    window._attribute_layout_key = None
    window._field_search_edit = _FieldBrowserWidget()
    window._filled_fields_check = _FieldBrowserWidget()
    window._field_count_label = _FieldBrowserWidget()
    window._no_fields_label = _FieldBrowserWidget()
    viewport = type("_Viewport", (), {"width": lambda self: self.available_width})()
    viewport.available_width = 1200
    window._attr_scroll_area = type("_Scroll", (), {"viewport": lambda self: viewport})()
    window._show_flight_level = False
    return window


def test_filter_grid_breakpoints_keep_fields_readable_and_limit_columns():
    column_count = LayerCustomViewWindow._filter_grid_column_count
    for width, expected in [(0, 1), (260, 1), (533, 1), (534, 2),
                            (807, 2), (808, 3), (1081, 3), (1082, 4), (3000, 4)]:
        assert column_count(width, 20) == expected
    assert column_count(3000, 2) == 2
    assert column_count(3000, 0) == 1


def test_layout_enums_support_scoped_qt6_and_unscoped_qt5():
    from geodata_catalog.ui.layer_custom_view_dock import _qt_enum_value

    scoped = type("_Qt6", (), {"Orientation": type("_Orientation", (), {"Vertical": 2})})
    legacy = type("_Qt5", (), {"Orientation": type("_Orientation", (), {}), "Vertical": 2})
    assert _qt_enum_value(scoped, "Orientation", "Vertical") == 2
    assert _qt_enum_value(legacy, "Orientation", "Vertical") == 2


def test_field_search_matches_names_and_labels_without_changing_filters():
    window = _field_browser_window()
    original_filter = window._current_filter()
    window._field_search_edit.setText("  traffic CLASS ")
    window._refresh_attribute_fields()
    assert all(not cell.visible for _name, cell in window._attribute_fields)
    assert window._no_fields_label.visible is True

    for query in (" traffic_class ", " TRAFFIC CATEGORY "):
        window._field_search_edit.setText(query)
        window._refresh_attribute_fields()
        assert [name for name, cell in window._attribute_fields if cell.visible] == ["TRAFFIC_CLASS"]
        assert window._no_fields_label.visible is False
        assert "1 of 4 fields | 3 filled" in window._field_count_label.text()
        assert "2 filled fields hidden" in window._field_count_label.text()
        assert window._current_filter() == original_filter


def test_filled_fields_include_unchecked_checkbox_and_multi_value_dropdown():
    window = _field_browser_window()
    window._filled_fields_check.setChecked(True)
    window._refresh_attribute_fields()
    assert [name for name, cell in window._attribute_fields if cell.visible] == [
        "AERODROMEID", "TRAFFIC_CLASS",
    ]
    assert window._checkbox_fields[0][1].visible is True
    assert window._attribute_filter_value("ACTIVE") == "N"
    assert window._attribute_filter_value("TRAFFIC_CLASS") == "CIVIL, MILITARY"
    assert window._field_count_label.text() == "3 of 4 fields | 3 filled"

    window._attr_edits["AERODROMEID"].clear()
    window._refresh_attribute_fields()
    assert window._attribute_fields[0][1].visible is False
    assert window._field_count_label.text() == "2 of 4 fields | 2 filled"


def test_field_layout_reflows_existing_widgets_without_gaps_or_stale_columns():
    window = _field_browser_window()
    window._refresh_attribute_fields()
    original_cells = [cell for _name, cell in window._attribute_fields]
    assert [(row, col) for _cell, row, col in window._attribute_grid.items] == [
        (0, 0), (0, 1), (0, 2),
    ]
    window._attr_scroll_area.viewport().available_width = 598
    window._refresh_attribute_fields()
    assert [(row, col) for _cell, row, col in window._attribute_grid.items] == [
        (0, 0), (0, 1), (1, 0),
    ]
    assert window._attribute_grid.stretches == {0: 1, 1: 1, 2: 0, 3: 0}
    assert [cell for cell, _row, _col in window._attribute_grid.items] == original_cells
    window._field_search_edit.setText("traffic")
    window._refresh_attribute_fields()
    assert window._attribute_grid.items == [(original_cells[2], 0, 0)]
    assert window._attribute_grid.stretches == {0: 1, 1: 0, 2: 0, 3: 0}


def test_reset_filters_restores_all_fields_and_clears_hidden_values():
    window = _field_browser_window()
    window._field_search_edit.setText("traffic")
    window._filled_fields_check.setChecked(True)
    window._enabled_check = window._lower_spin = window._upper_spin = None
    window._attr_checks = {}
    window._checkbox_fields = []
    window._set_combo_filter_text = lambda combo, text: combo.lineEdit().setText(text)
    window._sync_preset_button_state = lambda _lower, _upper: None
    applied = []
    window._on_search_clicked = lambda: applied.append(window._current_filter())
    window._on_reset_filters()
    assert window._field_search_edit.text() == ""
    assert window._filled_fields_check.isChecked() is False
    assert all(cell.visible for _name, cell in window._attribute_fields)
    assert applied[0].attributes == []
    assert window._field_count_label.text() == "3 of 3 fields | 0 filled"


def test_viewport_resize_reflows_fields_with_qt6_scoped_event(monkeypatch):
    window = _field_browser_window()
    window._attr_combo_line_edits = {}
    scoped_event = type("_Event", (), {"Type": type("_Type", (), {"Resize": 14})})
    monkeypatch.setattr("geodata_catalog.ui.layer_custom_view_dock.QEvent", scoped_event)
    event = type("_Resize", (), {"type": lambda self: 14})()
    window.eventFilter(window._attr_scroll_area.viewport(), event)
    assert window._attribute_layout_key == (
        4, ("ACTIVE", "AERODROMEID", "AOI_SITUATION", "TRAFFIC_CLASS"),
    )


class _DummyExportFormatCombo:
    def __init__(self, value: str):
        self._value = value

    def currentData(self):
        return self._value


class _DummyMessageBox:
    def __init__(self):
        self.information_calls: list[tuple[Any, ...]] = []
        self.warning_calls: list[tuple[Any, ...]] = []

    def information(self, *_args, **_kwargs):
        self.information_calls.append(tuple(_args))
        return None

    def warning(self, *_args, **_kwargs):
        self.warning_calls.append(tuple(_args))
        return None


class _DummyLayer:
    def __init__(self, layer_name: str):
        self._layer_name = layer_name

    def name(self) -> str:
        return self._layer_name


class _DummySelectableLayer:
    def __init__(self):
        self.selected_fids: list[int] = []

    def selectByIds(self, fids: list[int]) -> None:
        self.selected_fids = fids


class _DummySelectedItem:
    def __init__(self, row: int):
        self._row = row

    def row(self) -> int:
        return self._row


class _DummyTableSelection:
    def __init__(self, selected_rows: list[int]):
        self._selected_rows = selected_rows

    def selectedItems(self) -> list[_DummySelectedItem]:
        return [_DummySelectedItem(row) for row in self._selected_rows]


def test_append_trailing_separator_adds_comma_space_once():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    combo = _DummyCombo("DEC365")

    window._append_trailing_separator(combo)
    assert combo.lineEdit().text() == "DEC365, "


def test_record_cell_click_toggles_clicked_record():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    layer = _DummySelectableLayer()
    window._layer = layer
    window._checked_fids = {11, 13}
    window._current_fids = [11, 12, 13]
    window._logger = None
    window._update_map_highlights = lambda _fids: None
    window._fill_table = lambda: None

    window._on_record_cell_clicked(1, 1)
    assert layer.selected_fids == [11, 12, 13]

    window._on_record_cell_clicked(1, 1)
    assert layer.selected_fids == [11, 13]


def test_record_checkbox_click_is_handled_only_by_item_changed():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    layer = _DummySelectableLayer()
    window._layer = layer
    window._checked_fids = {11}
    window._current_fids = [11]
    window._logger = None
    window._update_map_highlights = lambda _fids: None

    window._on_record_cell_clicked(0, 0)

    assert layer.selected_fids == []
    assert window._checked_fids == {11}


def test_clear_map_selection_removes_checked_features_and_highlights():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    layer = _DummySelectableLayer()
    window._layer = layer
    window._checked_fids = {11, 13}
    window._table = type("_T", (), {"clearSelection": lambda self: None})()
    window._logger = None
    cleared = {"highlights": False}
    window._clear_map_highlights = lambda: cleared.update(highlights=True)
    window._update_map_highlights = lambda _fids: None
    window._apply_view_state = lambda: None

    window._clear_map_selection()

    assert window._checked_fids == set()
    assert layer.selected_fids == []
    assert cleared["highlights"] is True


class _SelectionSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self):
        for callback in self.callbacks:
            callback([], [], False)


class _SignallingLayer(_DummySelectableLayer):
    def __init__(self):
        super().__init__()
        self.selectionChanged = _SelectionSignal()
        self.selection_writes = 0

    def selectedFeatureIds(self):
        return list(self.selected_fids)

    def selectByIds(self, fids):
        super().selectByIds(fids)
        self.selection_writes += 1
        self.selectionChanged.emit()


class _SelectionWidget:
    def __init__(self, value=None):
        self.value = value
        self.enabled = None
        self.text = ""

    def currentData(self):
        return self.value

    def count(self):
        return 1

    def setText(self, text):
        self.text = text

    def setEnabled(self, enabled):
        self.enabled = enabled


def _selection_window():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    window._all_records = [
        {"__fid": fid, "name": name}
        for fid, name in [(1, "Alpha"), (2, "Bravo"), (3, "Charlie"), (4, "Delta")]
    ]
    window._columns = [{"name": "name", "type": "varchar"}]
    window._checked_fids = set()
    window._syncing_selection = False
    window._record_order_cache = None
    window._current_page = 1
    window._quick_search_active_text = ""
    window._quick_search_active_column = None
    window._sort_column_combo = _SelectionWidget("name")
    window._sort_order_combo = _SelectionWidget("asc")
    window._page_size_spin = type("_PageSize", (), {"value": lambda self: 2})()
    window._summary_label = _SelectionWidget()
    window._selection_label = _SelectionWidget()
    window._clear_selection_btn = _SelectionWidget()
    window._prev_btn = _SelectionWidget()
    window._next_btn = _SelectionWidget()
    window._layer = _SignallingLayer()
    window._logger = None
    window._map_canvas = None
    window._map_highlights = []
    window._table = type("_Table", (), {
        "scrollToTop": lambda self: None,
        "clearSelection": lambda self: None,
    })()
    window._fill_table = lambda: None
    window._layer.selectionChanged.connect(window._on_layer_selection_changed)
    return window


def test_map_selection_pins_checks_and_returns_to_first_page_without_feedback():
    window = _selection_window()
    window._current_page = 2

    window._layer.selectByIds([4, 3])

    assert window._checked_fids == {3, 4}
    assert window._current_page == 1
    assert window._current_fids == [3, 4]
    assert window._selection_label.text == "Selected: 2"
    assert window._clear_selection_btn.enabled is True
    assert window._layer.selection_writes == 1

    window._layer.selectByIds([2])
    assert window._checked_fids == {2}
    assert window._current_fids == [2, 1]

    window._layer.selectByIds([])
    assert window._checked_fids == set()
    assert window._current_fids == [1, 2]
    assert window._clear_selection_btn.enabled is False


def test_selected_records_bypass_quick_search_but_not_layer_results():
    window = _selection_window()
    window._quick_search_active_text = "bravo"
    window._quick_search_active_column = "name"

    window._layer.selectByIds([4, 99])

    assert window._current_fids == [4, 2]
    assert window._selection_label.text == "Selected: 2"
    assert "1 match search" in window._summary_label.text
    assert window._all_records[0]["__fid"] == 1
    window._clear_map_selection()
    assert window._current_fids == [2]
    assert window._layer.selectedFeatureIds() == []
    assert window._clear_selection_btn.enabled is False


def test_selection_order_preserves_descending_sort_and_paging():
    window = _selection_window()
    window._sort_order_combo.value = "desc"
    window._layer.selectByIds([1, 3, 4])
    assert window._current_fids == [4, 3]

    window._on_next_page()
    assert window._current_fids == [1, 2]
    window._clear_map_selection()
    assert window._current_page == 1
    assert window._current_fids == [4, 3]
    assert window._checked_fids == set()


def test_table_selection_does_not_move_rows_or_reenter_view_refresh():
    window = _selection_window()
    window._apply_view_state()
    window._on_record_cell_clicked(1, 1)
    assert window._checked_fids == {2}
    assert window._current_fids == [1, 2]
    assert window._layer.selectedFeatureIds() == [2]
    assert window._syncing_selection is False


def test_selection_reuses_sort_cache_and_invalidates_on_sort_search_and_reload():
    window = _selection_window()
    window._apply_view_state()
    cache = window._record_order_cache
    window._layer.selectByIds([4])
    assert window._record_order_cache is cache

    window._sort_order_combo.value = "desc"
    window._apply_view_state()
    assert window._record_order_cache is not cache
    assert window._current_fids == [4, 3]

    window._quick_search_active_text = "bravo"
    window._apply_view_state()
    assert window._current_fids == [4, 2]

    window._all_records = [{"__fid": 5, "name": "Bravo"}]
    window._apply_view_state()
    assert window._current_fids == [5]


def test_fill_table_checks_selected_features_and_unchecks_deselected_features(monkeypatch):
    class _Item:
        def __init__(self, text):
            self.text = text

        def setFlags(self, flags):
            self.flags = flags

        def setCheckState(self, state):
            self.state = state

        def setData(self, role, value):
            self.fid = value

    class _Table:
        def __init__(self):
            self.items = {}

        def blockSignals(self, blocked):
            self.blocked = blocked

        def setRowCount(self, count):
            self.row_count = count

        def setItem(self, row, column, item):
            self.items[row, column] = item

    monkeypatch.setattr("geodata_catalog.ui.layer_custom_view_dock.QTableWidgetItem", _Item)
    flags = {
        "enabled": 1, "checkable": 2, "selectable": 4,
        "checked": 2, "unchecked": 0, "user_role": 256,
    }
    monkeypatch.setattr("geodata_catalog.ui.layer_custom_view_dock._ITEM_FLAGS", flags)
    window = _selection_window()
    window._table = _Table()
    window._resize_table_columns_to_contents = lambda: None
    window._apply_record_highlight = lambda _item, _selected: None
    window._current_records = window._all_records[:2]
    window._current_fids = [1, 2]
    window._checked_fids = {2}

    LayerCustomViewWindow._fill_table(window)
    assert window._table.items[0, 0].state == flags["unchecked"]
    assert window._table.items[1, 0].state == flags["checked"]
    assert window._table.items[1, 0].fid == 2
    assert window._table.blocked is False
    assert window._updating_table is False
    assert window._clear_selection_btn.enabled is True

    window._checked_fids.clear()
    LayerCustomViewWindow._fill_table(window)
    assert window._table.items[1, 0].state == flags["unchecked"]
    assert window._clear_selection_btn.enabled is False


def test_selection_item_flags_support_scoped_qt6_enums(monkeypatch):
    from geodata_catalog.ui.layer_custom_view_dock import _get_item_flags

    class _ScopedQt:
        class ItemFlag:
            ItemIsEnabled = 1
            ItemIsUserCheckable = 2
            ItemIsSelectable = 4

        class CheckState:
            Checked = 2
            Unchecked = 0

        class ItemDataRole:
            UserRole = 256

    monkeypatch.setattr("geodata_catalog.ui.layer_custom_view_dock.Qt", _ScopedQt)
    flags = _get_item_flags()
    assert flags["user_role"] == 256
    assert flags["checked"] == 2
    assert flags["checkable"] == 2


def test_vector_export_temporary_selection_does_not_reorder_results(monkeypatch, tmp_path):
    class _Writer:
        NoError = 0

        class SaveVectorOptions:
            pass

        @staticmethod
        def writeAsVectorFormatV3(layer, _path, _context, _options):
            assert layer.selectedFeatureIds() == [1, 2, 3, 4]
            return (0, "")

    monkeypatch.setattr("geodata_catalog.ui.layer_custom_view_dock.QgsVectorFileWriter", _Writer)
    window = _selection_window()
    window._layer.name = lambda: "Sample"
    window._layer.selectByIds([4])
    window._on_next_page()
    previous_page = window._current_page
    previous_fids = list(window._current_fids)

    window._write_vector_export(tmp_path / "out.geojson", "geojson", [1, 2, 3, 4])

    assert window._layer.selectedFeatureIds() == [4]
    assert window._checked_fids == {4}
    assert window._current_page == previous_page
    assert window._current_fids == previous_fids
    assert window._syncing_selection is False


def test_map_selection_uses_checked_records_only():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    layer = _DummySelectableLayer()
    window._layer = layer
    window._checked_fids = {11, 13}
    window._logger = None
    window._update_map_highlights = lambda _fids: None

    window._update_map_selection()
    assert layer.selected_fids == [11, 13]


def test_map_selection_clears_layer_when_no_records_are_selected():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    layer = _DummySelectableLayer()
    window._layer = layer
    window._checked_fids = set()
    window._current_fids = [11]
    window._table = _DummyTableSelection([])
    window._logger = None

    window._update_map_selection()

    assert layer.selected_fids == []


def test_candidate_values_for_child_column_follow_parent_selection():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    window._filter_by_map = {"flight_sector": "sectors_combination"}
    window._attr_combos = {"sectors_combination": _DummyCombo("DEC365")}
    window._distinct_values = {
        "flight_sector": ["DELTA_H", "DELTA_L", "BRAVO_H"],
        "sectors_combination": ["DEC365", "DEC366"],
    }
    window._filtered_distinct_values = {
        "flight_sector": {
            "DEC365": ["DELTA_H", "DELTA_L"],
            "DEC366": ["BRAVO_H"],
        }
    }

    values = window._candidate_values_for_column("flight_sector")
    assert sorted(values) == ["DELTA_H", "DELTA_L"]


def test_candidate_values_for_child_column_falls_back_when_parent_not_single():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    window._filter_by_map = {"flight_sector": "sectors_combination"}
    window._attr_combos = {"sectors_combination": _DummyCombo("DEC365, DEC366")}
    window._distinct_values = {
        "flight_sector": ["DELTA_H", "DELTA_L", "BRAVO_H"],
        "sectors_combination": ["DEC365", "DEC366"],
    }
    window._filtered_distinct_values = {
        "flight_sector": {
            "DEC365": ["DELTA_H", "DELTA_L"],
            "DEC366": ["BRAVO_H"],
        }
    }

    values = window._candidate_values_for_column("flight_sector")
    assert sorted(values) == ["BRAVO_H", "DELTA_H", "DELTA_L"]


def test_export_format_spec_geojson_defaults():
    ext, file_filter, driver = LayerCustomViewWindow._export_format_spec("geojson")
    assert ext == "geojson"
    assert file_filter == "GeoJSON Files (*.geojson)"
    assert driver == "GeoJSON"


def test_export_format_spec_kml():
    ext, file_filter, driver = LayerCustomViewWindow._export_format_spec("kml")
    assert ext == "kml"
    assert file_filter == "KML Files (*.kml)"
    assert driver == "KML"


def test_export_format_spec_csv():
    ext, file_filter, driver = LayerCustomViewWindow._export_format_spec("csv")
    assert ext == "csv"
    assert file_filter == "CSV Files (*.csv)"
    assert driver == "CSV"


def test_export_format_spec_xlsx():
    ext, file_filter, driver = LayerCustomViewWindow._export_format_spec("xlsx")
    assert ext == "xlsx"
    assert file_filter == "Excel Files (*.xlsx)"
    assert driver == "XLSX"


def test_ensure_export_extension_adds_missing_suffix(tmp_path):
    base_path = tmp_path / "selected_records"
    ensured = LayerCustomViewWindow._ensure_export_extension(base_path, "geojson")
    assert ensured.name == "selected_records.geojson"


def test_ensure_export_extension_keeps_existing_suffix(tmp_path):
    base_path = tmp_path / "selected_records.kml"
    ensured = LayerCustomViewWindow._ensure_export_extension(base_path, "kml")
    assert ensured.name == "selected_records.kml"


def test_export_selected_records_passes_all_filtered_fids(monkeypatch, tmp_path):
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    window._layer = object()
    window._all_records = [
        {"__fid": 1, "name": "A"},
        {"__fid": 2, "name": "B"},
        {"__fid": 3, "name": "C"},
    ]
    window._checked_fids = set()
    window._export_format_combo = _DummyExportFormatCombo("geojson")
    window._EXPORT_FORMAT_GEOJSON = "geojson"
    window._EXPORT_FORMAT_KML = "kml"
    window._logger = None

    chosen_path = tmp_path / "out.geojson"
    captured: dict[str, object] = {}

    def _fake_choose_export_path(export_format: str):
        captured["format"] = export_format
        return chosen_path

    def _fake_write_vector_export(file_path, export_format, selected_fids):
        captured["file_path"] = file_path
        captured["write_format"] = export_format
        captured["selected_fids"] = list(selected_fids)

    monkeypatch.setattr(
        "geodata_catalog.ui.layer_custom_view_dock.QMessageBox",
        _DummyMessageBox(),
    )
    monkeypatch.setattr(window, "_choose_export_path", _fake_choose_export_path)
    monkeypatch.setattr(window, "_write_vector_export", _fake_write_vector_export)

    window._on_export_selected_records()

    assert captured["format"] == "geojson"
    assert captured["file_path"] == chosen_path
    assert captured["write_format"] == "geojson"
    assert captured["selected_fids"] == [1, 2, 3]


def test_export_selected_records_without_filtered_results_does_not_write(monkeypatch):
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    window._layer = object()
    window._all_records = []
    window._checked_fids = set()
    window._export_format_combo = _DummyExportFormatCombo("geojson")
    window._EXPORT_FORMAT_GEOJSON = "geojson"
    window._EXPORT_FORMAT_KML = "kml"
    window._logger = None

    message_box = _DummyMessageBox()
    monkeypatch.setattr(
        "geodata_catalog.ui.layer_custom_view_dock.QMessageBox",
        message_box,
    )

    called = {"write": False}

    def _fake_write_vector_export(_file_path, _export_format, _selected_fids):
        called["write"] = True

    monkeypatch.setattr(window, "_write_vector_export", _fake_write_vector_export)

    window._on_export_selected_records()

    assert called["write"] is False
    assert len(message_box.information_calls) == 1
    assert "No records match the current filter criteria" in str(message_box.information_calls[0][2])


def test_build_export_file_basename_uses_layer_and_criteria(monkeypatch):
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    window._layer = _DummyLayer("MUAC Sectors")
    window._MAX_EXPORT_FILENAME_LENGTH = 140

    layer_filter = LayerFilter(
        flight_level=FlightLevelFilter(
            mode=LayerFilterService.MODE_BETWEEN,
            lower=245,
            upper=355,
            enabled=True,
            lower_field="fl_lower",
            upper_field="fl_upper",
        ),
        attributes=[
            AttributeSearchFilter(column="sector_combination", value="DEC365, DEC366"),
            AttributeSearchFilter(column="flight_sectorid", value="LUX_H"),
        ],
    )

    monkeypatch.setattr(window, "_current_filter", lambda: layer_filter)

    basename = window._build_export_file_basename()
    assert basename.startswith("MUAC_Sectors_")
    assert "DEC365_DEC366" in basename
    assert "LUX_H" in basename
    assert basename.endswith("fl-245-355")


def test_build_export_file_basename_truncates_long_names(monkeypatch):
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    window._layer = _DummyLayer("Very Long Layer Name")
    window._MAX_EXPORT_FILENAME_LENGTH = 30

    long_value = "X" * 200
    layer_filter = LayerFilter(
        flight_level=FlightLevelFilter(
            mode=LayerFilterService.MODE_NONE,
            lower=0,
            upper=600,
            enabled=False,
            lower_field="fl_lower",
            upper_field="fl_upper",
        ),
        attributes=[AttributeSearchFilter(column="description", value=long_value)],
    )

    monkeypatch.setattr(window, "_current_filter", lambda: layer_filter)

    basename = window._build_export_file_basename()
    assert len(basename) <= 30