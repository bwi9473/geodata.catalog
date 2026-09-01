from __future__ import annotations

from pathlib import Path
from typing import Any

from geodata_catalog.connectors.base_connector import BaseConnector
from geodata_catalog.exceptions import ConfigurationException, LayerLoadException
from geodata_catalog.models.layer_definition import LayerDefinition

try:
    from qgis.core import QgsVectorLayer
except ImportError:  # pragma: no cover
    QgsVectorLayer = None


class KmlConnector(BaseConnector):
    """Connector for local KML/KMZ discovery and loading."""

    def __init__(self, datasource_id: str, config: dict[str, Any]) -> None:
        self._datasource_id = datasource_id
        self._config = config

    def get_layers(self) -> list[LayerDefinition]:
        path = self._resolve_path()
        sublayers = self._discover_sublayers(path)
        if not sublayers:
            sublayers = [{"name": path.stem, "layer_id": None}]

        return [
            LayerDefinition(
                datasource_id=self._datasource_id,
                layer_name=sublayer["name"],
                display_name=sublayer["name"],
                provider_key="ogr",
                provider_uri=(
                    f"{path.as_posix()}|layerid={sublayer['layer_id']}"
                    if sublayer["layer_id"] is not None
                    else f"{path.as_posix()}|layername={sublayer['name']}"
                ),
                business_group="File Sources",
                geometry_type=None,
                srid=4326,
                default_crs="EPSG:4326",
                technical_name=f"{path}:{sublayer['name']}",
                label_column=self._label_column_from_config(self._config),
                metadata={
                    "path": str(path),
                    "type": "KML",
                    "sublayer": sublayer["name"],
                    "sublayer_id": sublayer["layer_id"],
                },
            )
            for sublayer in sublayers
        ]

    def get_layer_metadata(self, layer_name: str) -> LayerDefinition:
        for layer in self.get_layers():
            if layer.layer_name == layer_name:
                return layer
        raise LayerLoadException(f"KML layer '{layer_name}' not found.")

    def load_layer(self, layer_name: str, key_column: str | None = None):
        if QgsVectorLayer is None:
            raise LayerLoadException("QGIS runtime is not available.")
        metadata = self.get_layer_metadata(layer_name)
        layer = QgsVectorLayer(metadata.provider_uri, metadata.display_name, metadata.provider_key)
        if not layer.isValid():
            raise LayerLoadException(f"Invalid KML layer '{metadata.display_name}'.")
        if layer.featureCount() == 0:
            raise LayerLoadException(
                f"Layer '{metadata.display_name}' is not loaded because it contains no data."
            )
        return layer

    def test_connection(self) -> bool:
        _ = self._resolve_path()
        return True

    def _resolve_path(self) -> Path:
        path_value = self._config.get("path")
        if not path_value:
            raise ConfigurationException("KML datasource requires 'path'.")
        path = Path(path_value)
        if not path.exists() or not path.is_file():
            raise ConfigurationException(f"KML path does not exist: {path}")
        return path

    def _discover_sublayers(self, path: Path) -> list[dict[str, str | None]]:
        if QgsVectorLayer is None:
            return []
        probe = QgsVectorLayer(str(path), path.stem, "ogr")
        if not probe.isValid():
            return []
        result: list[dict[str, str | None]] = []
        for entry in probe.dataProvider().subLayers():
            parsed = self._parse_sublayer_entry(entry)
            if parsed["name"]:
                result.append(parsed)
        return result

    @staticmethod
    def _parse_sublayer_entry(entry: str) -> dict[str, str | None]:
        tokens = [token.strip() for token in entry.split("!!::!!") if token is not None]
        if len(tokens) < 2:
            return {"name": entry.strip(), "layer_id": None}

        # OGR can emit either "id!!::!!name..." or "name!!::!!id...".
        first, second = tokens[0], tokens[1]
        if first.isdigit():
            return {"name": second, "layer_id": first}
        if second.isdigit():
            return {"name": first, "layer_id": second}

        # Fallback for providers that don't include a numeric layer id.
        return {"name": second, "layer_id": None}
