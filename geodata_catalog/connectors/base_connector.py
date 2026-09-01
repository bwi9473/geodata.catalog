from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from geodata_catalog.exceptions import LayerLoadException
from geodata_catalog.models.layer_definition import LayerDefinition


class BaseConnector(ABC):
    """Base connector contract for all datasource types."""

    @abstractmethod
    def get_layers(self) -> list[LayerDefinition]:
        """Discover and return available layers."""

    @abstractmethod
    def get_layer_metadata(self, layer_name: str) -> LayerDefinition:
        """Return metadata for a specific layer."""

    @abstractmethod
    def load_layer(self, layer_name: str, key_column: str | None = None):
        """Create and return a QgsVectorLayer instance."""

    @abstractmethod
    def test_connection(self) -> bool:
        """Validate connectivity to the source."""

    @staticmethod
    def _label_column_from_config(config: dict[str, Any]) -> str | None:
        """Return the optional label_column setting from a datasource config dict."""
        value = config.get("label_column")
        return str(value).strip() if value else None

    @staticmethod
    def _raise_if_empty_layer(metadata: LayerDefinition) -> None:
        """Raise a clear error before QGIS tries to load an empty source."""
        if metadata.feature_count == 0:
            raise LayerLoadException(
                f"Layer '{metadata.display_name}' is not loaded because it contains no data."
            )
