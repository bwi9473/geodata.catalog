from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

from geodata_catalog.connectors.base_connector import BaseConnector
from geodata_catalog.exceptions import (
    ConfigurationException,
    DatasourceConnectionException,
    LayerLoadException,
)
from geodata_catalog.models.datasource import AuthType
from geodata_catalog.models.layer_definition import LayerDefinition

try:
    from qgis.core import QgsVectorLayer
except ImportError:  # pragma: no cover
    QgsVectorLayer = None


class RestConnector(BaseConnector):
    """Connector for GeoJSON REST endpoints."""

    def __init__(self, datasource_id: str, config: dict[str, Any]) -> None:
        self._datasource_id = datasource_id
        self._config = config
        self._temp_files: dict[str, Path] = {}

    def get_layers(self) -> list[LayerDefinition]:
        base_url = self._config.get("url")
        if not base_url:
            raise ConfigurationException("REST datasource requires 'url'.")

        datasets = self._config.get("datasets") or []
        if not datasets:
            datasets = [{"name": self._config.get("display_name", "REST Dataset"), "params": {}}]

        layers: list[LayerDefinition] = []
        for dataset in datasets:
            display_name = dataset.get("name", "REST Dataset")
            dataset_params = dataset.get("params", {})
            uri = self._build_request_url(base_url, dataset_params)
            layers.append(
                LayerDefinition(
                    datasource_id=self._datasource_id,
                    layer_name=display_name,
                    display_name=display_name,
                    provider_key="ogr",
                    provider_uri=uri,
                    business_group="REST Sources",
                    technical_name=uri,
                    label_column=self._label_column_from_config(self._config),
                    metadata={
                        "url": base_url,
                        "dataset_params": dataset_params,
                        "headers": self._config.get("headers", {}),
                    },
                )
            )
        return layers

    def get_layer_metadata(self, layer_name: str) -> LayerDefinition:
        for layer in self.get_layers():
            if layer.layer_name == layer_name:
                return layer
        raise LayerLoadException(f"REST layer '{layer_name}' not found.")

    def load_layer(self, layer_name: str):
        if QgsVectorLayer is None:
            raise LayerLoadException("QGIS runtime is not available.")

        metadata = self.get_layer_metadata(layer_name)
        payload = self._request_geojson(metadata)
        temp_path = self._write_temp_geojson(layer_name, payload)
        layer = QgsVectorLayer(str(temp_path), metadata.display_name, "ogr")
        if not layer.isValid():
            raise LayerLoadException(f"Invalid REST GeoJSON for '{metadata.display_name}'.")
        return layer

    def test_connection(self) -> bool:
        for layer in self.get_layers():
            _ = self._request_geojson(layer)
        return True

    def _request_geojson(self, layer: LayerDefinition) -> dict[str, Any]:
        if requests is None:
            raise DatasourceConnectionException(
                "requests package is not installed. REST sources are unavailable."
            )
        url = self._config.get("url")
        headers = dict(self._config.get("headers", {}))
        params = dict(self._config.get("query_params", {}))
        params.update(layer.metadata.get("dataset_params", {}))

        auth = self._build_auth(headers)
        response = requests.get(
            url,
            headers=headers,
            params=params,
            auth=auth,
            timeout=float(self._config.get("timeout", 30.0)),
        )
        response.raise_for_status()
        payload = response.json()
        self._validate_geojson(payload)
        return payload

    def _build_auth(self, headers: dict[str, str]):
        auth_type = AuthType(self._config.get("auth_type", AuthType.NONE.value))
        if auth_type is AuthType.NONE:
            return None
        if auth_type is AuthType.BASIC:
            return (
                self._config.get("username", ""),
                self._config.get("password", ""),
            )
        if auth_type is AuthType.BEARER:
            token = self._config.get("token", "")
            headers["Authorization"] = f"Bearer {token}"
            return None
        return None

    def _write_temp_geojson(self, layer_name: str, payload: dict[str, Any]) -> Path:
        if layer_name in self._temp_files:
            path = self._temp_files[layer_name]
        else:
            fd, name = tempfile.mkstemp(prefix="geodata_catalog_", suffix=".geojson")
            Path(name).unlink(missing_ok=True)
            path = Path(name)
            self._temp_files[layer_name] = path
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    @staticmethod
    def _validate_geojson(payload: dict[str, Any]) -> None:
        if payload.get("type") not in {"FeatureCollection", "Feature"}:
            raise ConfigurationException("REST endpoint did not return valid GeoJSON.")

    @staticmethod
    def _build_request_url(base_url: str, dataset_params: dict[str, Any]) -> str:
        if not dataset_params:
            return base_url
        encoded = "&".join(f"{key}={value}" for key, value in dataset_params.items())
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}{encoded}"
