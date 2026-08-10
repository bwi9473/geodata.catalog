from geodata_catalog.connectors.oracle_connector import OracleConnector


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
