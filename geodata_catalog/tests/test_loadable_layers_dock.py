from types import SimpleNamespace

import pytest

from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.ui import loadable_layers_dock as panel


class _LayerItem:
    def __init__(self, labels):
        self.labels = labels
        self.roles = {}
        self.tooltip = ""
        self.hidden = False
        self.disabled = False
        self.selected = False

    def setData(self, column, role, value):
        self.roles[column, role] = value

    def data(self, column, role):
        return self.roles.get((column, role))

    def text(self, column):
        return self.labels[column]

    def setToolTip(self, column, text):
        self.tooltip = text

    def toolTip(self, column):
        return self.tooltip

    def setHidden(self, hidden):
        self.hidden = hidden

    def setDisabled(self, disabled):
        self.disabled = disabled

    def setSelected(self, selected):
        self.selected = selected

    def setIcon(self, column, icon):
        pass

    def setTextAlignment(self, column, alignment):
        pass


class _LayerTree:
    def __init__(self):
        self.items = []
        self.current = None

    def clear(self):
        self.items.clear()

    def addTopLevelItem(self, item):
        self.items.append(item)

    def topLevelItemCount(self):
        return len(self.items)

    def topLevelItem(self, index):
        return self.items[index]

    def setCurrentItem(self, item):
        self.current = item


@pytest.fixture
def dock(monkeypatch):
    monkeypatch.setattr(panel, "QTreeWidgetItem", _LayerItem)
    monkeypatch.setattr(panel, "QIcon", lambda *_args: object())
    monkeypatch.setattr(panel.LoadableLayersDockWidget, "_right_alignment", lambda self: 0)
    dock = panel.LoadableLayersDockWidget.__new__(panel.LoadableLayersDockWidget)
    dock.layers_tree = _LayerTree()
    dock._highlighted_identity = None
    dock._selected_category = ""
    dock.filter_edit = SimpleNamespace(text=lambda: "")
    dock.navigation = SimpleNamespace(
        set_entries=lambda entries, selected: setattr(dock, "entries", entries)
    )
    dock._populate_presets = lambda: None
    dock._show_layer_details = lambda layer: None
    layers = [
        LayerDefinition("db", "ROADS", "Roads", "oracle", "", geometry_column="SHAPE"),
        LayerDefinition("files", "PARKS", "Parks", "geojson", ""),
        LayerDefinition("db", "RAIL", "Rail", "oracle", ""),
    ]
    dock.rows = [
        {
            "datasource_id": layer.datasource_id,
            "source_name": source,
            "source_type": layer.provider_key,
            "business_group": category,
            "layer": layer,
            "loadable": loadable,
            "availability_reason": "Not connected" if not loadable else "",
        }
        for layer, source, category, loadable in zip(
            layers,
            ["Database", "Local files", "Database"],
            ["Transport", "Nature", "Transport"],
            [True, True, False],
        )
    ]
    dock.set_rows(dock.rows, set(), "")
    return dock


def test_data_panel_renders_only_layers_and_groups_navigation(dock):
    assert dock.layers_tree.topLevelItemCount() == 3
    assert all(
        len(item.data(0, panel.USER_ROLE)) == 4
        for item in dock.layers_tree.items
    )
    assert [(entry[0], entry[2]) for entry in dock.entries] == [
        ("", 3), ("Nature", 1), ("Transport", 2)
    ]
    rail = next(item for item in dock.layers_tree.items if item.text(0).startswith("Rail"))
    assert rail.disabled
    assert "Not connected" in rail.tooltip


def test_data_panel_combines_navigation_and_search(dock):
    dock.filter_edit = SimpleNamespace(text=lambda: "roads")
    dock._on_navigation_changed("Transport")
    assert [item.text(0) for item in dock.layers_tree.items if not item.hidden] == [
        "Roads (0 saved layers)"
    ]
    dock._on_navigation_changed("Nature")
    assert all(item.hidden for item in dock.layers_tree.items)
    dock._on_navigation_changed("")
    dock._apply_filter("local files")
    assert [item.text(0) for item in dock.layers_tree.items if not item.hidden] == [
        "Parks (0 saved layers)"
    ]
    dock._apply_filter("transport")
    assert sum(not item.hidden for item in dock.layers_tree.items) == 2
    dock._apply_filter("")
    assert all(not item.hidden for item in dock.layers_tree.items)


def test_layer_tooltip_includes_geometry_column(dock):
    roads = next(item for item in dock.layers_tree.items if item.text(0).startswith("Roads"))
    parks = next(item for item in dock.layers_tree.items if item.text(0).startswith("Parks"))
    assert "Geometry column: SHAPE" in roads.tooltip
    assert "Geometry column: Not set" in parks.tooltip


@pytest.mark.parametrize("query", ["roads", "ROADS", "rOaDs"])
def test_data_panel_layer_search_is_case_insensitive(dock, query):
    dock._apply_filter(query)
    assert [item.text(0) for item in dock.layers_tree.items if not item.hidden] == [
        "Roads (0 saved layers)"
    ]


def test_data_panel_selects_flat_layer_for_saved_view_and_emits_load(dock):
    emitted = []
    dock.load_layer_requested = SimpleNamespace(
        emit=lambda *args: emitted.append(args)
    )
    dock._select_tree_layer("db", "ROADS")
    roads = dock.layers_tree.current
    assert roads.selected
    dock._on_item_double_clicked(roads, 0)
    assert emitted == [("db", "ROADS")]
    dock._select_tree_layer("db", "RAIL")
    assert not roads.selected
    dock._on_item_double_clicked(dock.layers_tree.current, 0)
    assert emitted == [("db", "ROADS")]


def test_data_panel_refresh_resets_missing_category_and_handles_empty_rows(dock):
    dock._selected_category = "Transport"
    dock.set_rows([dock.rows[1]], set(), "")
    assert dock._selected_category == ""
    assert dock.layers_tree.topLevelItemCount() == 1
    assert not dock.layers_tree.items[0].hidden
    dock.set_rows([], set(), "")
    assert dock.layers_tree.topLevelItemCount() == 0
    assert [(entry[0], entry[2]) for entry in dock.entries] == [("", 0)]
