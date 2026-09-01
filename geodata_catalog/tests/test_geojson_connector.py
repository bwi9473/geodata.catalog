import json

import pytest

import geodata_catalog.connectors.geojson_connector as geojson_connector_module
from geodata_catalog.connectors.geojson_connector import GeoJsonConnector
from geodata_catalog.exceptions import LayerLoadException


def test_geojson_connector_discovers_layer(tmp_path):
    file_path = tmp_path / "airports.geojson"
    file_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "A"},
                        "geometry": {"type": "Point", "coordinates": [1, 2]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    connector = GeoJsonConnector("ds-file", {"path": str(file_path)})
    layers = connector.get_layers()

    assert len(layers) == 1
    assert layers[0].display_name == "airports"
    assert layers[0].feature_count == 1
    assert layers[0].geometry_type == "POINT"


def test_geojson_connector_reports_empty_file_before_qgis_load(tmp_path, monkeypatch):
    file_path = tmp_path / "empty.geojson"
    file_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": []}),
        encoding="utf-8",
    )
    connector = GeoJsonConnector("ds-file", {"path": str(file_path)})

    monkeypatch.setattr(
        geojson_connector_module,
        "QgsVectorLayer",
        lambda *args: pytest.fail("QGIS should not load an empty GeoJSON file"),
    )

    with pytest.raises(LayerLoadException, match="contains no data"):
        connector.load_layer("empty.geojson")
