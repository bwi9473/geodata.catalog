import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import qgis.core

from geodata_catalog.connectors import oracle_connector as oracle_module
from geodata_catalog.exceptions import ConfigurationException, DatasourceConnectionException
from geodata_catalog.metadata.datasource_repository import DatasourceRepository
from geodata_catalog.metadata.settings_manager import SettingsManager
from geodata_catalog.models.datasource import Datasource, DatasourceType
from geodata_catalog.services.database_session_service import (
    DatabaseSessionService, QgisSessionAuthentication, validate_database_config,
)
from geodata_catalog.services.datasource_service import DatasourceService


class MemorySettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


def source(source_id="db", **config):
    return Datasource(
        source_id, source_id, DatasourceType.ORACLE,
        {"host": "oracle.example.com", "service_name": "BETA3", **config},
    )


@pytest.fixture
def session(monkeypatch):
    backend = Mock(spec=QgisSessionAuthentication)
    backend.store.return_value = "abc1234"
    login = Mock(return_value=True)
    monkeypatch.setattr(oracle_module.OracleConnector, "test_connection", login)
    return DatabaseSessionService(backend), backend, login


def test_requires_login_and_shares_session_across_schemas(session):
    service, backend, login = session
    with pytest.raises(DatasourceConnectionException, match="disconnected"):
        service.connector_config(source())
    service.connect(source(schema="AIRSPACE"), " gis_user ", "not-persisted")
    other_schema = source("navigation", host="ORACLE.EXAMPLE.COM", schema="NAVIGATION")
    assert service.is_connected(other_schema)
    assert service.connector_config(other_schema) == {
        **other_schema.config, "authcfg": "abc1234",
    }
    assert service.username == "gis_user"
    assert "not-persisted" not in repr(vars(service))
    backend.store.assert_called_once_with("gis_user", "not-persisted")
    service.connector_config(other_schema)
    login.assert_called_once()
    for other in (source(service_name="PROD"), source(port=1522), source(host="other")):
        with pytest.raises(DatasourceConnectionException):
            service.connector_config(other)
    service.disconnect()
    assert service.datasource is None
    assert service.username == ""
    assert not service.is_connected(other_schema)


def test_login_failure_does_not_create_session(session):
    service, backend, login = session
    login.side_effect = DatasourceConnectionException("Login failed")
    with pytest.raises(DatasourceConnectionException):
        service.connect(source(), "user", "secret")
    backend.store.assert_not_called()
    assert service.datasource is None


def test_encryption_failure_does_not_create_session(session):
    service, backend, _ = session
    backend.store.side_effect = DatasourceConnectionException("Master password cancelled")
    with pytest.raises(DatasourceConnectionException):
        service.connect(source(), "user", "secret")
    assert service.datasource is None


def test_cleanup_failure_is_reported_and_not_disguised_as_disconnected(session):
    service, backend, _ = session
    service.connect(source(), "user", "secret")
    backend.cleanup.side_effect = DatasourceConnectionException("Cleanup failed")
    with pytest.raises(DatasourceConnectionException):
        service.disconnect()
    assert service.is_connected(source())


@pytest.mark.parametrize("config", [
    {"host": ""}, {"service_name": ""}, {"port": "wrong"}, {"port": 65536},
    {"password": "secret"}, {"authcfg": "stored"}, {"environment_color": "green"},
    {"environment_color": "#123456; color: red"},
])
def test_invalid_database_configuration_is_rejected(config):
    with pytest.raises(ConfigurationException):
        validate_database_config(source(**config).config)


def test_disabled_datasources_cannot_log_in(session):
    service, backend, login = session
    disabled = source()
    disabled.enabled = False
    with pytest.raises(ConfigurationException, match="enabled"):
        service.connect(disabled, "user", "secret")
    login.assert_not_called()
    backend.store.assert_not_called()


def test_datasource_service_uses_session_for_every_connector(session):
    db_session, _, login = session
    repository = DatasourceRepository(SettingsManager(settings=MemorySettings()))
    service = DatasourceService(repository, Mock())
    service.database_session = db_session
    db_source = source()
    repository.upsert(db_source)
    with pytest.raises(DatasourceConnectionException):
        service.get_connector(db_source)
    db_session.connect(db_source, "user", "secret")
    for _ in range(3):
        connector = service.get_connector(db_source)
        assert connector._config["authcfg"] == "abc1234"
        assert "password" not in connector._config
    login.assert_called_once()
    db_session.disconnect()
    with pytest.raises(DatasourceConnectionException):
        service.get_connector(db_source)
    assert "secret" not in json.dumps(repository._settings_manager._settings.values)


def test_plaintext_migration_cleans_file_and_qsettings(tmp_path):
    settings = MemorySettings()
    payload = {
        "datasources": [source(password="file-secret").to_dict()],
        "layers": [{"provider_key": "oracle", "provider_uri": "password=uri-secret"}],
    }
    settings.setValue("GeoDataCatalog/datasources", json.dumps([
        source(password="registry-secret").to_dict(),
    ]))
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    manager = SettingsManager(settings=settings, storage_file_path=str(path))
    assert "password" not in manager.get_json("datasources", [])[0]["config"]
    assert manager.get_json("layers", [])[0]["provider_uri"] == ""
    for secret in ("file-secret", "registry-secret", "uri-secret"):
        assert secret not in path.read_text(encoding="utf-8")
        assert secret not in json.dumps(settings.values)
    manager.set_json("datasources", [source(password="new-secret").to_dict()])
    assert "new-secret" not in path.read_text(encoding="utf-8")
    assert "new-secret" not in json.dumps(settings.values)


def test_qsettings_only_migration_never_copies_password_to_file(tmp_path):
    settings = MemorySettings()
    settings.setValue(
        "GeoDataCatalog/datasources", json.dumps([source(password="legacy-secret").to_dict()]),
    )
    path = tmp_path / "config.json"
    SettingsManager(settings=settings, storage_file_path=str(path))
    assert "legacy-secret" not in path.read_text(encoding="utf-8")
    assert "legacy-secret" not in json.dumps(settings.values)


def test_oracle_provider_uri_contains_only_auth_reference(monkeypatch):
    uri = Mock()
    uri.uri.return_value = "authcfg=abc1234"
    monkeypatch.setattr(oracle_module, "QgsDataSourceUri", lambda: uri)
    connector = oracle_module.OracleConnector("db", {
        **source().config, "authcfg": "abc1234",
    })
    assert connector._build_layer_uri("AIRSPACE", "FIR", "SHAPE", "ID") == "authcfg=abc1234"
    uri.setConnection.assert_called_once_with("oracle.example.com", "1521", "BETA3", "", "")
    uri.setAuthConfigId.assert_called_once_with("abc1234")
    uri.uri.assert_called_once_with(False)


def test_oracle_discovery_resolves_encrypted_credentials(monkeypatch):
    auth = Mock()
    auth.config.side_effect = {"username": "gis_user", "password": "runtime-secret"}.__getitem__
    manager = Mock()
    manager.loadAuthenticationConfig.return_value = True
    monkeypatch.setattr(qgis.core, "QgsApplication", SimpleNamespace(authManager=lambda: manager), raising=False)
    monkeypatch.setattr(qgis.core, "QgsAuthMethodConfig", lambda: auth, raising=False)
    driver = Mock()
    monkeypatch.setattr(oracle_module, "oracledb", driver)
    connector = oracle_module.OracleConnector("db", {**source().config, "authcfg": "abc1234"})
    connector._connect()
    driver.connect.assert_called_once_with(
        user="gis_user", password="runtime-secret", dsn=driver.makedsn.return_value,
    )
    assert "password" not in connector._config


def test_temporary_qgis_auth_record_is_tracked_and_cleaned(monkeypatch):
    settings = SettingsManager(settings=MemorySettings())
    manager = Mock()
    manager.availableAuthMethodConfigs.return_value = {"abc1234": object()}
    manager.removeAuthenticationConfig.return_value = True
    config = Mock()
    config.id.return_value = "abc1234"
    monkeypatch.setattr(qgis.core, "QgsAuthMethodConfig", lambda: config, raising=False)
    monkeypatch.setattr(
        qgis.core, "QgsProviderRegistry", SimpleNamespace(instance=lambda: Mock()), raising=False,
    )
    backend = QgisSessionAuthentication(settings)
    monkeypatch.setattr(backend, "_manager", lambda: manager)
    assert backend.store("user", "encrypted-secret") == "abc1234"
    assert settings.get_json(backend.SETTINGS_KEY, []) == ["abc1234"]
    assert "encrypted-secret" not in json.dumps(settings._settings.values)
    backend.cleanup()
    manager.clearCachedConfig.assert_called_once_with("abc1234")
    manager.removeAuthenticationConfig.assert_called_once_with("abc1234")
    assert settings.get_json(backend.SETTINGS_KEY, []) == []


def test_expired_authentication_does_not_fall_back_to_saved_password(monkeypatch):
    manager = Mock()
    manager.loadAuthenticationConfig.return_value = False
    monkeypatch.setattr(qgis.core, "QgsApplication", SimpleNamespace(authManager=lambda: manager), raising=False)
    monkeypatch.setattr(qgis.core, "QgsAuthMethodConfig", Mock(), raising=False)
    driver = Mock()
    monkeypatch.setattr(oracle_module, "oracledb", driver)
    connector = oracle_module.OracleConnector("db", {
        **source().config, "authcfg": "expired", "password": "must-not-be-used",
    })
    with pytest.raises(DatasourceConnectionException, match="Reconnect"):
        connector._connect()
    driver.connect.assert_not_called()


def test_oracle_connection_error_redacts_encrypted_session_password(monkeypatch):
    auth = Mock()
    auth.config.side_effect = {"username": "gis_user", "password": "runtime-secret"}.__getitem__
    manager = Mock()
    manager.loadAuthenticationConfig.return_value = True
    monkeypatch.setattr(qgis.core, "QgsApplication", SimpleNamespace(authManager=lambda: manager), raising=False)
    monkeypatch.setattr(qgis.core, "QgsAuthMethodConfig", lambda: auth, raising=False)
    driver = Mock()
    driver.connect.side_effect = RuntimeError("ORA-01017: invalid login: runtime-secret")
    monkeypatch.setattr(oracle_module, "oracledb", driver)
    connector = oracle_module.OracleConnector("db", {
        **source().config, "authcfg": "abc1234",
    })

    with pytest.raises(DatasourceConnectionException) as caught:
        connector._connect()

    assert "ORA-01017" in str(caught.value)
    assert "[REDACTED]" in str(caught.value)
    assert "runtime-secret" not in str(caught.value)


def test_layer_loading_never_logs_a_provider_uri():
    from geodata_catalog.models.layer_definition import LayerDefinition
    from geodata_catalog.services.qgis_loader_service import QgisLoaderService

    logger = Mock()
    loader = QgisLoaderService(Mock(), logger, project=Mock())
    connector = Mock()
    connector.load_layer.return_value.isValid.return_value = True
    layer = LayerDefinition("db", "AIRSPACE.FIR", "FIR", "oracle", "password=uri-secret")
    loader.load_layer(layer, connector)
    assert "uri-secret" not in str(logger.info.call_args_list)


def test_remembering_is_opt_in_and_not_used_as_layer_authentication(session):
    service, backend, login = session
    service.connect(source(), "user", "remembered-secret", remember=True)
    backend.remember_credentials.assert_called_once_with(source(), "user", "remembered-secret")
    backend.forget_credentials.assert_not_called()
    assert service.connector_config(source())["authcfg"] == "abc1234"
    service.disconnect()
    backend.forget_credentials.assert_not_called()
    with pytest.raises(DatasourceConnectionException):
        service.connector_config(source())
    login.assert_called_once()


def test_unchecking_remember_removes_previous_saved_login_after_validation(session):
    service, backend, _ = session
    service.connect(source(), "user", "temporary-secret", remember=False)
    backend.forget_credentials.assert_called_once_with(source())
    backend.remember_credentials.assert_not_called()


def test_failed_login_does_not_overwrite_remembered_credentials(session):
    service, backend, login = session
    login.side_effect = DatasourceConnectionException("Invalid password")
    with pytest.raises(DatasourceConnectionException):
        service.connect(source(), "user", "wrong-secret", remember=True)
    backend.remember_credentials.assert_not_called()
    backend.forget_credentials.assert_not_called()


def test_remember_failure_cleans_temporary_login_without_activating_session(session):
    service, backend, _ = session
    backend.remember_credentials.side_effect = DatasourceConnectionException("Storage failed")
    with pytest.raises(DatasourceConnectionException, match="Storage failed"):
        service.connect(source(), "user", "secret", remember=True)
    assert service.datasource is None
    assert backend.cleanup.call_count == 2


@pytest.fixture
def encrypted_backend(monkeypatch):
    records = {}

    class Config:
        def __init__(self):
            self.values = {}
            self.identifier = ""

        def setName(self, name):
            self.name = name

        def setMethod(self, method):
            self.method = method

        def setConfig(self, key, value):
            self.values[key] = value

        def config(self, key):
            return self.values[key]

        def id(self):
            return self.identifier

    def store(config):
        config.identifier = f"auth{len(records) + 1}"
        records[config.identifier] = dict(config.values)
        return True

    def load(auth_id, config, full):
        config.values = dict(records[auth_id])
        return True

    def remove(auth_id):
        del records[auth_id]
        return True

    manager = Mock()
    manager.storeAuthenticationConfig.side_effect = store
    manager.loadAuthenticationConfig.side_effect = load
    manager.removeAuthenticationConfig.side_effect = remove
    manager.availableAuthMethodConfigs.side_effect = lambda: dict(records)
    settings = SettingsManager(settings=MemorySettings())
    backend = QgisSessionAuthentication(settings)
    monkeypatch.setattr(backend, "_manager", lambda: manager)
    monkeypatch.setattr(qgis.core, "QgsAuthMethodConfig", Config, raising=False)
    monkeypatch.setattr(
        qgis.core, "QgsProviderRegistry", SimpleNamespace(instance=lambda: Mock()), raising=False,
    )
    return backend, records, settings, manager


def test_remembered_login_survives_session_cleanup_and_is_shared_only_on_same_endpoint(encrypted_backend):
    backend, records, settings, _ = encrypted_backend
    backend.remember_credentials(source(), "user", "saved-secret")
    saved_id = next(iter(records))
    temporary_id = backend.store("user", "saved-secret")
    assert saved_id != temporary_id
    backend.cleanup()
    assert saved_id in records
    assert temporary_id not in records
    assert backend.saved_credentials(source("other-schema", schema="NAVIGATION")) == ("user", "saved-secret")
    for other in (source(service_name="PROD"), source(port=1522), source(host="other")):
        assert backend.saved_credentials(other) is None
    assert "saved-secret" not in json.dumps(settings._settings.values)
    backend.forget_credentials(source())
    assert records == {}
    assert backend.saved_credentials(source()) is None


def test_remembered_login_can_be_updated_without_leaving_old_record(encrypted_backend):
    backend, records, _, _ = encrypted_backend
    backend.remember_credentials(source(), "user", "old-secret")
    backend.remember_credentials(source(), "user", "new-secret")
    assert len(records) == 1
    assert backend.saved_credentials(source()) == ("user", "new-secret")


def test_saved_login_unlock_failure_is_explicit(encrypted_backend):
    backend, _, _, manager = encrypted_backend
    backend.remember_credentials(source(), "user", "saved-secret")
    manager.loadAuthenticationConfig.side_effect = None
    manager.loadAuthenticationConfig.return_value = False
    with pytest.raises(DatasourceConnectionException, match="unlock"):
        backend.saved_credentials(source())


def test_deleted_qgis_auth_record_clears_stale_reference(encrypted_backend):
    backend, records, settings, _ = encrypted_backend
    backend.remember_credentials(source(), "user", "saved-secret")
    records.clear()
    assert backend.saved_credentials(source()) is None
    assert settings.get_json(backend.SAVED_SETTINGS_KEY, {}) == {}
