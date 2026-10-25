from unittest.mock import Mock

import pytest

from geodata_catalog.connectors.base_connector import BaseConnector
from geodata_catalog.exceptions import LayerLoadException
from geodata_catalog.logging_utils import PluginLogger
from geodata_catalog.metadata.layer_config_repository import LayerConfig, LayerConfigRepository
from geodata_catalog.metadata.layer_repository import LayerRepository
from geodata_catalog.models.datasource import Datasource, DatasourceType
from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.plugin import GeoDataCatalogPlugin
from geodata_catalog.services.datasource_service import DatasourceService
from geodata_catalog.services.layer_service import LayerService


def test_get_layer_preserves_configuration_without_discovering_other_layers():
    datasource = Datasource("oracle-1", "Oracle", DatasourceType.ORACLE)
    connector = Mock(spec=BaseConnector)
    connector.get_layer_metadata.return_value = LayerDefinition(
        "oracle-1", "AIRSPACE.FIR", "AIRSPACE.FIR", "oracle", "uri"
    )
    datasource_service = Mock(spec=DatasourceService)
    datasource_service.get_connector.return_value = connector
    repository = Mock(spec=LayerRepository)
    repository.list_by_datasource.return_value = [
        LayerDefinition(
            "oracle-1", "AIRSPACE.FIR", "Stored FIR", "oracle", "uri",
            default_crs="EPSG:4326",
            geometry_type="POLYGON", metadata={"custom": "preserved"},
        )
    ]
    config = LayerConfig(
        "oracle-1", "AIRSPACE.FIR", layername="Configured FIR",
        category_label="Airspace", label_column="NAME",
        qml_style_path="fir.qml", svg_marker_path="fir.svg",
        enable_fl_filter=False, key_column="OBJECTID",
        field_columns=[{"name": "NAME", "search": True, "export": True}],
    )
    config_repository = Mock(spec=LayerConfigRepository)
    config_repository.list_by_datasource.return_value = [config]
    service = LayerService(
        datasource_service, repository, Mock(spec=PluginLogger), config_repository
    )

    layer = service.get_layer(datasource, "AIRSPACE.FIR")

    connector.get_layer_metadata.assert_called_once_with("AIRSPACE.FIR")
    connector.get_layers.assert_not_called()
    assert layer.display_name == "Configured FIR"
    assert layer.business_group == "Airspace"
    assert layer.default_crs == "EPSG:4326"
    assert layer.geometry_type == "POLYGON"
    assert layer.default_style_file == "fir.qml"
    assert layer.label_column == "NAME"
    assert layer.metadata["custom"] == "preserved"
    assert layer.metadata["svg_marker_path"] == "fir.svg"
    assert layer.metadata["key_column"] == "OBJECTID"
    assert layer.metadata["enable_fl_filter"] is False
    assert layer.searchable_columns == config.searchable_columns
    assert layer.metadata["view_columns"] == config.view_columns


def test_resolve_layer_cache_miss_fetches_only_target_and_preserves_other_entries():
    plugin = GeoDataCatalogPlugin.__new__(GeoDataCatalogPlugin)
    other = LayerDefinition("oracle-1", "AIRSPACE.UIR", "UIR", "oracle", "other")
    selected = LayerDefinition("oracle-1", "AIRSPACE.FIR", "FIR", "oracle", "selected")
    plugin._layer_cache = {"oracle-1": {"AIRSPACE.UIR": other}}
    plugin._datasource_service = Mock(spec=DatasourceService)
    datasource = Datasource("oracle-1", "Oracle", DatasourceType.ORACLE)
    plugin._datasource_service.get_datasource.return_value = datasource
    plugin._layer_service = Mock(spec=LayerService)
    plugin._layer_service.get_layer.return_value = selected

    assert plugin._resolve_layer("oracle-1", "AIRSPACE.FIR") is selected
    assert plugin._resolve_layer("oracle-1", "AIRSPACE.FIR") is selected
    assert plugin._layer_cache["oracle-1"]["AIRSPACE.UIR"] is other
    plugin._layer_service.get_layer.assert_called_once_with(datasource, "AIRSPACE.FIR")
    plugin._layer_service.discover_layers.assert_not_called()


def test_resolve_layer_lookup_failure_is_not_cached():
    plugin = GeoDataCatalogPlugin.__new__(GeoDataCatalogPlugin)
    plugin._layer_cache = {}
    plugin._datasource_service = Mock(spec=DatasourceService)
    plugin._layer_service = Mock(spec=LayerService)
    plugin._layer_service.get_layer.side_effect = LayerLoadException("Layer not found")

    with pytest.raises(LayerLoadException, match="not found"):
        plugin._resolve_layer("oracle-1", "AIRSPACE.MISSING")

    assert plugin._layer_cache == {}
