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


def test_append_trailing_separator_adds_comma_space_once():
    window = LayerCustomViewWindow.__new__(LayerCustomViewWindow)
    combo = _DummyCombo("DEC365")

    window._append_trailing_separator(combo)
    assert combo.lineEdit().text() == "DEC365, "


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