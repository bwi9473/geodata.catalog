import pytest

import geodata_catalog.connectors.oracle_connector as oracle_connector_module
from geodata_catalog.connectors.oracle_connector import OracleConnector
from geodata_catalog.exceptions import LayerLoadException


class FakeCursor:
    def __init__(self):
        self.last_query = ""
        self.last_params = {}

    def execute(self, query, params=None):
        self.last_query = query
        self.last_params = params or {}

    def fetchall(self):
        if "FROM all_sdo_geom_metadata" in self.last_query:
            return [
                ("AIRSPACE", "FIR", "SHAPE", 4326, "TABLE"),
                ("AIRSPACE", "UIR", "SHAPE", 4326, "VIEW"),
            ]
        return []

    def fetchone(self):
        if "MIN(t." in self.last_query:
            return (2003,)
        if "COUNT(*)" in self.last_query:
            return (25,)
        return (1,)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class FakeConnection:
    def cursor(self):
        return FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def test_oracle_connector_discovers_spatial_layers(monkeypatch):
    connector = OracleConnector(
        datasource_id="oracle-1",
        config={
            "host": "x",
            "port": 1521,
            "service_name": "y",
            "username": "u",
            "password": "p",
        },
    )

    monkeypatch.setattr(connector, "_connect", lambda: FakeConnection())
    monkeypatch.setattr(
        connector,
        "_build_layer_uri",
        lambda owner, object_name, geometry_column: (
            f"oracle://{owner}/{object_name}/{geometry_column}"
        ),
    )

    layers = connector.get_layers()

    assert len(layers) == 2
    assert layers[0].owner == "AIRSPACE"
    assert layers[0].object_name == "FIR"
    assert layers[0].geometry_column == "SHAPE"
    assert layers[0].srid == 4326
    assert layers[0].geometry_type == "POLYGON"
    assert layers[0].feature_count == 25


def test_oracle_connector_reports_empty_table_before_qgis_load(monkeypatch):
    connector = OracleConnector(
        datasource_id="oracle-1",
        config={
            "host": "x",
            "port": 1521,
            "service_name": "y",
            "username": "u",
            "password": "p",
        },
    )
    monkeypatch.setattr(
        connector,
        "get_layer_metadata",
        lambda layer_name: oracle_connector_module.LayerDefinition(
            datasource_id="oracle-1",
            layer_name=layer_name,
            display_name="AIRSPACE.EMPTY_TABLE",
            provider_key="oracle",
            provider_uri="",
            feature_count=0,
        ),
    )
    monkeypatch.setattr(
        oracle_connector_module,
        "QgsVectorLayer",
        lambda *args: pytest.fail("QGIS should not load an empty Oracle table"),
    )

    with pytest.raises(LayerLoadException, match="contains no data"):
        connector.load_layer("AIRSPACE.EMPTY_TABLE")
