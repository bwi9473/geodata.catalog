from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from geodata_catalog import plugin as plugin_module
from geodata_catalog.exceptions import DatasourceConnectionException
from geodata_catalog.models.datasource import Datasource, DatasourceType
from geodata_catalog.models.user_profile import UserProfile
from geodata_catalog.plugin import GeoDataCatalogPlugin
from geodata_catalog.ui import geometry_toolbar as toolbar_module
from geodata_catalog.ui.geometry_toolbar import GeometryToolbar, _enum, contrasting_text_color


def database():
    return Datasource("db", "Development database", DatasourceType.ORACLE, {
        "host": "oracle.example.com", "service_name": "BETA3",
        "environment": "Development", "environment_color": "#59A947",
    })


def test_toolbar_shows_connection_and_resets_color_and_actions(monkeypatch):
    monkeypatch.setattr(toolbar_module, "QColor", lambda color: SimpleNamespace(name=lambda: color))
    toolbar = GeometryToolbar(Mock(), Mock())
    toolbar._toolbar = Mock()
    toolbar._connection_label = Mock()
    toolbar._connect_action = Mock()
    toolbar._disconnect_action = Mock()
    toolbar.set_database_connection("user@BETA3 - Development", "#59A947", "oracle.example.com:1521/BETA3")
    toolbar._connection_label.setText.assert_called_with("user@BETA3 - Development")
    toolbar._connection_label.setToolTip.assert_called_with("oracle.example.com:1521/BETA3")
    assert "#59A947" in toolbar._toolbar.setStyleSheet.call_args.args[0]
    toolbar._connect_action.setEnabled.assert_called_with(False)
    toolbar._disconnect_action.setEnabled.assert_called_with(True)
    toolbar.set_database_connection()
    toolbar._connection_label.setText.assert_called_with("Database disconnected")
    assert "#F8FBFF" in toolbar._toolbar.setStyleSheet.call_args.args[0]
    toolbar._connect_action.setEnabled.assert_called_with(True)
    toolbar._disconnect_action.setEnabled.assert_called_with(False)


@pytest.mark.parametrize(("color", "expected"), [
    ("#59A947", "#202020"), ("#C62828", "#FFFFFF"),
    ("#FFFFFF", "#202020"), ("#000000", "#FFFFFF"),
])
def test_environment_color_has_readable_text(color, expected):
    assert contrasting_text_color(color) == expected


def test_qt6_scoped_dialog_and_enum_compatibility():
    scoped = SimpleNamespace(EchoMode=SimpleNamespace(Password=2))
    assert _enum(scoped, "EchoMode", "Password") == 2
    assert _enum(SimpleNamespace(Password=2), "EchoMode", "Password") == 2
    dialog = SimpleNamespace(DialogCode=SimpleNamespace(Accepted=1), exec=Mock(return_value=1))
    assert GeoDataCatalogPlugin._run_dialog(dialog) == GeoDataCatalogPlugin._accepted_code(dialog)


@pytest.fixture
def connection_plugin(monkeypatch):
    source = database()
    layer = Mock()
    layer.customProperty.return_value = "db"
    layer.isEditable.return_value = False
    layer.id.return_value = "database-layer"
    other_layer = Mock()
    other_layer.customProperty.return_value = "file"
    project = Mock()
    project.mapLayers.return_value = {"db-layer": layer, "file-layer": other_layer}
    monkeypatch.setattr(plugin_module, "QgsProject", SimpleNamespace(instance=lambda: project))
    question = Mock(return_value=1)
    monkeypatch.setattr(plugin_module, "QMessageBox", SimpleNamespace(question=question))
    plugin = GeoDataCatalogPlugin.__new__(GeoDataCatalogPlugin)
    plugin._active_profile = UserProfile("developer", "Developer", "developer")
    plugin._profile_actions = []
    plugin._database_session = SimpleNamespace(
        datasource=source, username="user", disconnect=Mock(),
        is_connected=lambda candidate: candidate.id == "db",
        initialize=Mock(), saved_credentials=Mock(), forget_credentials=Mock(),
    )
    plugin._datasource_service = Mock()
    plugin._datasource_service.list_datasources.return_value = [source]
    plugin._layer_cache = {"db": {"layer": object()}, "file": {}}
    plugin._loaded_layer_keys = {"db:AIRSPACE.FIR", "file:airports"}
    plugin._custom_view_docks = [SimpleNamespace(_layer=layer, close=Mock())]
    plugin._unloading = False
    plugin.iface = Mock()
    plugin._show_error = Mock()
    plugin._update_database_connection_ui = Mock()
    plugin._refresh_connection_views = Mock()
    plugin._messagebox_yes_button = lambda: 1
    plugin._messagebox_no_button = lambda: 2
    return plugin, project, layer, question


def test_disconnect_removes_only_matching_database_layers(connection_plugin):
    plugin, project, _, question = connection_plugin
    assert plugin._disconnect_database()
    question.assert_called_once()
    plugin._custom_view_docks[0].close.assert_called_once()
    project.removeMapLayers.assert_called_once_with(["database-layer"])
    plugin._database_session.disconnect.assert_called_once()
    assert plugin._loaded_layer_keys == {"file:airports"}
    assert plugin._layer_cache == {}
    plugin._refresh_connection_views.assert_called_once()


def test_cancel_disconnect_keeps_layers_and_session(connection_plugin):
    plugin, project, _, question = connection_plugin
    question.return_value = 2
    assert not plugin._disconnect_database()
    project.removeMapLayers.assert_not_called()
    plugin._database_session.disconnect.assert_not_called()


def test_disconnect_refuses_to_discard_pending_edits(connection_plugin):
    plugin, project, layer, _ = connection_plugin
    layer.isEditable.return_value = True
    assert not plugin._disconnect_database()
    plugin._show_error.assert_called_once()
    project.removeMapLayers.assert_not_called()


def test_saved_project_layers_receive_new_authcfg_without_credentials(connection_plugin, monkeypatch):
    import qgis.core

    plugin, _, layer, _ = connection_plugin
    plugin._database_session.connector_config = Mock(return_value={
        **database().config, "authcfg": "new1234",
    })
    uri = Mock()
    uri.uri.return_value = "authcfg=new1234 table=AIRSPACE.FIR"
    monkeypatch.setattr(qgis.core, "QgsDataSourceUri", Mock(return_value=uri), raising=False)
    layer.providerType.return_value = "oracle"
    layer.name.return_value = "FIR"
    layer.isValid.return_value = True
    layer.customProperty.side_effect = lambda key, default: {
        "geodata_catalog/datasource_id": "db",
        "geodata_catalog/source_layer_name": "AIRSPACE.FIR",
    }.get(key, default)
    plugin._restore_database_project_layers()
    uri.setConnection.assert_called_once_with("oracle.example.com", "1521", "BETA3", "", "")
    uri.setAuthConfigId.assert_called_once_with("new1234")
    uri.uri.assert_called_once_with(False)
    layer.setDataSource.assert_called_once_with("authcfg=new1234 table=AIRSPACE.FIR", "FIR", "oracle")


def test_theme_override_uses_database_environment_color(connection_plugin):
    plugin, _, _, _ = connection_plugin
    plugin._system_configuration_repository = Mock()
    plugin._system_configuration_repository.load_ui_colors.return_value = {
        "primary": "#123456", "primary_text": "#FFFFFF", "text": "#202020",
    }
    colors = plugin._load_ui_colors()
    assert colors["primary"] == "#59A947"
    assert colors["primary_text"] == "#202020"
    plugin._database_session.datasource = None
    assert plugin._load_ui_colors()["primary"] == "#123456"


@pytest.mark.parametrize("accepted", [False, True])
def test_login_dialog_is_cleared_on_success_or_cancel(connection_plugin, monkeypatch, accepted):
    from geodata_catalog.ui import database_login_dialog

    plugin, _, _, _ = connection_plugin
    plugin._database_session.datasource = None
    plugin._database_session.connect = Mock()
    plugin._restore_database_project_layers = Mock()
    plugin._accepted_code = lambda dialog: 1
    plugin._run_dialog = Mock(return_value=int(accepted))
    dialog = Mock()
    dialog.credentials.return_value = (database(), "user", "transient-secret")
    dialog.remember_password.return_value = False
    monkeypatch.setattr(database_login_dialog, "DatabaseLoginDialog", Mock(return_value=dialog))
    plugin._connect_database()
    if accepted:
        plugin._database_session.connect.assert_called_once_with(
            database(), "user", "transient-secret", remember=False,
        )
        plugin._restore_database_project_layers.assert_called_once()
    else:
        plugin._database_session.connect.assert_not_called()
    dialog.clear_password.assert_called_once()
    dialog.deleteLater.assert_called_once()


def test_failed_login_offers_retry_without_enabling_database_ui(connection_plugin, monkeypatch):
    from geodata_catalog.ui import database_login_dialog

    plugin, _, _, _ = connection_plugin
    plugin._database_session.datasource = None
    plugin._database_session.connect = Mock(side_effect=DatasourceConnectionException("Login failed"))
    plugin._accepted_code = lambda dialog: 1
    plugin._run_dialog = Mock(side_effect=[1, 0])
    dialog = Mock()
    dialog.credentials.return_value = (database(), "user", "wrong-secret")
    monkeypatch.setattr(database_login_dialog, "DatabaseLoginDialog", Mock(return_value=dialog))
    plugin._connect_database()
    plugin._show_error.assert_called_once_with("Database login", "Login failed")
    plugin._update_database_connection_ui.assert_not_called()
    assert dialog.clear_password.call_count == 2


def test_startup_never_prompts_or_accesses_authentication_even_with_database(connection_plugin, monkeypatch):
    plugin, _, _, _ = connection_plugin
    plugin._geometry_toolbar = Mock()
    plugin._ensure_layer_panel_filter_action = Mock()
    plugin._logger = Mock()
    plugin._connect_database = Mock()
    monkeypatch.setattr(plugin_module, "QAction", Mock())
    plugin.initGui()
    plugin._connect_database.assert_not_called()
    plugin._database_session.initialize.assert_not_called()
    plugin._database_session.saved_credentials.assert_not_called()


def test_unload_never_discards_edits_when_disconnect_was_cancelled(connection_plugin):
    plugin, project, _, question = connection_plugin
    question.return_value = 2
    plugin._geometry_toolbar = Mock()
    plugin._dock_widget = None
    plugin._loadable_layers_dock = None
    plugin._open_catalog_action = None
    plugin._logger = Mock()
    plugin.unload()
    project.removeMapLayers.assert_not_called()
    plugin._database_session.disconnect.assert_called_once()
    plugin._show_error.assert_called_once()


def test_connect_passes_remember_choice_only_after_manual_request(connection_plugin, monkeypatch):
    from geodata_catalog.ui import database_login_dialog

    plugin, _, _, _ = connection_plugin
    plugin._database_session.datasource = None
    plugin._database_session.connect = Mock()
    plugin._restore_database_project_layers = Mock()
    plugin._accepted_code = lambda dialog: 1
    plugin._run_dialog = Mock(return_value=1)
    dialog = Mock()
    dialog.credentials.return_value = (database(), "user", "saved-secret")
    dialog.remember_password.return_value = True
    monkeypatch.setattr(database_login_dialog, "DatabaseLoginDialog", Mock(return_value=dialog))
    plugin._connect_database()
    plugin._database_session.initialize.assert_called_once()
    plugin._database_session.connect.assert_called_once_with(
        database(), "user", "saved-secret", remember=True,
    )


@pytest.fixture
def login_dialog():
    from geodata_catalog.ui.database_login_dialog import DatabaseLoginDialog

    dialog = DatabaseLoginDialog.__new__(DatabaseLoginDialog)
    dialog._database = Mock()
    dialog._database.currentData.return_value = database()
    dialog._username = Mock()
    dialog._password = Mock()
    dialog._remember = Mock()
    dialog._saved_credentials = Mock(return_value=None)
    dialog._forget_credentials = Mock()
    return dialog


def test_login_dialog_fills_saved_credentials_and_checks_remember(login_dialog):
    login_dialog._saved_credentials.return_value = ("remembered_user", "saved-secret")
    login_dialog._on_database_changed()
    login_dialog._username.setText.assert_called_with("remembered_user")
    login_dialog._password.setText.assert_called_once_with("saved-secret")
    login_dialog._remember.setChecked.assert_called_with(True)


def test_database_switch_clears_previous_password_and_remember_choice(login_dialog):
    login_dialog._on_database_changed()
    login_dialog._password.clear.assert_called_once()
    login_dialog._password.setText.assert_not_called()
    login_dialog._remember.setChecked.assert_called_once_with(False)


def test_forget_button_removes_saved_record_and_clears_password(login_dialog):
    login_dialog._on_forget_credentials()
    login_dialog._forget_credentials.assert_called_once_with(database())
    login_dialog._password.clear.assert_called_once()
    login_dialog._remember.setChecked.assert_called_once_with(False)


def test_saved_password_unlock_failure_is_shown_and_does_not_fill_password(login_dialog, monkeypatch):
    from geodata_catalog.ui import database_login_dialog

    warning = Mock()
    monkeypatch.setattr(database_login_dialog, "QMessageBox", SimpleNamespace(warning=warning))
    login_dialog._saved_credentials.side_effect = DatasourceConnectionException("Unlock cancelled")
    login_dialog._on_database_changed()
    warning.assert_called_once()
    login_dialog._password.setText.assert_not_called()
