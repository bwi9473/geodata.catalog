import json

from geodata_catalog.connectors.geojson_connector import GeoJsonConnector


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
