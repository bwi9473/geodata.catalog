from geodata_catalog.plugin import GeoDataCatalogPlugin
from geodata_catalog.services.layer_filter_service import FlightLevelFilter, LayerFilter
from qgis.PyQt.QtWidgets import QAction


class _FakeFields:
    def __init__(self, names):
        self._names = list(names)

    def names(self):
        return list(self._names)


class _FakeLayer:
    def __init__(self, names, subset_string: str = ""):
        self._fields = _FakeFields(names)
        self._subset_string = subset_string
        self.last_subset_string = subset_string

    def fields(self):
        return self._fields

    def subsetString(self):
        return self._subset_string

    def setSubsetString(self, value: str):
        self._subset_string = value
        self.last_subset_string = value

    def name(self):
        return "FS_KAMI"


def test_resolve_layer_field_name_case_insensitive():
    plugin = GeoDataCatalogPlugin.__new__(GeoDataCatalogPlugin)
    layer = _FakeLayer(["FL_LOWER", "FL_UPPER", "STATUS"])

    assert plugin._resolve_layer_field_name(layer, "fl_lower") == "FL_LOWER"
    assert plugin._resolve_layer_field_name(layer, "fl_upper") == "FL_UPPER"
    assert plugin._resolve_layer_field_name(layer, "STATUS") == "STATUS"


def test_normalize_flight_level_fields_uses_real_layer_case():
    plugin = GeoDataCatalogPlugin.__new__(GeoDataCatalogPlugin)
    layer = _FakeLayer(["FL_LOWER", "FL_UPPER"])
    fl = FlightLevelFilter(
        mode="between",
        lower=100,
        upper=350,
        enabled=True,
        lower_field="fl_lower",
        upper_field="fl_upper",
    )

    normalized = plugin._normalize_flight_level_fields(layer, fl)

    assert normalized.lower_field == "FL_LOWER"
    assert normalized.upper_field == "FL_UPPER"


def test_apply_layer_filter_removes_cleared_distinct_selection_clause():
    plugin = GeoDataCatalogPlugin.__new__(GeoDataCatalogPlugin)

    class _FakeLayerDef:
        searchable_columns = [
            {"name": "sectors_combinid", "use_distinct": True},
            {"name": "flight_sectorid", "use_distinct": True, "filter_by": "sectors_combinid"},
            {"name": "setting_sectorid", "use_distinct": True},
        ]

    layer = _FakeLayer(
        ["SECTORS_COMBINID", "FLIGHT_SECTORID", "SETTING_SECTORID", "FL_LOWER", "FL_UPPER"],
        subset_string='("sectors_combinid" = \'BRU355\') AND ("flight_sectorid" = \'KOKSY_H\')',
    )

    plugin._find_layer_definition_for_qgis_layer = lambda _layer: _FakeLayerDef()
    plugin._logger = type("_L", (), {"info": lambda self, _msg: None})()

    layer_filter = LayerFilter(
        flight_level=FlightLevelFilter(
            mode="none",
            lower=0,
            upper=600,
            enabled=False,
            lower_field="fl_lower",
            upper_field="fl_upper",
        ),
        attributes=[],
    )

    plugin._apply_layer_filter(layer, layer_filter)

    assert layer.last_subset_string == ""


def test_build_geodata_context_menu_includes_quick_search_vertices_and_group_columns():
    plugin = GeoDataCatalogPlugin.__new__(GeoDataCatalogPlugin)
    plugin.iface = type("_Iface", (), {"mainWindow": lambda self: object()})()
    plugin._logger = type("_L", (), {"warning": lambda self, _msg: None, "info": lambda self, _msg: None})()
    plugin._layer_panel_filter_action = QAction("Quick Search", None)

    class _FakeService:
        def set_vertices_visible(self, _layer, _visible):
            return None

        def apply_value_grouping_rules(self, _layer, field_name):
            return field_name

    class _FakeLayerDef:
        searchable_columns = [{"name": "status"}, {"name": "region"}]

    class _FakeLayer:
        def name(self):
            return "Sample Layer"

    plugin._layer_toolbox_service = _FakeService()
    plugin._find_layer_definition_for_qgis_layer = lambda _layer: _FakeLayerDef()

    menu = plugin._build_geodata_context_menu(_FakeLayer())
    texts = [action.text() for action in menu.actions()]

    assert "Show Vertices" in texts
    assert "Hide Vertices" in texts
    assert "Quick Search" in texts
    assert "Group By" in texts

    group_by = next(action for action in menu.actions() if getattr(action, "text", lambda: "")() == "Group By")
    subgroup = group_by.menu()
    subgroup_texts = [action.text() for action in subgroup.actions()]

    assert "status" in subgroup_texts
    assert "region" in subgroup_texts
