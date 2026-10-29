from __future__ import annotations

import re
import json
from hashlib import sha256
from typing import Any

from geodata_catalog.connectors.oracle_connector import OracleConnector
from geodata_catalog.exceptions import ConfigurationException, DatasourceConnectionException
from geodata_catalog.models.datasource import Datasource, DatasourceType


def database_endpoint(datasource: Datasource) -> tuple[str, int, str]:
    config = datasource.config
    host = str(config.get("host", "")).strip()
    service = str(config.get("service_name", "")).strip()
    try:
        port = int(config.get("port", 1521))
    except (ValueError, TypeError) as exc:
        raise ConfigurationException("Database port must be an integer.") from exc
    if not host or not service or not 1 <= port <= 65535:
        raise ConfigurationException("Database host, service_name and a valid port are required.")
    return host.casefold(), port, service.casefold()


def validate_database_config(config: dict[str, Any]) -> None:
    database_endpoint(Datasource("", "", DatasourceType.ORACLE, config))
    color = config.get("environment_color", "#E7E7E7")
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ConfigurationException("environment_color must be a hexadecimal color such as #59A947.")
    if config.get("password") or config.get("authcfg"):
        raise ConfigurationException("Use Connect to log in; do not configure a password or authcfg.")


class QgisSessionAuthentication:
    """Separate temporary session records from opt-in remembered credentials."""

    SETTINGS_KEY = "database_session_auth_ids"
    SAVED_SETTINGS_KEY = "database_saved_auth_ids"

    def __init__(self, settings_manager) -> None:
        self._settings = settings_manager

    @staticmethod
    def _manager():
        from qgis.core import QgsApplication

        manager = QgsApplication.authManager()
        if manager is None or manager.isDisabled():
            raise DatasourceConnectionException("QGIS Authentication Manager is unavailable.")
        return manager

    def cleanup(self) -> None:
        ids = self._settings.get_json(self.SETTINGS_KEY, [])
        manager = self._manager() if ids else None
        for auth_id in list(ids):
            if auth_id in manager.availableAuthMethodConfigs():
                manager.clearCachedConfig(auth_id)
                if not manager.removeAuthenticationConfig(auth_id):
                    raise DatasourceConnectionException("Could not remove the temporary database login.")
            ids.remove(auth_id)
            self._settings.set_json(self.SETTINGS_KEY, ids)

    @staticmethod
    def _endpoint_key(datasource: Datasource) -> str:
        return sha256(json.dumps(database_endpoint(datasource)).encode("utf-8")).hexdigest()

    def saved_credentials(self, datasource: Datasource) -> tuple[str, str] | None:
        from qgis.core import QgsAuthMethodConfig

        saved = self._settings.get_json(self.SAVED_SETTINGS_KEY, {})
        auth_id = saved.get(self._endpoint_key(datasource))
        if not auth_id:
            return None
        manager = self._manager()
        if auth_id not in manager.availableAuthMethodConfigs():
            self.forget_credentials(datasource)
            return None
        config = QgsAuthMethodConfig()
        if not manager.loadAuthenticationConfig(auth_id, config, True):
            raise DatasourceConnectionException(
                "Could not unlock the saved database login. Unlock QGIS Authentication Manager "
                "or use Forget saved login to enter new credentials."
            )
        return config.config("username"), config.config("password")

    def forget_credentials(self, datasource: Datasource) -> None:
        saved = self._settings.get_json(self.SAVED_SETTINGS_KEY, {})
        key = self._endpoint_key(datasource)
        auth_id = saved.get(key)
        if auth_id:
            manager = self._manager()
            if auth_id in manager.availableAuthMethodConfigs():
                manager.clearCachedConfig(auth_id)
                if not manager.removeAuthenticationConfig(auth_id):
                    raise DatasourceConnectionException("Could not remove the saved database login.")
            saved.pop(key)
            self._settings.set_json(self.SAVED_SETTINGS_KEY, saved)

    def remember_credentials(self, datasource: Datasource, username: str, password: str) -> None:
        saved = self._settings.get_json(self.SAVED_SETTINGS_KEY, {})
        key = self._endpoint_key(datasource)
        old_id = saved.get(key)
        config = self._store_record(username, password, "GeoData Catalog remembered database login")
        saved[key] = config.id()
        self._track_record(config, self.SAVED_SETTINGS_KEY, saved)
        if old_id:
            manager = self._manager()
            if old_id in manager.availableAuthMethodConfigs():
                manager.clearCachedConfig(old_id)
                if not manager.removeAuthenticationConfig(old_id):
                    ids = self._settings.get_json(self.SETTINGS_KEY, [])
                    ids.append(old_id)
                    self._settings.set_json(self.SETTINGS_KEY, ids)
                    raise DatasourceConnectionException("Could not remove the previous saved database login.")

    def _store_record(self, username: str, password: str, name: str):
        from qgis.core import QgsAuthMethodConfig, QgsProviderRegistry

        if QgsProviderRegistry.instance().providerMetadata("oracle") is None:
            raise DatasourceConnectionException("The QGIS Oracle provider is not installed.")
        manager = self._manager()
        config = QgsAuthMethodConfig()
        config.setName(name)
        config.setMethod("Basic")
        config.setConfig("username", username)
        config.setConfig("password", password)
        if not manager.storeAuthenticationConfig(config):
            raise DatasourceConnectionException(
                "Could not store the encrypted login. Unlock the QGIS Authentication Manager."
            )
        return config

    def _track_record(self, config, key: str, value: Any) -> None:
        try:
            self._settings.set_json(key, value)
        except Exception:
            if not self._manager().removeAuthenticationConfig(config.id()):
                raise DatasourceConnectionException("Could not clean up an untracked database login.")
            raise

    def store(self, username: str, password: str) -> str:
        config = self._store_record(username, password, "GeoData Catalog temporary database session")
        ids = self._settings.get_json(self.SETTINGS_KEY, [])
        ids.append(config.id())
        self._track_record(config, self.SETTINGS_KEY, ids)
        return config.id()


class DatabaseSessionService:
    """One explicitly authenticated database endpoint per plugin session."""

    def __init__(self, authentication: QgisSessionAuthentication) -> None:
        self._authentication = authentication
        self.datasource: Datasource | None = None
        self.username = ""
        self._auth_id = ""

    def initialize(self) -> None:
        self._authentication.cleanup()

    def is_connected(self, datasource: Datasource) -> bool:
        return (
            datasource.enabled
            and datasource.datasource_type is DatasourceType.ORACLE
            and self.datasource is not None
            and database_endpoint(datasource) == database_endpoint(self.datasource)
        )

    def saved_credentials(self, datasource: Datasource) -> tuple[str, str] | None:
        return self._authentication.saved_credentials(datasource)

    def forget_credentials(self, datasource: Datasource) -> None:
        self._authentication.forget_credentials(datasource)

    def connect(
        self, datasource: Datasource, username: str, password: str, remember: bool = False,
    ) -> None:
        if self.datasource is not None:
            raise ConfigurationException("Disconnect the current database before connecting.")
        if not datasource.enabled or datasource.datasource_type is not DatasourceType.ORACLE:
            raise ConfigurationException("Select an enabled Oracle datasource.")
        validate_database_config(datasource.config)
        username = username.strip()
        if not username or not password:
            raise ConfigurationException("Database username and password are required.")
        self._authentication.cleanup()
        config = {**datasource.config, "username": username, "password": password}
        if not OracleConnector(datasource.id, config).test_connection():
            raise DatasourceConnectionException("Database login failed.")
        auth_id = self._authentication.store(username, password)
        try:
            if remember:
                self._authentication.remember_credentials(datasource, username, password)
            else:
                self._authentication.forget_credentials(datasource)
        except Exception:
            self._authentication.cleanup()
            raise
        self.datasource = datasource
        self.username = username
        self._auth_id = auth_id

    def connector_config(self, datasource: Datasource) -> dict[str, Any]:
        if not self.is_connected(datasource):
            raise DatasourceConnectionException("Database disconnected. Use Connect in the GeoData Catalog toolbar.")
        return {
            **{key: value for key, value in datasource.config.items() if key not in ("username", "password", "authcfg")},
            "authcfg": self._auth_id,
        }

    def disconnect(self) -> None:
        self._authentication.cleanup()
        self.datasource = None
        self.username = ""
        self._auth_id = ""
