from geodata_catalog.metadata.datasource_repository import DatasourceRepository
from geodata_catalog.metadata.settings_manager import SettingsManager
from geodata_catalog.models.datasource import Datasource, DatasourceType


class InMemorySettings:
    def __init__(self):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value

    def value(self, key, default=None):
        return self.values.get(key, default)

    def remove(self, key):
        self.values.pop(key, None)


def test_datasource_repository_upsert_and_get():
    settings = SettingsManager(settings=InMemorySettings())
    repository = DatasourceRepository(settings)

    datasource = Datasource(
        id="ds-1",
        name="Oracle Source",
        datasource_type=DatasourceType.ORACLE,
        config={"host": "localhost"},
    )

    repository.upsert(datasource)

    result = repository.get_by_id("ds-1")
    assert result is not None
    assert result.name == "Oracle Source"
    assert result.datasource_type is DatasourceType.ORACLE


def test_datasource_repository_delete():
    settings = SettingsManager(settings=InMemorySettings())
    repository = DatasourceRepository(settings)

    repository.upsert(
        Datasource(
            id="ds-1",
            name="A",
            datasource_type=DatasourceType.GEOJSON,
            config={},
        )
    )
    repository.delete("ds-1")

    assert repository.get_by_id("ds-1") is None
