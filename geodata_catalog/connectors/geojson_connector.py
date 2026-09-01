from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from geodata_catalog.connectors.base_connector import BaseConnector
from geodata_catalog.exceptions import ConfigurationException, LayerLoadException
from geodata_catalog.models.layer_definition import LayerDefinition

try:
    from qgis.core import QgsVectorLayer
except ImportError:  # pragma: no cover
    QgsVectorLayer = None


class GeoJsonConnector(BaseConnector):
    """Connector for local GeoJSON file discovery and loading."""

    def __init__(self, datasource_id: str, config: dict[str, Any]) -> None:
        self._datasource_id = datasource_id
        self._config = config

    def get_layers(self) -> list[LayerDefinition]:
        layers: list[LayerDefinition] = []
        for file_path in self._resolve_paths():
            payload = self._load_and_validate_geojson(file_path)
            geometry_type = self._infer_geometry_type(payload)
            layers.append(
                LayerDefinition(
                    datasource_id=self._datasource_id,
                    layer_name=file_path.name,
                    display_name=file_path.stem,
                    provider_key="ogr",
                    provider_uri=str(file_path),
                    business_group="File Sources",
                    geometry_type=geometry_type,
                    srid=self._extract_epsg(payload),
                    feature_count=self._feature_count(payload),
                    technical_name=str(file_path),
                    default_crs="EPSG:4326",
                    label_column=self._label_column_from_config(self._config),
                    metadata={"path": str(file_path), "type": "GeoJSON"},
                )
            )
        return layers

    def get_layer_metadata(self, layer_name: str) -> LayerDefinition:
        for layer in self.get_layers():
            if layer.layer_name == layer_name:
                return layer
        raise LayerLoadException(f"GeoJSON layer '{layer_name}' not found.")

    def load_layer(self, layer_name: str, key_column: str | None = None):
        if QgsVectorLayer is None:
            raise LayerLoadException("QGIS runtime is not available.")
        metadata = self.get_layer_metadata(layer_name)
        self._raise_if_empty_layer(metadata)
        layer = QgsVectorLayer(metadata.provider_uri, metadata.display_name, metadata.provider_key)
        if not layer.isValid():
            raise LayerLoadException(f"Invalid GeoJSON file for '{metadata.display_name}'.")
        return layer

    def test_connection(self) -> bool:
        for file_path in self._resolve_paths():
            _ = self._load_and_validate_geojson(file_path)
        return True

    def _resolve_paths(self) -> list[Path]:
        path_value = self._config.get("path")
        if not path_value:
            raise ConfigurationException("GeoJSON datasource requires 'path'.")
        path = Path(path_value)
        if path.is_file():
            return [path]
        if path.is_dir():
            return sorted([*path.glob("*.geojson"), *path.glob("*.json")])
        raise ConfigurationException(f"GeoJSON path does not exist: {path}")

    @staticmethod
    def _load_and_validate_geojson(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("type") not in {"FeatureCollection", "Feature"}:
            raise ConfigurationException(f"Unsupported GeoJSON type in file: {path}")
        return payload

    @staticmethod
    def _feature_count(payload: dict[str, Any]) -> int:
        if payload.get("type") == "FeatureCollection":
            return len(payload.get("features", []))
        return 1

    @staticmethod
    def _infer_geometry_type(payload: dict[str, Any]) -> str | None:
        if payload.get("type") == "Feature":
            geometry = payload.get("geometry") or {}
            return geometry.get("type")
        features = payload.get("features", [])
        for feature in features:
            geometry = feature.get("geometry") or {}
            geom_type = geometry.get("type")
            if geom_type:
                return geom_type.upper()
        return None

    @staticmethod
    def _extract_epsg(payload: dict[str, Any]) -> int | None:
        crs = payload.get("crs") or {}
        props = crs.get("properties") or {}
        name = props.get("name", "")
        if name.upper().startswith("EPSG:"):
            try:
                return int(name.split(":", maxsplit=1)[1])
            except (ValueError, IndexError):
                return None
        return None
