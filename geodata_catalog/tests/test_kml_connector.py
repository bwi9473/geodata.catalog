from pathlib import Path

import pytest

import geodata_catalog.connectors.kml_connector as kml_connector_module
from geodata_catalog.connectors.kml_connector import KmlConnector
from geodata_catalog.exceptions import LayerLoadException
from geodata_catalog.models.layer_definition import LayerDefinition


def test_parse_sublayer_entry_with_id_first():
    parsed = KmlConnector._parse_sublayer_entry("1!!::!!Aerodromes!!::!!4!!::!!Point25D")

    assert parsed["name"] == "Aerodromes"
    assert parsed["layer_id"] == "1"


def test_parse_sublayer_entry_with_name_first():
    parsed = KmlConnector._parse_sublayer_entry("Aerodromes!!::!!1!!::!!4!!::!!Point25D")

    assert parsed["name"] == "Aerodromes"
    assert parsed["layer_id"] == "1"


def test_kml_get_layers_prefers_layer_id_uri(monkeypatch):
    connector = KmlConnector("ds-kml", {"path": "C:/tmp/aerodromes_sample.kml"})

    monkeypatch.setattr(connector, "_resolve_path", lambda: Path("C:/tmp/aerodromes_sample.kml"))
    monkeypatch.setattr(
        connector,
        "_discover_sublayers",
        lambda path: [{"name": "Aerodromes", "layer_id": "1"}],
    )

    layers = connector.get_layers()

    assert len(layers) == 1
    assert layers[0].display_name == "Aerodromes"
    assert layers[0].provider_uri == "C:/tmp/aerodromes_sample.kml|layerid=1"


def test_kml_connector_reports_empty_layer(monkeypatch):
    connector = KmlConnector("ds-kml", {"path": "C:/tmp/empty.kml"})
    metadata = LayerDefinition(
        datasource_id="ds-kml",
        layer_name="empty",
        display_name="Empty KML",
        provider_key="ogr",
        provider_uri="C:/tmp/empty.kml|layerid=0",
    )

    class EmptyKmlLayer:
        def isValid(self):
            return True

        def featureCount(self):
            return 0

    monkeypatch.setattr(connector, "get_layer_metadata", lambda layer_name: metadata)
    monkeypatch.setattr(kml_connector_module, "QgsVectorLayer", lambda *args: EmptyKmlLayer())

    with pytest.raises(LayerLoadException, match="contains no data"):
        connector.load_layer("empty")
