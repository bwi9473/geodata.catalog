from __future__ import annotations

from geodata_catalog.logging_utils import PluginLogger
from geodata_catalog.metadata.layer_config_repository import LayerConfigRepository
from geodata_catalog.metadata.layer_repository import LayerRepository
from geodata_catalog.models.datasource import Datasource
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

    def discover_layers(self, datasource: Datasource) -> list[LayerDefinition]:
        connector = self._datasource_service.get_connector(datasource)
        discovered = connector.get_layers()
        configured = {
            layer.layer_name: layer
            for layer in self._layer_repository.list_by_datasource(datasource.id)
        }
        layer_configs = (
            {
                cfg.layer_name: cfg
                for cfg in self._layer_config_repository.list_by_datasource(datasource.id)
            }
            if self._layer_config_repository is not None
            else {}
        )

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
                layer.metadata = {**layer.metadata, **configured_layer.metadata}

            # Merge per-layer display/search config (label_column, searchable_columns)
            layer_config = layer_configs.get(layer.layer_name)
            if layer_config is not None:
                if layer_config.layername:
                    layer.display_name = layer_config.layername
                if layer_config.label_column is not None:
                    layer.label_column = layer_config.label_column
                layer.metadata["enable_fl_filter"] = bool(layer_config.enable_fl_filter)
                if layer_config.searchable_columns:
                    layer.searchable_columns = layer_config.searchable_columns
                if layer_config.view_columns:
                    layer.metadata["view_columns"] = layer_config.view_columns

            merged.append(layer)

        self._logger.info(
            f"Discovered {len(merged)} layers for datasource '{datasource.name}'."
        )
        return merged

    def save_layer_configuration(self, layer: LayerDefinition) -> None:
        self._layer_repository.upsert(layer)
        self._logger.info(
            f"Layer configuration saved: {layer.datasource_id}/{layer.layer_name}"
        )

    def get_layer_configuration(
        self,
        datasource_id: str,
        layer_name: str,
    ) -> LayerDefinition | None:
        for layer in self._layer_repository.list_by_datasource(datasource_id):
            if layer.layer_name == layer_name:
                return layer
        return None
