from __future__ import annotations

from collections.abc import Iterable

from geodata_catalog.models.datasource import Datasource
from geodata_catalog.metadata.settings_manager import SettingsManager


class DatasourceRepository:
    """Persistence for datasource definitions."""

    SETTINGS_KEY = "datasources"

    def __init__(self, settings_manager: SettingsManager) -> None:
        self._settings_manager = settings_manager

    def list_all(self) -> list[Datasource]:
        values = self._settings_manager.get_json(self.SETTINGS_KEY, default=[])
        return [Datasource.from_dict(item) for item in values]

    def get_by_id(self, datasource_id: str) -> Datasource | None:
        for datasource in self.list_all():
            if datasource.id == datasource_id:
                return datasource
        return None

    def upsert(self, datasource: Datasource) -> None:
        items = self.list_all()
        replaced = False
        for index, item in enumerate(items):
            if item.id == datasource.id:
                items[index] = datasource
                replaced = True
                break
        if not replaced:
            items.append(datasource)
        self._save(items)

    def delete(self, datasource_id: str) -> None:
        items = [item for item in self.list_all() if item.id != datasource_id]
        self._save(items)

    def bulk_replace(self, datasources: Iterable[Datasource]) -> None:
        self._save(list(datasources))

    def _save(self, datasources: list[Datasource]) -> None:
        payload = [datasource.to_dict() for datasource in datasources]
        self._settings_manager.set_json(self.SETTINGS_KEY, payload)
