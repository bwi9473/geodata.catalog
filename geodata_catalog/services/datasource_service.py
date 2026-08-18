from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from geodata_catalog.connectors.base_connector import BaseConnector
from geodata_catalog.connectors.geojson_connector import GeoJsonConnector
from geodata_catalog.connectors.kml_connector import KmlConnector
from geodata_catalog.connectors.oracle_connector import OracleConnector
from geodata_catalog.connectors.rest_connector import RestConnector
from geodata_catalog.exceptions import ConfigurationException
from geodata_catalog.logging_utils import PluginLogger
from geodata_catalog.metadata.datasource_repository import DatasourceRepository
from geodata_catalog.models.datasource import Datasource, DatasourceType

ConnectorFactory = Callable[[Datasource], BaseConnector]


class DatasourceService:
    """Business service for datasource lifecycle and connector creation."""

    def __init__(self, repository: DatasourceRepository, logger: PluginLogger) -> None:
        self._repository = repository
        self._logger = logger

    def list_datasources(self) -> list[Datasource]:
        return self._repository.list_all()

    def create_datasource(
        self,
        name: str,
        datasource_type: DatasourceType,
        config: dict[str, Any],
        enabled: bool = True,
    ) -> Datasource:
        datasource = Datasource(
            id=str(uuid.uuid4()),
            name=name,
            datasource_type=datasource_type,
            config=config,
            enabled=enabled,
        )
        self._repository.upsert(datasource)
        self._logger.info(f"Datasource created: {datasource.name}")
        return datasource

    def update_datasource(self, datasource: Datasource) -> None:
        self._repository.upsert(datasource)
        self._logger.info(f"Datasource updated: {datasource.name}")

    def delete_datasource(self, datasource_id: str) -> None:
        datasource = self._repository.get_by_id(datasource_id)
        self._repository.delete(datasource_id)
        if datasource is not None:
            self._logger.info(f"Datasource deleted: {datasource.name}")

    def get_datasource(self, datasource_id: str) -> Datasource:
        datasource = self._repository.get_by_id(datasource_id)
        if datasource is None:
            raise ConfigurationException(f"Datasource '{datasource_id}' not found.")
        return datasource

    def get_connector(self, datasource: Datasource) -> BaseConnector:
        connector_map: dict[DatasourceType, type[BaseConnector]] = {
            DatasourceType.ORACLE: OracleConnector,
            DatasourceType.GEOJSON: GeoJsonConnector,
            DatasourceType.KML: KmlConnector,
            DatasourceType.REST: RestConnector,
        }
        connector_type = connector_map.get(datasource.datasource_type)
        if connector_type is None:
            raise ConfigurationException(
                f"Unsupported datasource type: {datasource.datasource_type.value}"
            )
        return connector_type(datasource.id, datasource.config)

    def test_datasource(self, datasource_id: str) -> bool:
        datasource = self.get_datasource(datasource_id)
        connector = self.get_connector(datasource)
        result = connector.test_connection()
        self._logger.info(f"Datasource test completed: {datasource.name}")
        return result
