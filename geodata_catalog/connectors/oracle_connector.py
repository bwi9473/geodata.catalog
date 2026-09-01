from __future__ import annotations

import re
from typing import Any

from geodata_catalog.connectors.base_connector import BaseConnector
from geodata_catalog.exceptions import DatasourceConnectionException, LayerLoadException
from geodata_catalog.models.layer_definition import LayerDefinition

try:
    import oracledb
except ImportError:  # pragma: no cover
    oracledb = None

try:
    from qgis.core import QgsDataSourceUri, QgsVectorLayer
except ImportError:  # pragma: no cover
    QgsDataSourceUri = None
    QgsVectorLayer = None


class OracleConnector(BaseConnector):
    """Connector for Oracle Spatial discovery and loading."""

    _IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")

    def __init__(self, datasource_id: str, config: dict[str, Any]) -> None:
        self._datasource_id = datasource_id
        self._config = config

    def get_layers(self) -> list[LayerDefinition]:
        rows = self._discover_spatial_objects()
        layers: list[LayerDefinition] = []
        for row in rows:
            owner = row[0]
            object_name = row[1]
            geometry_column = row[2]
            srid = row[3]
            object_type = row[4]
            geometry_type = self._detect_geometry_type(owner, object_name, geometry_column)
            feature_count = self._get_feature_count(owner, object_name)
            uri = self._build_layer_uri(owner, object_name, geometry_column)
            display_name = f"{owner}.{object_name}"
            layers.append(
                LayerDefinition(
                    datasource_id=self._datasource_id,
                    layer_name=display_name,
                    display_name=display_name,
                    provider_key="oracle",
                    provider_uri=uri,
                    business_group=self._business_group_for(object_type),
                    geometry_type=geometry_type,
                    srid=int(srid) if srid is not None else None,
                    feature_count=feature_count,
                    geometry_column=geometry_column,
                    owner=owner,
                    object_name=object_name,
                    technical_name=f"{owner}.{object_name}",
                    default_crs=f"EPSG:{srid}" if srid else None,
                    label_column=self._label_column_from_config(self._config),
                    metadata={
                        "owner": owner,
                        "object_name": object_name,
                        "object_type": object_type,
                        "geometry_column": geometry_column,
                        "srid": srid,
                        "geometry_type": geometry_type,
                        "feature_count": feature_count,
                    },
                )
            )
        return layers

    def get_layer_metadata(self, layer_name: str) -> LayerDefinition:
        for layer in self.get_layers():
            if layer.layer_name == layer_name:
                return layer
        raise LayerLoadException(f"Oracle layer '{layer_name}' not found.")

    def load_layer(self, layer_name: str, key_column: str | None = None):
        if QgsVectorLayer is None:
            raise LayerLoadException("QGIS runtime is not available.")
        metadata = self.get_layer_metadata(layer_name)
        configured_key = str(key_column or "").strip()
        if configured_key and not self._is_safe_identifier(configured_key):
            raise LayerLoadException(f"Invalid Oracle key column '{configured_key}'.")
        uri = self._build_layer_uri(
            metadata.owner or "",
            metadata.object_name or "",
            metadata.geometry_column or "",
            configured_key,
        )
        layer = QgsVectorLayer(uri, metadata.display_name, metadata.provider_key)
        if not layer.isValid():
            raise LayerLoadException(f"Invalid Oracle layer '{metadata.display_name}'.")
        return layer

    def get_layer_fields(self, layer_name: str) -> list[dict[str, str | int]]:
        """Return table or view attributes without requiring a QGIS provider key."""
        metadata = self.get_layer_metadata(layer_name)
        owner = metadata.owner or ""
        object_name = metadata.object_name or ""
        if not self._is_safe_identifier(owner) or not self._is_safe_identifier(object_name):
            raise LayerLoadException(f"Invalid Oracle layer name '{layer_name}'.")
        query = """
            SELECT column_name, data_type, column_id
            FROM all_tab_columns
            WHERE owner = :owner
              AND table_name = :object_name
              AND data_type <> 'SDO_GEOMETRY'
            ORDER BY column_id
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"owner": owner, "object_name": object_name})
                return [
                    {
                        "name": str(column_name),
                        "label": str(column_name),
                        "type": self._field_type_category(str(data_type)),
                        "position": int(position),
                    }
                    for column_name, data_type, position in cursor.fetchall()
                ]

    def test_connection(self) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM dual")
                _ = cursor.fetchone()
        return True

    @staticmethod
    def _field_type_category(data_type: str) -> str:
        return (
            "numeric"
            if data_type.upper() in {"NUMBER", "FLOAT", "BINARY_FLOAT", "BINARY_DOUBLE", "INTEGER", "DECIMAL"}
            else "varchar"
        )

    def _discover_spatial_objects(self) -> list[tuple[Any, ...]]:
        owner_filter = self._config.get("schema")
        query = """
            SELECT
                m.owner,
                m.table_name,
                m.column_name,
                m.srid,
                o.object_type
            FROM all_sdo_geom_metadata m
            JOIN all_objects o
                ON o.owner = m.owner
               AND o.object_name = m.table_name
               AND o.object_type IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW')
            JOIN all_tab_columns c
                ON c.owner = m.owner
               AND c.table_name = m.table_name
               AND c.column_name = m.column_name
               AND c.data_type = 'SDO_GEOMETRY'
            WHERE (:owner_filter IS NULL OR m.owner = :owner_filter)
            ORDER BY m.owner, m.table_name
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"owner_filter": owner_filter.upper() if owner_filter else None})
                return cursor.fetchall()

    def _detect_geometry_type(self, owner: str, object_name: str, geometry_column: str) -> str | None:
        sql = (
            f'SELECT MIN(t."{geometry_column}".SDO_GTYPE) '
            f'FROM "{owner}"."{object_name}" t '
            f'WHERE t."{geometry_column}" IS NOT NULL'
        )
        if not self._is_safe_identifier(owner) or not self._is_safe_identifier(object_name) or not self._is_safe_identifier(geometry_column):
            return None
        with self._connect() as connection:
            with connection.cursor() as cursor:
                try:
                    cursor.execute(sql)
                    row = cursor.fetchone()
                except Exception:
                    return None
        if not row or row[0] is None:
            return None
        return self._map_oracle_gtype(int(row[0]))

    def _get_feature_count(self, owner: str, object_name: str) -> int | None:
        if not self._is_safe_identifier(owner) or not self._is_safe_identifier(object_name):
            return None
        sql = f'SELECT COUNT(*) FROM "{owner}"."{object_name}"'
        with self._connect() as connection:
            with connection.cursor() as cursor:
                try:
                    cursor.execute(sql)
                    row = cursor.fetchone()
                    return int(row[0]) if row else None
                except Exception:
                    return None

    def _build_layer_uri(
        self,
        owner: str,
        object_name: str,
        geometry_column: str,
        key_column: str | None = None,
    ) -> str:
        if QgsDataSourceUri is None:
            return ""
        uri = QgsDataSourceUri()
        uri.setConnection(
            self._config.get("host", ""),
            str(self._config.get("port", 1521)),
            self._config.get("service_name", ""),
            self._config.get("username", ""),
            self._config.get("password", ""),
        )
        uri.setDataSource(
            owner,
            object_name,
            geometry_column,
            "",
            key_column or self._config.get("key_column", ""),
        )
        return uri.uri(False)

    def _connect(self):
        if oracledb is None:
            raise DatasourceConnectionException("python-oracledb is not installed.")
        try:
            dsn = oracledb.makedsn(
                self._config["host"],
                int(self._config.get("port", 1521)),
                service_name=self._config["service_name"],
            )
            return oracledb.connect(
                user=self._config["username"],
                password=self._config["password"],
                dsn=dsn,
            )
        except Exception as exc:  # pragma: no cover
            raise DatasourceConnectionException("Failed to connect to Oracle datasource.") from exc

    @classmethod
    def _is_safe_identifier(cls, identifier: str) -> bool:
        return bool(cls._IDENTIFIER_RE.match(identifier))

    @staticmethod
    def _map_oracle_gtype(gtype: int) -> str:
        mapping = {
            2001: "POINT",
            2002: "LINESTRING",
            2003: "POLYGON",
            2007: "MULTIPOLYGON",
            3001: "POINT",
            3002: "LINESTRING",
            3003: "POLYGON",
            3007: "MULTIPOLYGON",
        }
        return mapping.get(gtype, "UNKNOWN")

    @staticmethod
    def _business_group_for(object_type: str) -> str:
        if object_type == "VIEW":
            return "Views"
        if object_type == "MATERIALIZED VIEW":
            return "Materialized Views"
        return "Tables"
