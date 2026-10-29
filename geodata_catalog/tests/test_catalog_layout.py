from types import SimpleNamespace

from geodata_catalog.ui import catalog_layout
from geodata_catalog.ui.catalog_layout import CollapsibleSection, catalog_styles
from geodata_catalog.ui import catalog_dockwidget, loadable_layers_dock
from geodata_catalog.plugin import GeoDataCatalogPlugin
from geodata_catalog.models.datasource import Datasource, DatasourceType
from geodata_catalog.models.layer_definition import LayerDefinition


def test_catalog_windows_use_the_data_panel_size(monkeypatch):
    class _Geometry:
        def width(self):
            return 2000

        def height(self):
            return 1200

    class _Widget:
        def setMinimumSize(self, width, height):
            self.minimum_size = (width, height)

        def resize(self, width, height):
            self.size = (width, height)

    plugin = GeoDataCatalogPlugin.__new__(GeoDataCatalogPlugin)
    geometry = _Geometry()
    monkeypatch.setattr(plugin, "_available_screen_geometry", lambda _widget: geometry)
    monkeypatch.setattr(plugin, "_data_panel_target_geometry", lambda: geometry)
    data_panel = _Widget()
    configuration = _Widget()

    plugin._size_data_panel_window(data_panel)
    plugin._size_configuration_window(configuration)

    assert data_panel.size == configuration.size == (1240, 820)
    assert data_panel.minimum_size == configuration.minimum_size == (1140, 520)


def test_shared_catalog_styles_apply_the_same_navigation_and_selection_colors():
    styles = catalog_styles(
        {
            "primary": "#39784A",
            "primary_text": "#FFFFFF",
            "header_text": "#263D33",
            "selection_background": "#EDF5EE",
            "selection_text": "#24352E",
            "navigation_background": "#173D26",
            "navigation_text": "#F4F7F4",
        }
    )

    assert "QFrame[catalogNavigation='true']" in styles
    assert "QToolButton[sectionToggle='true']" in styles
    assert "background: #39784A" in styles
    assert "background: #EDF5EE" in styles
    assert "background: #173D26" in styles
    assert "color: #F4F7F4" in styles


def test_catalog_navigation_groups_datasources_without_grouping_layer_overview(
    monkeypatch,
):
    monkeypatch.setattr(catalog_dockwidget, "QIcon", lambda *_args: object())
    layer = LayerDefinition(
        "oracle-id",
        "SCHEMA.ROADS",
        "Roads",
        "oracle",
        "",
        business_group="Transport",
    )
    dock = catalog_dockwidget.CatalogDockWidget.__new__(
        catalog_dockwidget.CatalogDockWidget
    )
    dock._grouping_mode = "datasource"
    dock._datasources = [
        Datasource("oracle-id", "Oracle", DatasourceType.ORACLE)
    ]
    dock._layers_by_datasource = {"oracle-id": [layer]}

    groups = dock._navigation_groups()

    assert [(key, label, layers) for key, label, layers, _icon in groups] == [
        ("oracle-id", "Oracle", [layer])
    ]


def test_catalog_navigation_groups_categories_without_nested_category_rows(monkeypatch):
    monkeypatch.setattr(catalog_dockwidget, "QIcon", lambda *_args: object())
    layer = LayerDefinition(
        "oracle-id",
        "SCHEMA.ROADS",
        "Roads",
        "oracle",
        "",
        business_group="Transport",
    )
    dock = catalog_dockwidget.CatalogDockWidget.__new__(
        catalog_dockwidget.CatalogDockWidget
    )
    dock._grouping_mode = "category"
    dock._datasources = [
        Datasource("oracle-id", "Oracle", DatasourceType.ORACLE)
    ]
    dock._layers_by_datasource = {"oracle-id": [layer]}

    groups = dock._navigation_groups()

    assert [(key, label, layers) for key, label, layers, _icon in groups] == [
        ("Transport", "Transport", [layer])
    ]


def test_catalog_tree_renders_layers_directly_without_repeating_navigation_group(
    monkeypatch,
):
    monkeypatch.setattr(catalog_dockwidget, "QIcon", lambda *_args: object())
    layer = LayerDefinition(
        "oracle-id",
        "SCHEMA.ROADS",
        "Roads",
        "oracle",
        "",
        business_group="Transport",
    )

    class _Tree:
        def clear(self):
            return None

    class _Navigation:
        def __init__(self):
            self.entries = []

        def set_entries(self, entries, _selected_key):
            self.entries = entries

    dock = catalog_dockwidget.CatalogDockWidget.__new__(
        catalog_dockwidget.CatalogDockWidget
    )
    dock._grouping_mode = "datasource"
    dock._datasources = [
        Datasource("oracle-id", "Oracle", DatasourceType.ORACLE)
    ]
    dock._layers_by_datasource = {"oracle-id": [layer]}
    dock._selected_group = "oracle-id"
    dock._datasource_items = {}
    dock.datasource_tree = _Tree()
    dock.navigation = _Navigation()
    dock.filter_edit = SimpleNamespace(text=lambda: "")
    rendered = []
    dock._add_layer_item = lambda parent, value, category: rendered.append(
        (parent, value, category)
    )
    dock._apply_filter = lambda _text: None
    dock._show_selection_details = lambda: None

    dock._render_tree()

    assert rendered == [(dock.datasource_tree, layer, "Transport")]
    assert [entry[1] for entry in dock.navigation.entries] == [
        "All layers",
        "Oracle",
    ]


def test_new_layout_helpers_resolve_qt6_scoped_enums(monkeypatch):
    scoped_qt = SimpleNamespace(
        ItemDataRole=SimpleNamespace(UserRole=256),
        ContextMenuPolicy=SimpleNamespace(CustomContextMenu=8),
        ArrowType=SimpleNamespace(DownArrow=1, RightArrow=2),
        ToolButtonStyle=SimpleNamespace(ToolButtonTextBesideIcon=3),
        Orientation=SimpleNamespace(Horizontal=4, Vertical=5),
        ScrollBarPolicy=SimpleNamespace(ScrollBarAlwaysOff=6),
        TextElideMode=SimpleNamespace(ElideRight=7),
    )
    monkeypatch.setattr(catalog_layout, "Qt", scoped_qt)
    monkeypatch.setattr(catalog_dockwidget, "Qt", scoped_qt)
    monkeypatch.setattr(loadable_layers_dock, "Qt", scoped_qt)

    assert CollapsibleSection._arrow("DownArrow") == 1
    assert CollapsibleSection._text_beside_icon() == 3
    assert catalog_dockwidget.CatalogDockWidget._orientation("Vertical") == 5
    assert loadable_layers_dock.LoadableLayersDockWidget._orientation("Horizontal") == 4
    assert catalog_layout.CatalogNavigation._scroll_bar_policy("ScrollBarAlwaysOff") == 6
    assert catalog_layout.CatalogNavigation._text_elide_mode("ElideRight") == 7


def test_new_layout_helpers_preserve_qt5_unscoped_enum_fallbacks(monkeypatch):
    unscoped_qt = SimpleNamespace(
        UserRole=256,
        CustomContextMenu=8,
        DownArrow=1,
        RightArrow=2,
        ToolButtonTextBesideIcon=3,
        Horizontal=4,
        Vertical=5,
        ScrollBarAlwaysOff=6,
        ElideRight=7,
    )
    monkeypatch.setattr(catalog_layout, "Qt", unscoped_qt)
    monkeypatch.setattr(catalog_dockwidget, "Qt", unscoped_qt)
    monkeypatch.setattr(loadable_layers_dock, "Qt", unscoped_qt)

    assert CollapsibleSection._arrow("RightArrow") == 2
    assert CollapsibleSection._text_beside_icon() == 3
    assert catalog_dockwidget.CatalogDockWidget._orientation("Horizontal") == 4
    assert loadable_layers_dock.LoadableLayersDockWidget._orientation("Vertical") == 5
    assert catalog_layout.CatalogNavigation._scroll_bar_policy("ScrollBarAlwaysOff") == 6
    assert catalog_layout.CatalogNavigation._text_elide_mode("ElideRight") == 7
