from __future__ import annotations

from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.metadata.settings_manager import SettingsManager


class LayerRepository:
    """Persistence for business-layer catalog metadata."""

    SETTINGS_KEY = "layers"

    def __init__(self, settings_manager: SettingsManager) -> None:
        self._settings_manager = settings_manager

    def list_all(self) -> list[LayerDefinition]:
        values = self._settings_manager.get_json(self.SETTINGS_KEY, default=[])
        return [LayerDefinition.from_dict(item) for item in values]

    def list_by_datasource(self, datasource_id: str) -> list[LayerDefinition]:
        return [layer for layer in self.list_all() if layer.datasource_id == datasource_id]

    def upsert(self, layer: LayerDefinition) -> None:
        items = self.list_all()
        replaced = False
        for index, item in enumerate(items):
            if item.key() == layer.key():
                items[index] = layer
                replaced = True
                break
        if not replaced:
            items.append(layer)
        self._save(items)

    def delete(self, datasource_id: str, layer_name: str) -> None:
        items = [
            layer
            for layer in self.list_all()
            if not (layer.datasource_id == datasource_id and layer.layer_name == layer_name)
        ]
        self._save(items)

    def _save(self, layers: list[LayerDefinition]) -> None:
        payload = [layer.to_dict() for layer in layers]
        self._settings_manager.set_json(self.SETTINGS_KEY, payload)
