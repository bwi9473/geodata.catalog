from __future__ import annotations

from typing import Any

from geodata_catalog.connectors.base_connector import BaseConnector
from geodata_catalog.exceptions import DatasourceConnectionException, LayerLoadException
from geodata_catalog.models.layer_definition import LayerDefinition

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

try:
    from qgis.core import QgsDataSourceUri, QgsVectorLayer
except ImportError:  # pragma: no cover
    QgsDataSourceUri = None
    QgsVectorLayer = None


class PostgisConnector(BaseConnector):
    """Connector for PostGIS discovery and loading."""

    def __init__(self, datasource_id: str, config: dict[str, Any]) -> None:
        self._datasource_id = datasource_id
        self._config = config

    def get_layers(self) -> list[LayerDefinition]:
        sql = """
            SELECT
                f_table_schema,
                f_table_name,
                f_geometry_column,
                srid,
                type
            FROM geometry_columns
            ORDER BY f_table_schema, f_table_name
        """
        layers: list[LayerDefinition] = []
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                for schema, table_name, geom_col, srid, geom_type in rows:
                    full_name = f"{schema}.{table_name}"
                    uri = self._build_layer_uri(schema, table_name, geom_col)
                    layers.append(
                        LayerDefinition(
                            datasource_id=self._datasource_id,
                            layer_name=full_name,
                            display_name=full_name,
                            provider_key="postgres",
                            provider_uri=uri,
                            business_group="Database",
                            geometry_type=geom_type,
                            srid=int(srid) if srid is not None else None,
                            feature_count=self._feature_count(schema, table_name),
                            geometry_column=geom_col,
                            owner=schema,
                            object_name=table_name,
                            technical_name=full_name,
                            default_crs=f"EPSG:{srid}" if srid else None,
                            label_column=self._label_column_from_config(self._config),
                            metadata={
                                "schema": schema,
                                "table": table_name,
                                "geometry_column": geom_col,
                                "srid": srid,
                                "geometry_type": geom_type,
                            },
                        )
                    )
        return layers

    def get_layer_metadata(self, layer_name: str) -> LayerDefinition:
        for layer in self.get_layers():
            if layer.layer_name == layer_name:
                return layer
        raise LayerLoadException(f"PostGIS layer '{layer_name}' not found.")

    def load_layer(self, layer_name: str):
        if QgsVectorLayer is None:
            raise LayerLoadException("QGIS runtime is not available.")
        metadata = self.get_layer_metadata(layer_name)
        layer = QgsVectorLayer(metadata.provider_uri, metadata.display_name, metadata.provider_key)
        if not layer.isValid():
            raise LayerLoadException(f"Invalid PostGIS layer '{metadata.display_name}'.")
        return layer

    def test_connection(self) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                _ = cursor.fetchone()
        return True

    def _connect(self):
        if psycopg is None:
            raise DatasourceConnectionException("psycopg is not installed.")
        try:
            return psycopg.connect(
                host=self._config["host"],
                port=int(self._config.get("port", 5432)),
                dbname=self._config["database"],
                user=self._config["username"],
                password=self._config["password"],
            )
        except Exception as exc:  # pragma: no cover
            raise DatasourceConnectionException("Failed to connect to PostGIS datasource.") from exc

    def _feature_count(self, schema: str, table_name: str) -> int | None:
        sql = f'SELECT COUNT(*) FROM "{schema}"."{table_name}"'
        with self._connect() as connection:
            with connection.cursor() as cursor:
                try:
                    cursor.execute(sql)
                    row = cursor.fetchone()
                    return int(row[0]) if row else None
                except Exception:
                    return None

    def _build_layer_uri(self, schema: str, table_name: str, geom_col: str) -> str:
        if QgsDataSourceUri is None:
            return ""
        uri = QgsDataSourceUri()
        uri.setConnection(
            self._config.get("host", ""),
            str(self._config.get("port", 5432)),
            self._config.get("database", ""),
            self._config.get("username", ""),
            self._config.get("password", ""),
        )
        uri.setDataSource(schema, table_name, geom_col, "", self._config.get("key_column", ""))
        return uri.uri(False)
