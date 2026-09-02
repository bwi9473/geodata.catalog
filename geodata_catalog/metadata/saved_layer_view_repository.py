from __future__ import annotations

from datetime import datetime, timezone

from geodata_catalog.metadata.settings_manager import SettingsManager
from geodata_catalog.models.saved_layer_view import SavedLayerView


class SavedLayerViewRepository:
    """Persistence for user-local saved layer views."""

    SETTINGS_KEY = "saved_layer_views"

    def __init__(self, settings_manager: SettingsManager) -> None:
        self._settings_manager = settings_manager

    def list_all(self) -> list[SavedLayerView]:
        values = self._settings_manager.get_json(self.SETTINGS_KEY, default=[])
        return [SavedLayerView.from_dict(item) for item in values]

    def list_by_layer(self, datasource_id: str, layer_name: str) -> list[SavedLayerView]:
        return [
            view for view in self.list_all()
            if view.datasource_id == datasource_id and view.layer_name == layer_name
        ]

    def get_by_name(self, datasource_id: str, layer_name: str, name: str) -> SavedLayerView | None:
        wanted = name.strip().casefold()
        return next(
            (view for view in self.list_by_layer(datasource_id, layer_name) if view.name.casefold() == wanted),
            None,
        )

    def upsert(self, view: SavedLayerView) -> None:
        items = self.list_all()
        existing = self.get_by_name(view.datasource_id, view.layer_name, view.name)
        view.updated_at = datetime.now(timezone.utc).isoformat()
        if existing is not None:
            view.id = existing.id
            items = [item for item in items if item.id != existing.id]
        items.append(view)
        self._settings_manager.set_json(self.SETTINGS_KEY, [item.to_dict() for item in items])