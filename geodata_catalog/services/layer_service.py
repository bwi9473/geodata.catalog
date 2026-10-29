from __future__ import annotations

from dataclasses import replace

from geodata_catalog.exceptions import ConfigurationException
from geodata_catalog.logging_utils import PluginLogger
from geodata_catalog.metadata.layer_config_repository import LayerConfig, LayerConfigRepository
from geodata_catalog.metadata.layer_repository import LayerRepository
from geodata_catalog.models.datasource import Datasource, DatasourceType
from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.services.datasource_service import DatasourceService


class LayerService:
    """Combines discovered connector layers with configured business metadata."""

    def __init__(
        self,
        datasource_service: DatasourceService,
        layer_repository: LayerRepository,
        logger: PluginLogger,
        layer_config_repository: LayerConfigRepository | None = None,
    ) -> None:
        self._datasource_service = datasource_service
        self._layer_repository = layer_repository
        self._logger = logger
        self._layer_config_repository = layer_config_repository

    def discover_layers(
        self, datasource: Datasource, include_stats: bool = True
    ) -> list[LayerDefinition]:
        connector = self._datasource_service.get_connector(datasource)
        discovered = list(connector.get_layers(include_stats=include_stats))
        if datasource.datasource_type is DatasourceType.ORACLE:
            found = {layer.layer_name for layer in discovered}
            for layer in self.configured_layers(datasource):
                if layer.layer_name not in found:
                    layer.metadata["unavailable"] = True
                    layer.metadata["unavailable_reason"] = (
                        "Source not found or not accessible with this database login."
                    )
                    discovered.append(layer)
        merged = self._merge_configuration(datasource.id, discovered)
        self._logger.info(
            f"Discovered {len(merged)} layers for datasource '{datasource.name}'."
        )
        return merged

    def get_layer(self, datasource: Datasource, layer_name: str) -> LayerDefinition:
        """Resolve one layer and apply the same configuration as catalog discovery."""
        connector = self._datasource_service.get_connector(datasource)
        layer = connector.get_layer_metadata(layer_name)
        return self._merge_configuration(datasource.id, [layer])[0]

    def _merge_configuration(
        self, datasource_id: str, discovered: list[LayerDefinition]
    ) -> list[LayerDefinition]:
        datasource = self._datasource_service.get_datasource(datasource_id)
        configured, layer_configs = self._configuration(datasource)

        merged: list[LayerDefinition] = []
        for layer in discovered:
            # Merge business metadata (display_name, style, CRS, etc.)
            configured_layer = configured.get(layer.layer_name)
            if configured_layer is not None:
                layer.display_name = configured_layer.display_name
                layer.business_group = configured_layer.business_group
                layer.default_crs = configured_layer.default_crs or layer.default_crs
                layer.default_style_file = (
                    configured_layer.default_style_file or layer.default_style_file
                )
                layer.geometry_type = layer.geometry_type or configured_layer.geometry_type
                layer.metadata = {**layer.metadata, **configured_layer.metadata}

            # Merge per-layer display/search config (label_column, searchable_columns)
            layer_config = layer_configs.get(layer.layer_name)
            if layer_config is not None:
                if layer_config.layername:
                    layer.display_name = layer_config.layername
                if layer_config.category_label:
                    layer.business_group = layer_config.category_label
                if layer_config.label_column is not None:
                    layer.label_column = layer_config.label_column
                layer.metadata["svg_marker_path"] = layer_config.svg_marker_path
                if layer_config.qml_style_path:
                    layer.default_style_file = layer_config.qml_style_path
                layer.metadata["enable_fl_filter"] = bool(layer_config.enable_fl_filter)
                layer.searchable_columns = layer_config.searchable_columns
                layer.metadata["view_columns"] = layer_config.view_columns
                layer.metadata["key_column"] = layer_config.key_column

            merged.append(layer)

        return merged

    def _configuration_ids(self, datasource: Datasource) -> list[str]:
        if datasource.datasource_type is not DatasourceType.ORACLE or not datasource.config.get("catalog_id"):
            return [datasource.id]
        peers = [
            source.id for source in self._datasource_service.list_datasources()
            if source.datasource_type is DatasourceType.ORACLE
            and source.catalog_id == datasource.catalog_id and source.id != datasource.id
        ]
        return list(dict.fromkeys([datasource.catalog_id, datasource.id, *sorted(peers)]))

    def _configuration(
        self, datasource: Datasource, legacy_catalog_id: str | None = None,
    ) -> tuple[dict[str, LayerDefinition], dict[str, LayerConfig]]:
        layers: dict[str, LayerDefinition] = {}
        configs: dict[str, LayerConfig] = {}
        source_ids = self._configuration_ids(datasource)
        if legacy_catalog_id and legacy_catalog_id not in source_ids:
            source_ids.append(legacy_catalog_id)
        for source_id in source_ids:
            for layer in self._layer_repository.list_by_datasource(source_id):
                layers.setdefault(layer.layer_name, layer)
            if self._layer_config_repository is None:
                continue
            for config in self._layer_config_repository.list_by_datasource(source_id):
                previous = configs.get(config.layer_name)
                if previous is not None and previous.datasource_id != datasource.catalog_id:
                    if replace(previous, datasource_id="") != replace(config, datasource_id=""):
                        raise ConfigurationException(
                            f"Conflicting legacy configuration for '{config.layer_name}' in catalog "
                            f"'{datasource.catalog_id}'. Align the existing layer configurations "
                            "before sharing this catalog_id."
                        )
                configs.setdefault(config.layer_name, config)
        return layers, configs

    def get_display_configuration(self, datasource: Datasource, layer_name: str) -> LayerConfig | None:
        return self._configuration(datasource)[1].get(layer_name)

    def save_display_configuration(self, datasource: Datasource, config: LayerConfig) -> None:
        if self._layer_config_repository is None:
            raise ConfigurationException("Layer configuration storage is unavailable.")
        self._layer_config_repository.save(replace(config, datasource_id=datasource.catalog_id))

    def promote_configuration(self, datasource: Datasource, legacy_catalog_id: str | None = None) -> None:
        """Copy legacy endpoint settings to the shared catalog before unlinking it."""
        layers, configs = self._configuration(datasource, legacy_catalog_id)
        for config in configs.values():
            self.save_display_configuration(datasource, config)
        for layer in layers.values():
            self._layer_repository.upsert(replace(
                layer, datasource_id=datasource.catalog_id,
                provider_uri="" if datasource.datasource_type is DatasourceType.ORACLE else layer.provider_uri,
                metadata={key: value for key, value in layer.metadata.items()
                          if key not in ("unavailable", "unavailable_reason")},
            ))

    def display_configurations(self, datasource: Datasource) -> list[LayerConfig]:
        return [
            replace(config, datasource_id=datasource.catalog_id)
            for config in self._configuration(datasource)[1].values()
        ]

    def configured_layers(self, datasource: Datasource) -> list[LayerDefinition]:
        configured, configs = self._configuration(datasource)
        layers = {
            name: LayerDefinition.from_dict(layer.to_dict())
            for name, layer in configured.items()
        }
        for name in configs:
            layers.setdefault(name, LayerDefinition(
                datasource.id, name, name,
                "oracle" if datasource.datasource_type is DatasourceType.ORACLE else "", "",
            ))
        for layer in layers.values():
            layer.datasource_id = datasource.id
            layer.metadata = dict(layer.metadata)
            if datasource.datasource_type is DatasourceType.ORACLE:
                layer.provider_uri = ""
        return self._merge_configuration(datasource.id, list(layers.values()))

    def save_layer_configuration(self, layer: LayerDefinition) -> None:
        datasource = self._datasource_service.get_datasource(layer.datasource_id)
        metadata = {key: value for key, value in layer.metadata.items()
                    if key not in ("unavailable", "unavailable_reason")}
        self._layer_repository.upsert(replace(
            layer, datasource_id=datasource.catalog_id, metadata=metadata,
            provider_uri="" if datasource.datasource_type is DatasourceType.ORACLE else layer.provider_uri,
        ))
        self._logger.info(
            f"Layer configuration saved: {layer.datasource_id}/{layer.layer_name}"
        )

    def get_layer_configuration(
        self,
        datasource_id: str,
        layer_name: str,
    ) -> LayerDefinition | None:
        for layer in self.list_configured_layers(datasource_id):
            if layer.layer_name == layer_name:
                return layer
        return None

    def list_configured_layers(self, datasource_id: str) -> list[LayerDefinition]:
        """Return shared and legacy configurations for a runtime datasource.

        Useful as fallback metadata when runtime discovery is temporarily unavailable.
        """
        datasource = self._datasource_service.get_datasource(datasource_id)
        return self.configured_layers(datasource)
