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