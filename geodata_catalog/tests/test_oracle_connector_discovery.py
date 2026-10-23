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


@pytest.fixture
def targeted_oracle(monkeypatch):
    queries = []
    connections = []
    rows = [
        ("AIRSPACE", f"LAYER_{index}", "SHAPE", 4326, "VIEW")
        for index in range(35)
    ]

    class RecordingCursor(FakeCursor):
        def execute(self, query, params=None):
            super().execute(query, params)
            queries.append((query, params or {}))

        def fetchall(self):
            if "FROM all_sdo_geom_metadata" not in self.last_query:
                return [("OBJECTID", "NUMBER", 1)]
            return [
                row for row in rows
                if (not self.last_params.get("layer_owner") or row[0] == self.last_params["layer_owner"])
                and (not self.last_params.get("layer_object") or row[1] == self.last_params["layer_object"])
                and (not self.last_params.get("owner_filter") or row[0] == self.last_params["owner_filter"])
            ]

    class RecordingConnection(FakeConnection):
        def cursor(self):
            return RecordingCursor()

    def connect():
        connections.append(1)
        return RecordingConnection()

    connector = OracleConnector("oracle-1", {})
    monkeypatch.setattr(connector, "_connect", connect)
    monkeypatch.setattr(
        connector, "_build_layer_uri",
        lambda owner, object_name, geometry_column, key_column=None: (
            f"{owner}.{object_name}/{geometry_column}/{key_column or ''}"
        ),
    )
    return connector, queries, connections, rows


def test_oracle_metadata_only_queries_selected_layer(targeted_oracle):
    connector, queries, connections, _rows = targeted_oracle

    metadata = connector.get_layer_metadata("AIRSPACE.LAYER_17")

    assert metadata.layer_name == "AIRSPACE.LAYER_17"
    assert metadata.geometry_column == "SHAPE"
    assert metadata.default_crs == "EPSG:4326"
    assert metadata.geometry_type is None
    assert metadata.feature_count is None
    assert len(connections) == len(queries) == 1
    query, params = queries[0]
    assert "m.owner = :layer_owner" in query
    assert "m.table_name = :layer_object" in query
    assert params["layer_owner"] == "AIRSPACE"
    assert params["layer_object"] == "LAYER_17"


def test_oracle_load_only_checks_selected_layer_for_data(targeted_oracle, monkeypatch):
    connector, queries, connections, _rows = targeted_oracle
    loaded = []

    class ValidLayer:
        def __init__(self, *args):
            loaded.append(args)

        def isValid(self):
            return True

    monkeypatch.setattr(oracle_connector_module, "QgsVectorLayer", ValidLayer)

    connector.load_layer("AIRSPACE.LAYER_17", key_column="OBJECTID")

    assert loaded == [("AIRSPACE.LAYER_17/SHAPE/OBJECTID", "AIRSPACE.LAYER_17", "oracle")]
    assert len(connections) == len(queries) == 2
    assert 'SELECT 1 FROM "AIRSPACE"."LAYER_17" WHERE ROWNUM = 1' in queries[1][0]
    assert all("COUNT(*)" not in query and "MIN(t." not in query for query, _ in queries)


def test_oracle_load_empty_layer_uses_bounded_check(targeted_oracle, monkeypatch):
    connector, queries, _connections, _rows = targeted_oracle
    monkeypatch.setattr(FakeCursor, "fetchone", lambda self: None)
    monkeypatch.setattr(
        oracle_connector_module, "QgsVectorLayer",
        lambda *args: pytest.fail("QGIS should not load an empty Oracle layer"),
    )

    with pytest.raises(LayerLoadException, match="contains no data"):
        connector.load_layer("AIRSPACE.LAYER_17")

    assert len(queries) == 2


@pytest.mark.parametrize("layer_name", ["LAYER_17", "AIRSPACE.X.Y", "AIRSPACE.X;DROP", ".X"])
def test_oracle_rejects_invalid_target_without_connecting(targeted_oracle, layer_name):
    connector, queries, connections, _rows = targeted_oracle

    with pytest.raises(LayerLoadException, match="Invalid Oracle layer name"):
        connector.get_layer_metadata(layer_name)

    assert queries == connections == []


def test_oracle_missing_target_does_not_query_statistics(targeted_oracle):
    connector, queries, connections, _rows = targeted_oracle

    with pytest.raises(LayerLoadException, match="not found"):
        connector.get_layer_metadata("AIRSPACE.MISSING")

    assert len(connections) == len(queries) == 1


def test_oracle_target_lookup_respects_schema_filter(targeted_oracle):
    connector, queries, _connections, _rows = targeted_oracle
    connector._config["schema"] = "another_schema"

    with pytest.raises(LayerLoadException, match="not found"):
        connector.get_layer_metadata("AIRSPACE.LAYER_17")

    assert queries[0][1]["owner_filter"] == "ANOTHER_SCHEMA"


def test_oracle_field_lookup_only_queries_selected_layer(targeted_oracle):
    connector, queries, connections, _rows = targeted_oracle

    fields = connector.get_layer_fields("AIRSPACE.LAYER_17")

    assert fields == [
        {"name": "OBJECTID", "label": "OBJECTID", "type": "numeric", "position": 1}
    ]
    assert len(connections) == len(queries) == 2
    assert queries[0][1]["layer_object"] == "LAYER_17"
    assert queries[1][1] == {"owner": "AIRSPACE", "object_name": "LAYER_17"}


def test_oracle_load_surfaces_data_check_failure(targeted_oracle, monkeypatch):
    connector, queries, _connections, _rows = targeted_oracle

    def fail_fetch(self):
        raise RuntimeError("Database query failed")

    monkeypatch.setattr(FakeCursor, "fetchone", fail_fetch)
    monkeypatch.setattr(
        oracle_connector_module, "QgsVectorLayer",
        lambda *args: pytest.fail("QGIS must not load after a failed data check"),
    )

    with pytest.raises(RuntimeError, match="Database query failed"):
        connector.load_layer("AIRSPACE.LAYER_17")

    assert len(queries) == 2
