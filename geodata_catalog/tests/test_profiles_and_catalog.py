from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from geodata_catalog import plugin as plugin_module
from geodata_catalog.exceptions import ConfigurationException, DatasourceConnectionException
from geodata_catalog.metadata.datasource_repository import DatasourceRepository
from geodata_catalog.metadata.layer_config_repository import LayerConfig, LayerConfigRepository
from geodata_catalog.metadata.layer_repository import LayerRepository
from geodata_catalog.metadata.profile_repository import ProfileRepository
from geodata_catalog.metadata.saved_layer_view_repository import SavedLayerViewRepository
from geodata_catalog.metadata.settings_manager import SettingsManager
from geodata_catalog.models.datasource import Datasource, DatasourceType
from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.models.saved_layer_view import SavedLayerView
from geodata_catalog.models.user_profile import UserProfile
from geodata_catalog.plugin import GeoDataCatalogPlugin
from geodata_catalog.services.database_session_service import validate_database_config
from geodata_catalog.services.datasource_service import DatasourceService
from geodata_catalog.services.layer_service import LayerService
from geodata_catalog.ui.geometry_toolbar import GeometryToolbar, _enum
from geodata_catalog.ui.loadable_layers_dock import LoadableLayersDockWidget


class MemorySettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def remove(self, key):
        self.values.pop(key, None)


@pytest.fixture
def catalog(tmp_path):
    settings = SettingsManager(settings=MemorySettings(), storage_file_path=str(tmp_path / "config.json"))
    sources = DatasourceRepository(settings)
    dev = Datasource("dev", "Development", DatasourceType.ORACLE, {
        "host": "dev.example", "service_name": "DEV", "catalog_id": "aviation",
    })
    prod = Datasource("prod", "Production", DatasourceType.ORACLE, {
        "host": "prod.example", "service_name": "PROD", "catalog_id": "aviation",
    })
    unrelated = Datasource("other", "Other", DatasourceType.ORACLE, {
        "host": "other.example", "service_name": "OTHER",
    })
    sources.bulk_replace([dev, prod, unrelated])
    configs = LayerConfigRepository(tmp_path / "layer_config.json")
    layers = LayerRepository(settings)
    datasource_service = DatasourceService(sources, Mock())
    connector = Mock()
    connector.get_layers.return_value = []
    datasource_service.get_connector = Mock(return_value=connector)
    service = LayerService(datasource_service, layers, Mock(), configs)
    plugin = GeoDataCatalogPlugin.__new__(GeoDataCatalogPlugin)
    plugin._datasource_service = datasource_service
    plugin._layer_service = service
    plugin._database_session = SimpleNamespace(datasource=prod)
    plugin._layer_cache = {}
    plugin._active_profile = UserProfile("user", "User")
    plugin._saved_layer_view_repository = SavedLayerViewRepository(settings)
    plugin._logger = Mock()
    plugin._loader_service = Mock()
    plugin._show_error = Mock()
    return SimpleNamespace(
        settings=settings, sources=sources, dev=dev, prod=prod, other=unrelated,
        configs=configs, layers=layers, datasource_service=datasource_service,
        connector=connector, service=service, plugin=plugin,
    )


def definition(source_id="dev", name="AIRSPACE.FIR"):
    return LayerDefinition(source_id, name, "FIR", "oracle", "old-development-uri")


def test_default_user_and_developer_profiles_are_persistent(catalog):
    repository = ProfileRepository(catalog.settings)
    profiles, active = repository.load()
    assert active == "user"
    assert profiles[0].is_developer
    profiles[1].visible_layer_ids = ["aviation:AIRSPACE.FIR"]
    repository.save(profiles, "developer")
    restored = ProfileRepository(SettingsManager(
        settings=MemorySettings(), storage_file_path=str(catalog.settings.sibling_file_path("config.json")),
    ))
    assert restored.load() == (profiles, "developer")


def test_profile_visibility_distinguishes_all_none_and_developer():
    assert UserProfile("all", "All").can_view("new:layer")
    assert not UserProfile("none", "None", visible_layer_ids=[]).can_view("new:layer")
    limited = UserProfile("limited", "Limited", visible_layer_ids=["aviation:AIRSPACE.FIR"])
    assert limited.can_view("aviation:AIRSPACE.FIR")
    assert not limited.can_view("other:AIRSPACE.FIR")
    assert UserProfile("dev", "Dev", "developer", []).can_view("any:layer")


@pytest.mark.parametrize("payload", [
    {},
    {"active_profile_id": "missing", "profiles": []},
    {"active_profile_id": "u", "profiles": [{"id": "u", "name": "User", "role": "admin"}]},
    {"active_profile_id": "d", "profiles": [
        {"id": "d", "name": "Developer", "role": "developer", "visible_layer_ids": "all"},
    ]},
])
def test_invalid_profiles_are_reported_not_replaced(catalog, payload):
    catalog.settings.set_json(ProfileRepository.SETTINGS_KEY, payload)
    with pytest.raises(ConfigurationException):
        ProfileRepository(catalog.settings).load()
    assert catalog.settings.get_json(ProfileRepository.SETTINGS_KEY, None) == payload


def test_existing_endpoint_configuration_is_shared_without_reusing_its_uri(catalog):
    catalog.layers.upsert(definition())
    catalog.configs.save(LayerConfig(
        "dev", "AIRSPACE.FIR", layername="Flight regions", category_label="Airspace",
        label_column="NAME", qml_style_path="fir.qml", key_column="ID",
        field_columns=[{"name": "NAME", "search": True, "export": True}],
    ))
    runtime = definition("prod")
    runtime.provider_uri = "authenticated-production-uri"
    catalog.connector.get_layers.return_value = [runtime]
    layer = catalog.service.discover_layers(catalog.prod, include_stats=False)[0]
    assert layer.datasource_id == "prod"
    assert layer.display_name == "Flight regions"
    assert layer.business_group == "Airspace"
    assert layer.provider_uri == "authenticated-production-uri"
    assert layer.label_column == "NAME"
    assert layer.default_style_file == "fir.qml"
    assert layer.metadata["key_column"] == "ID"
    assert layer.searchable_columns == [{"name": "NAME"}]
    assert layer.metadata["view_columns"][0]["name"] == "NAME"
    assert not layer.metadata.get("unavailable")


def test_missing_configured_layer_stays_visible_and_cannot_load(catalog):
    catalog.configs.save(LayerConfig("dev", "AIRSPACE.FIR", layername="Flight regions"))
    rows = catalog.plugin._catalog_rows()
    assert len(rows) == 1
    assert rows[0]["datasource_id"] == "prod"
    assert rows[0]["layer"].display_name == "Flight regions"
    assert rows[0]["layer"].provider_uri == ""
    assert not rows[0]["loadable"]
    assert "not found or not accessible" in rows[0]["availability_reason"]
    catalog.plugin._on_load_layer("prod", "AIRSPACE.FIR")
    catalog.plugin._loader_service.load_layer.assert_not_called()
    catalog.plugin._show_error.assert_called_once()


def test_layer_can_reappear_after_reconnection_without_stale_unavailability(catalog):
    catalog.layers.upsert(definition())
    missing = catalog.service.discover_layers(catalog.prod)[0]
    assert missing.metadata["unavailable"]
    catalog.connector.get_layers.return_value = [definition("prod")]
    available = catalog.service.discover_layers(catalog.prod)[0]
    assert not available.metadata.get("unavailable")
    assert catalog.layers.list_all()[0].metadata == {}


def test_unreachable_database_keeps_category_and_reports_connection_reason(catalog):
    catalog.configs.save(LayerConfig("dev", "AIRSPACE.FIR", category_label="Airspace"))
    catalog.datasource_service.get_connector.side_effect = DatasourceConnectionException("Login required")
    rows = catalog.plugin._catalog_rows()
    assert rows[0]["business_group"] == "Airspace"
    assert rows[0]["availability_reason"] == "Database not connected or not accessible."
    assert not rows[0]["loadable"]


def test_hidden_layers_are_absent_and_direct_requests_are_rejected(catalog):
    catalog.connector.get_layers.return_value = [definition("prod")]
    catalog.plugin._active_profile.visible_layer_ids = []
    assert catalog.plugin._catalog_rows() == []
    catalog.plugin._on_load_layer("prod", "AIRSPACE.FIR")
    catalog.plugin._loader_service.load_layer.assert_not_called()
    assert "not visible" in catalog.plugin._show_error.call_args.args[1]


def test_shared_catalog_is_listed_once_for_active_environment(catalog):
    assert [source.id for source in catalog.plugin._catalog_datasources()] == ["prod", "other"]
    catalog.plugin._database_session.datasource = catalog.dev
    assert [source.id for source in catalog.plugin._catalog_datasources()] == ["dev", "other"]
    assert catalog.dev.catalog_layer_id("AIRSPACE.FIR") == catalog.prod.catalog_layer_id("AIRSPACE.FIR")
    assert catalog.other.catalog_layer_id("AIRSPACE.FIR") != catalog.prod.catalog_layer_id("AIRSPACE.FIR")


def test_conflicting_legacy_display_configuration_is_explicit(catalog):
    catalog.configs.save(LayerConfig("dev", "AIRSPACE.FIR", layername="Dev name"))
    catalog.configs.save(LayerConfig("prod", "AIRSPACE.FIR", layername="Different name"))
    with pytest.raises(ConfigurationException, match="Conflicting legacy"):
        catalog.service.configured_layers(catalog.prod)
    with pytest.raises(ConfigurationException, match="Conflicting legacy"):
        catalog.service.promote_configuration(catalog.prod)


def test_shared_save_takes_precedence_and_survives_endpoint_removal(catalog):
    catalog.configs.save(LayerConfig("dev", "AIRSPACE.FIR", layername="Legacy"))
    catalog.service.promote_configuration(catalog.dev)
    catalog.service.save_display_configuration(
        catalog.prod, LayerConfig("prod", "AIRSPACE.FIR", layername="Shared"),
    )
    catalog.sources.delete("dev")
    config = catalog.service.get_display_configuration(catalog.prod, "AIRSPACE.FIR")
    assert config.datasource_id == "aviation"
    assert config.layername == "Shared"


def test_promoting_to_a_new_group_includes_old_canonical_settings(catalog):
    catalog.configs.save(LayerConfig("aviation", "AIRSPACE.FIR", layername="Shared"))
    new_source = replace(catalog.dev, config={**catalog.dev.config, "catalog_id": "new-group"})
    catalog.service.promote_configuration(new_source, "aviation")
    assert catalog.configs.get("new-group", "AIRSPACE.FIR").layername == "Shared"


def test_saved_views_follow_active_environment_visibility_and_availability(catalog):
    catalog.configs.save(LayerConfig("dev", "AIRSPACE.FIR"))
    view = SavedLayerView("dev", "AIRSPACE.FIR", "FIR", "My view", {}, {}, "")
    catalog.plugin._saved_layer_view_repository.upsert(view)
    views = catalog.plugin._visible_saved_views()
    assert views[0].datasource_id == "prod"
    assert catalog.plugin._saved_layer_view_repository.list_all()[0].datasource_id == "dev"
    catalog.plugin._catalog_rows()
    catalog.plugin._apply_saved_layer_view(view.id)
    catalog.plugin._loader_service.load_layer.assert_not_called()
    catalog.plugin._active_profile.visible_layer_ids = []
    assert catalog.plugin._visible_saved_views() == []
    catalog.plugin._apply_saved_layer_view(view.id)
    catalog.plugin._loader_service.load_layer.assert_not_called()


def test_developer_configuration_entry_points_reject_user_mode(catalog):
    plugin = catalog.plugin
    plugin._on_add_source()
    plugin._on_edit_source("prod")
    plugin._on_delete_source("prod")
    plugin._on_edit_layer_config("prod", "AIRSPACE.FIR")
    plugin._export_layer_configuration()
    plugin._show_dock()
    assert plugin._show_error.call_count == 6


def test_profile_switch_persists_and_refreshes_without_touching_project(catalog, monkeypatch):
    plugin = catalog.plugin
    plugin.iface = Mock()
    plugin._profile_repository = ProfileRepository(catalog.settings)
    plugin._profiles, _ = plugin._profile_repository.load()
    plugin._active_profile = plugin._profiles[0]
    plugin._update_profile_ui = Mock()
    plugin._refresh_connection_views = Mock()
    plugin._show_loadable_layers_dock = Mock()
    monkeypatch.setattr(plugin_module, "QInputDialog", SimpleNamespace(
        getItem=Mock(return_value=("User (user)", True)),
    ))
    plugin._switch_profile()
    assert plugin._active_profile.id == "user"
    assert plugin._profile_repository.load()[1] == "user"
    plugin._update_profile_ui.assert_called_once()
    plugin._refresh_connection_views.assert_called_once()
    plugin._show_loadable_layers_dock.assert_called_once()


def test_visibility_migrates_when_catalog_id_changes(catalog):
    plugin = catalog.plugin
    plugin._profile_repository = ProfileRepository(catalog.settings)
    plugin._profiles, _ = plugin._profile_repository.load()
    plugin._profiles[1].visible_layer_ids = ["dev:AIRSPACE.FIR", "other:AIRSPACE.UIR"]
    plugin._active_profile = plugin._profiles[0]
    plugin._migrate_profile_visibility("dev", "aviation")
    assert plugin._profiles[1].visible_layer_ids == ["aviation:AIRSPACE.FIR", "other:AIRSPACE.UIR"]
    assert plugin._profile_repository.load()[0][1].visible_layer_ids == plugin._profiles[1].visible_layer_ids


def test_user_mode_hides_only_configuration_and_closes_existing_configuration(catalog):
    plugin = catalog.plugin
    plugin._geometry_toolbar = Mock()
    plugin._open_catalog_action = Mock()
    plugin._profile_actions = [Mock(), Mock()]
    plugin._dock_widget = Mock()
    plugin._update_profile_ui()
    plugin._open_catalog_action.setVisible.assert_called_with(False)
    plugin._profile_actions[1].setVisible.assert_called_with(False)
    plugin._dock_widget.close.assert_called_once()
    plugin._active_profile = UserProfile("dev", "Developer", "developer")
    plugin._update_profile_ui()
    plugin._open_catalog_action.setVisible.assert_called_with(True)
    plugin._geometry_toolbar.set_configuration_visible.assert_called_with(True)


def test_unavailable_saved_view_load_button_cannot_emit():
    dock = LoadableLayersDockWidget.__new__(LoadableLayersDockWidget)
    dock._detail_loadable = False
    dock._selected_saved_view_id = "view"
    dock.saved_view_requested = Mock()
    dock._on_load_button_clicked()
    dock.saved_view_requested.emit.assert_not_called()


def test_qt6_scoped_profile_enums_and_toolbar_visibility():
    scoped = SimpleNamespace(
        ItemDataRole=SimpleNamespace(UserRole=256),
        ItemFlag=SimpleNamespace(ItemIsUserCheckable=16),
        CheckState=SimpleNamespace(Checked=2, Unchecked=0),
    )
    assert _enum(scoped, "ItemFlag", "ItemIsUserCheckable") == 16
    assert _enum(scoped, "CheckState", "Checked") == 2
    toolbar = GeometryToolbar(Mock(), Mock())
    toolbar._configuration_action = Mock()
    toolbar.set_configuration_visible(False)
    toolbar._configuration_action.setVisible.assert_called_once_with(False)


@pytest.mark.parametrize("catalog_id", ["", "  ", 42, " spaced "])
def test_invalid_catalog_id_is_reported(catalog_id):
    with pytest.raises(ConfigurationException, match="catalog_id"):
        validate_database_config({"host": "db", "service_name": "DB", "catalog_id": catalog_id})


def test_corrupt_layer_configuration_does_not_silently_hide_layers(tmp_path):
    path = tmp_path / "layer_config.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ConfigurationException, match="Failed to read"):
        LayerConfigRepository(path).list_all()


def test_catalog_refresh_error_clears_previous_profile_rows(catalog):
    plugin = catalog.plugin
    plugin._loadable_layers_dock = Mock()
    plugin._loaded_layer_keys = set()
    plugin._catalog_rows = Mock(side_effect=ConfigurationException("Invalid layer configuration"))
    plugin._refresh_all_layers_view()
    plugin._loadable_layers_dock.set_rows.assert_called_once_with([], set(), "#2777B5", [])
    plugin._show_error.assert_called_once()


def test_saved_views_survive_environment_removal_without_changing_edit_time(catalog):
    repository = catalog.plugin._saved_layer_view_repository
    view = SavedLayerView("dev", "AIRSPACE.FIR", "FIR", "My view", {}, {}, "")
    repository.upsert(view)
    updated_at = repository.list_all()[0].updated_at
    catalog.plugin._migrate_saved_view_catalog(catalog.dev)
    catalog.sources.delete("dev")
    persisted = repository.list_all()[0]
    assert persisted.updated_at == updated_at
    assert persisted.catalog_id == "aviation"
    assert catalog.plugin._visible_saved_views()[0].datasource_id == "prod"


def test_saved_view_names_use_logical_layer_identity_across_environments(catalog):
    repository = catalog.plugin._saved_layer_view_repository
    original = SavedLayerView("dev", "AIRSPACE.FIR", "FIR", "My view", {}, {}, "", catalog_id="aviation")
    repository.upsert(original)
    replacement = SavedLayerView("prod", "AIRSPACE.FIR", "FIR", "My view", {"new": True}, {}, "",
                                 catalog_id="aviation")
    repository.upsert(replacement)
    assert len(repository.list_all()) == 1
    assert repository.list_all()[0].id == original.id
    assert repository.list_all()[0].filter_state == {"new": True}


def test_saved_view_load_uses_current_database_connector(catalog):
    plugin = catalog.plugin
    catalog.connector.get_layers.return_value = [definition("prod")]
    plugin._catalog_rows()
    repository = plugin._saved_layer_view_repository
    view = SavedLayerView("dev", "AIRSPACE.FIR", "FIR", "My view", {}, {}, "")
    repository.upsert(view)
    plugin._find_saved_view_layer = Mock(return_value=None)
    plugin._deserialize_layer_filter = Mock(return_value=object())
    plugin._apply_layer_filter = Mock()
    plugin._apply_layer_style = Mock()
    plugin._apply_saved_layer_view(view.id)
    loaded_definition, connector = plugin._loader_service.load_layer.call_args.args
    assert loaded_definition.datasource_id == "prod"
    assert connector is catalog.connector
    assert catalog.datasource_service.get_connector.call_args.args[0].id == "prod"


def test_profile_layer_selection_keeps_configured_but_undiscovered_ids(monkeypatch):
    from geodata_catalog.ui import profile_dialog as module

    scoped = SimpleNamespace(
        ItemDataRole=SimpleNamespace(UserRole=256),
        CheckState=SimpleNamespace(Checked=2, Unchecked=0),
    )
    monkeypatch.setattr(module, "Qt", scoped)
    dialog = module.ProfileDialog.__new__(module.ProfileDialog)
    dialog.profiles = [UserProfile("u", "User", visible_layer_ids=["missing:layer", "known:old"])]
    dialog._editing_id = "u"
    dialog._known_layer_ids = {"known:old", "known:new"}
    dialog.name_edit = Mock()
    dialog.name_edit.text.return_value = "Named user"
    dialog.all_layers = Mock()
    dialog.all_layers.isChecked.return_value = False
    checked = Mock()
    checked.checkState.return_value = 2
    checked.data.return_value = "known:new"
    unchecked = Mock()
    unchecked.checkState.return_value = 0
    dialog.layers_list = Mock()
    dialog.layers_list.count.return_value = 2
    dialog.layers_list.item.side_effect = [checked, unchecked]
    dialog._store_current()
    assert dialog.profiles[0].name == "Named user"
    assert dialog.profiles[0].visible_layer_ids == ["known:new", "missing:layer"]
    dialog.all_layers.isChecked.return_value = True
    dialog._store_current()
    assert dialog.profiles[0].visible_layer_ids is None


@pytest.mark.parametrize("all_selected", [False, True])
@pytest.mark.parametrize("qt", [
    SimpleNamespace(
        ItemDataRole=SimpleNamespace(UserRole=256),
        CheckState=SimpleNamespace(Checked=2, Unchecked=0),
    ),
    SimpleNamespace(UserRole=256, Checked=2, Unchecked=0),
])
def test_uncheck_all_clears_current_profile_including_unlisted_layers(monkeypatch, all_selected, qt):
    from geodata_catalog.ui import profile_dialog as module

    monkeypatch.setattr(module, "Qt", qt)
    dialog = module.ProfileDialog.__new__(module.ProfileDialog)
    profile = UserProfile("u", "User", visible_layer_ids=(
        None if all_selected else ["known:layer", "missing:layer"]
    ))
    other = UserProfile("other", "Other", visible_layer_ids=["other:layer"])
    dialog.profiles = [profile, other]
    dialog._editing_id = "u"
    dialog._known_layer_ids = {"known:layer"}
    dialog.name_edit = Mock()
    dialog.name_edit.text.return_value = "User"
    dialog.all_layers = Mock()
    dialog.all_layers.isChecked.return_value = all_selected
    dialog.all_layers.setChecked.side_effect = lambda value: setattr(
        dialog.all_layers.isChecked, "return_value", value
    )
    item = Mock()
    item.data.return_value = "known:layer"
    item.checkState.return_value = 2
    item.setCheckState.side_effect = lambda value: setattr(item.checkState, "return_value", value)
    dialog.layers_list = Mock()
    dialog.layers_list.count.return_value = 1
    dialog.layers_list.item.return_value = item

    dialog._uncheck_all()
    dialog._store_current()

    dialog.all_layers.setChecked.assert_called_once_with(False)
    item.setCheckState.assert_called_once_with(0)
    assert profile.visible_layer_ids == []
    assert other.visible_layer_ids == ["other:layer"]


def test_unavailable_layer_row_remains_selectable_with_visible_status(catalog, monkeypatch):
    from geodata_catalog.ui import loadable_layers_dock as module

    catalog.configs.save(LayerConfig("dev", "AIRSPACE.FIR"))
    rows = catalog.plugin._catalog_rows()
    items = []

    def tree_item(*args):
        item = Mock()
        text = args[-1][0]
        item.text.return_value = text
        items.append(item)
        return item

    monkeypatch.setattr(module, "QTreeWidgetItem", tree_item)
    monkeypatch.setattr(module, "QIcon", Mock())
    monkeypatch.setattr(module, "QColor", Mock())
    dock = module.LoadableLayersDockWidget.__new__(module.LoadableLayersDockWidget)
    dock.layers_tree = Mock()
    dock.layers_tree.topLevelItemCount.return_value = 1
    dock._theme_category_text = "#000000"
    dock._highlighted_identity = None
    dock._datasource_icon = Mock()
    dock._layer_icon = Mock(return_value=None)
    dock._right_alignment = Mock(return_value=0)
    dock._populate_presets = Mock()
    dock._show_layer_details = Mock()
    dock._apply_filter = Mock()
    dock.filter_edit = Mock()
    dock.set_rows(rows, set(), "#2777B5")
    layer_item = items[1]
    assert "Not available" in layer_item.setText.call_args.args[1]
    assert "not found or not accessible" in layer_item.setToolTip.call_args.args[1]
    layer_item.setDisabled.assert_not_called()


def test_unavailable_saved_view_selection_does_not_enable_loading(catalog):
    plugin = catalog.plugin
    catalog.configs.save(LayerConfig("dev", "AIRSPACE.FIR"))
    rows = plugin._catalog_rows()
    view = SavedLayerView("prod", "AIRSPACE.FIR", "FIR", "My view", {}, {}, "")
    dock = LoadableLayersDockWidget.__new__(LoadableLayersDockWidget)
    dock._saved_views = [view]
    dock._rows = rows
    dock._select_tree_layer = Mock()
    dock._show_layer_details = Mock()
    dock._select_saved_view(view.id)
    assert dock._detail_layer is rows[0]["layer"]
    assert not dock._detail_loadable


@pytest.mark.parametrize("role", ["user", "developer"])
def test_default_load_retains_loader_pipeline_and_only_developer_updates_catalog(catalog, role):
    plugin = catalog.plugin
    plugin._active_profile = UserProfile("p", "Profile", role)
    plugin._loaded_layer_keys = set()
    plugin._loadable_layers_dock = None
    plugin._layer_toolbox_service = Mock()
    plugin._geometry_type_from_qgis_layer = Mock(return_value="POLYGON")
    catalog.connector.get_layers.return_value = [definition("prod")]
    plugin._catalog_rows()
    plugin._on_load_layer("prod", "AIRSPACE.FIR")
    layer, connector = plugin._loader_service.load_layer.call_args.args
    assert layer.datasource_id == "prod"
    assert connector is catalog.connector
    plugin._layer_toolbox_service.ensure_default_basemap_for_empty_project.assert_called_once()
    assert plugin._loaded_layer_keys == {"prod:AIRSPACE.FIR"}
    assert bool(catalog.layers.list_all()) == (role == "developer")


def test_profile_assignment_keeps_layer_metadata_if_source_disappears(catalog, monkeypatch):
    plugin = catalog.plugin
    plugin.iface = Mock()
    plugin._profiles = [
        UserProfile("dev-profile", "Developer", "developer"),
        UserProfile("user", "User", visible_layer_ids=["aviation:AIRSPACE.FIR"]),
    ]
    plugin._active_profile = plugin._profiles[0]
    plugin._profile_repository = ProfileRepository(catalog.settings)
    plugin._accepted_code = Mock(return_value=1)
    plugin._run_dialog = Mock(return_value=1)
    plugin._update_profile_ui = Mock()
    plugin._refresh_connection_views = Mock()
    catalog.connector.get_layers.side_effect = lambda **kwargs: [definition("prod")]
    monkeypatch.setattr(plugin_module, "ProfileDialog", Mock(
        return_value=SimpleNamespace(profiles=plugin._profiles),
    ))
    plugin._manage_profiles()
    assert catalog.layers.list_by_datasource("aviation")[0].layer_name == "AIRSPACE.FIR"
    catalog.connector.get_layers.side_effect = None
    catalog.connector.get_layers.return_value = []
    plugin._active_profile = plugin._profiles[1]
    rows = plugin._catalog_rows()
    assert rows[0]["layer"].display_name == "FIR"
    assert not rows[0]["loadable"]


def test_legacy_configuration_accessors_resolve_shared_display_only_layers(catalog):
    catalog.configs.save(LayerConfig("aviation", "AIRSPACE.FIR", layername="Flight regions"))
    layer = catalog.service.get_layer_configuration("prod", "AIRSPACE.FIR")
    assert layer.display_name == "Flight regions"
    assert layer.datasource_id == "prod"
    assert catalog.service.list_configured_layers("prod")[0].display_name == "Flight regions"


def test_layer_configuration_write_failure_is_reported(tmp_path, monkeypatch):
    from pathlib import Path

    repository = LayerConfigRepository(tmp_path / "layer_config.json")

    def fail_write(*args, **kwargs):
        raise PermissionError("Read-only configuration")

    monkeypatch.setattr(Path, "write_text", fail_write)
    with pytest.raises(ConfigurationException, match="Failed to write layer configuration"):
        repository.save(LayerConfig("aviation", "AIRSPACE.FIR"))


def test_unavailable_layer_details_show_reason_and_disable_load(catalog, monkeypatch):
    from geodata_catalog.ui import loadable_layers_dock as module

    catalog.configs.save(LayerConfig("dev", "AIRSPACE.FIR"))
    rows = catalog.plugin._catalog_rows()
    label = Mock()
    monkeypatch.setattr(module, "QLabel", label)
    dock = module.LoadableLayersDockWidget.__new__(module.LoadableLayersDockWidget)
    dock._rows = rows
    dock._detail_loadable = False
    dock._selected_saved_view_id = ""
    dock.detail_title = Mock()
    dock.load_button = Mock()
    dock.detail_form = Mock()
    dock.detail_form.rowCount.return_value = 0
    dock._populate_presets = Mock()
    dock._show_layer_details(rows[0]["layer"])
    label.assert_any_call(rows[0]["availability_reason"])
    dock.load_button.setEnabled.assert_called_once_with(False)
    dock.load_button.setToolTip.assert_called_with(rows[0]["availability_reason"])
