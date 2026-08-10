from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from qgis.PyQt.QtCore import QSettings, QStandardPaths
except ImportError:  # pragma: no cover
    QSettings = None
    QStandardPaths = None

from geodata_catalog.exceptions import ConfigurationException


class SettingsManager:
    """Repository-facing adapter over QGIS settings."""

    def __init__(
        self,
        namespace: str = "GeoDataCatalog",
        settings: Any | None = None,
        storage_file_path: str | None = None,
    ) -> None:
        self._namespace = namespace
        if settings is not None:
            self._settings = settings
            # Test mode / injected settings mode: skip filesystem persistence by default.
            self._storage_file_path: Path | None = (
                Path(storage_file_path) if storage_file_path else None
            )
        elif QSettings is not None:
            self._settings = QSettings()
            self._storage_file_path = (
                Path(storage_file_path) if storage_file_path else self._resolve_default_file_path()
            )
        else:  # pragma: no cover
            raise ConfigurationException("QSettings is not available outside QGIS runtime.")

        self._file_store = self._load_file_store()

    def _key(self, key: str) -> str:
        return f"{self._namespace}/{key}"

    def set_json(self, key: str, value: Any) -> None:
        self._file_store[key] = value
        self._persist_file_store()
        self._settings.setValue(self._key(key), json.dumps(value))

    def get_json(self, key: str, default: Any) -> Any:
        if key in self._file_store:
            return self._file_store.get(key, default)

        raw = self._settings.value(self._key(key), None)
        if raw in (None, ""):
            return default
        if isinstance(raw, (dict, list)):
            self._file_store[key] = raw
            self._persist_file_store()
            return raw
        try:
            parsed = json.loads(raw)
            self._file_store[key] = parsed
            self._persist_file_store()
            return parsed
        except (TypeError, ValueError) as exc:
            raise ConfigurationException(f"Invalid settings payload for key '{key}'.") from exc

    def remove(self, key: str) -> None:
        self._file_store.pop(key, None)
        self._persist_file_store()
        self._settings.remove(self._key(key))

    def _resolve_default_file_path(self) -> Path:
        base_dir: Path
        if QStandardPaths is not None:
            # PyQt5 (QGIS 3.x): QStandardPaths.AppDataLocation
            # PyQt6 (QGIS 4.x): QStandardPaths.StandardLocation.AppDataLocation
            location = getattr(
                QStandardPaths,
                "AppDataLocation",
                getattr(
                    getattr(QStandardPaths, "StandardLocation", None),
                    "AppDataLocation",
                    None,
                ),
            )
            app_data = QStandardPaths.writableLocation(location) if location is not None else ""
            if app_data:
                base_dir = Path(app_data)
            else:
                base_dir = Path.home() / ".geodata_catalog"
        else:  # pragma: no cover
            base_dir = Path.home() / ".geodata_catalog"
        return base_dir / self._namespace / "config.json"

    def sibling_file_path(self, filename: str) -> "Path | None":
        """Return a Path for a sibling file next to the main config.json.

        Returns ``None`` when running in test / injected-settings mode without
        a real storage file path.
        """
        if self._storage_file_path is None:
            return None
        return self._storage_file_path.parent / filename

    def _load_file_store(self) -> dict[str, Any]:
        if self._storage_file_path is None:
            return {}
        if not self._storage_file_path.exists():
            return {}
        try:
            raw = self._storage_file_path.read_text(encoding="utf-8")
            if not raw.strip():
                return {}
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ConfigurationException("Settings file payload must be a JSON object.")
            return payload
        except (OSError, ValueError, TypeError) as exc:
            raise ConfigurationException(
                f"Failed to read settings file: {self._storage_file_path}"
            ) from exc

    def _persist_file_store(self) -> None:
        if self._storage_file_path is None:
            return
        try:
            self._storage_file_path.parent.mkdir(parents=True, exist_ok=True)
            self._storage_file_path.write_text(
                json.dumps(self._file_store, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            raise ConfigurationException(
                f"Failed to write settings file: {self._storage_file_path}"
            ) from exc
