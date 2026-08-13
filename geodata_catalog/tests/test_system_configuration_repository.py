import json

from geodata_catalog.metadata.settings_manager import SettingsManager
from geodata_catalog.metadata.system_configuration_repository import (
    DEFAULT_FLIGHT_LEVEL_PRESETS,
    DEFAULT_UI_COLORS,
    SystemConfigurationRepository,
)


class InMemorySettings:
    def __init__(self):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value

    def value(self, key, default=None):
        return self.values.get(key, default)

    def remove(self, key):
        self.values.pop(key, None)


def test_load_presets_uses_defaults_without_storage_file_path():
    settings = SettingsManager(settings=InMemorySettings())
    repository = SystemConfigurationRepository(settings)

    presets = repository.load_flight_level_presets()

    assert presets == DEFAULT_FLIGHT_LEVEL_PRESETS


def test_load_ui_colors_uses_defaults_without_storage_file_path():
    settings = SettingsManager(settings=InMemorySettings())
    repository = SystemConfigurationRepository(settings)

    colors = repository.load_ui_colors()

    assert colors == DEFAULT_UI_COLORS


def test_load_creates_system_configuration_file_with_defaults(tmp_path):
    settings_file_path = tmp_path / "config.json"
    settings = SettingsManager(
        settings=InMemorySettings(),
        storage_file_path=str(settings_file_path),
    )
    repository = SystemConfigurationRepository(settings)

    presets = repository.load_flight_level_presets()
    system_config_file = tmp_path / SystemConfigurationRepository.FILE_NAME

    assert presets == DEFAULT_FLIGHT_LEVEL_PRESETS
    assert system_config_file.exists()

    payload = json.loads(system_config_file.read_text(encoding="utf-8"))
    assert payload["flight_level_presets"] == DEFAULT_FLIGHT_LEVEL_PRESETS


def test_load_invalid_config_falls_back_to_defaults(tmp_path):
    settings_file_path = tmp_path / "config.json"
    settings = SettingsManager(
        settings=InMemorySettings(),
        storage_file_path=str(settings_file_path),
    )
    repository = SystemConfigurationRepository(settings)

    system_config_file = tmp_path / SystemConfigurationRepository.FILE_NAME
    system_config_file.write_text("{ invalid", encoding="utf-8")

    presets = repository.load_flight_level_presets()

    assert presets == DEFAULT_FLIGHT_LEVEL_PRESETS


def test_load_custom_presets_and_normalize_bounds(tmp_path):
    settings_file_path = tmp_path / "config.json"
    settings = SettingsManager(
        settings=InMemorySettings(),
        storage_file_path=str(settings_file_path),
    )
    repository = SystemConfigurationRepository(settings)

    system_config_file = tmp_path / SystemConfigurationRepository.FILE_NAME
    system_config_file.write_text(
        json.dumps(
            {
                "flight_level_presets": [
                    {"name": "MID", "lower": 450, "upper": 350},
                    {"name": "UPPER", "lower": 700, "upper": 1200},
                ]
            }
        ),
        encoding="utf-8",
    )

    presets = repository.load_flight_level_presets()

    assert presets == [
        {"name": "MID", "lower": 350, "upper": 450},
        {"name": "UPPER", "lower": 700, "upper": 999},
    ]


def test_load_ui_colors_normalizes_invalid_values(tmp_path):
    settings_file_path = tmp_path / "config.json"
    settings = SettingsManager(
        settings=InMemorySettings(),
        storage_file_path=str(settings_file_path),
    )
    repository = SystemConfigurationRepository(settings)

    system_config_file = tmp_path / SystemConfigurationRepository.FILE_NAME
    system_config_file.write_text(
        json.dumps(
            {
                "ui_colors": {
                    "primary": "#123abc",
                    "text": "invalid",
                    "border": 123,
                }
            }
        ),
        encoding="utf-8",
    )

    colors = repository.load_ui_colors()

    assert colors["primary"] == "#123abc"
    assert colors["text"] == DEFAULT_UI_COLORS["text"]
    assert colors["border"] == DEFAULT_UI_COLORS["border"]
