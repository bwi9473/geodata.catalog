from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_FLIGHT_LEVEL_PRESETS: list[dict[str, int | str]] = [
    {"name": "LOWER", "lower": 0, "upper": 355},
    {"name": "HIGH", "lower": 355, "upper": 999},
]


class SystemConfigurationRepository:
    """Persistence for system-level plugin configuration values."""

    FILE_NAME = "system_configuration.json"

    def __init__(self, settings_manager) -> None:
        self._settings_manager = settings_manager

    def load(self) -> dict[str, Any]:
        payload = self._read_payload()
        normalized = self._normalize_payload(payload)
        if payload != normalized:
            self.save(normalized)
        return normalized

    def load_flight_level_presets(self) -> list[dict[str, int | str]]:
        payload = self.load()
        return payload["flight_level_presets"]

    def save(self, payload: dict[str, Any]) -> None:
        file_path = self._file_path()
        if file_path is None:
            return
        normalized = self._normalize_payload(payload)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")

    def _read_payload(self) -> dict[str, Any]:
        file_path = self._file_path()
        if file_path is None:
            return self._default_payload()
        if not file_path.exists():
            default_payload = self._default_payload()
            self.save(default_payload)
            return default_payload
        try:
            raw = file_path.read_text(encoding="utf-8")
            if not raw.strip():
                return self._default_payload()
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (OSError, ValueError, TypeError):
            pass
        return self._default_payload()

    def _file_path(self) -> Path | None:
        return self._settings_manager.sibling_file_path(self.FILE_NAME)

    @staticmethod
    def _default_payload() -> dict[str, Any]:
        return {"flight_level_presets": deepcopy(DEFAULT_FLIGHT_LEVEL_PRESETS)}

    @classmethod
    def _normalize_payload(cls, payload: Any) -> dict[str, Any]:
        normalized: dict[str, Any] = dict(payload) if isinstance(payload, dict) else {}
        normalized["flight_level_presets"] = cls._normalize_presets(
            normalized.get("flight_level_presets")
        )
        return normalized

    @staticmethod
    def _normalize_presets(raw_presets: Any) -> list[dict[str, int | str]]:
        if not isinstance(raw_presets, list):
            return deepcopy(DEFAULT_FLIGHT_LEVEL_PRESETS)

        normalized: list[dict[str, int | str]] = []
        for item in raw_presets:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            try:
                lower = int(item.get("lower", 0))
                upper = int(item.get("upper", 999))
            except (TypeError, ValueError):
                continue

            lower = max(0, min(999, lower))
            upper = max(0, min(999, upper))
            if lower > upper:
                lower, upper = upper, lower

            normalized.append({"name": name, "lower": lower, "upper": upper})

        return normalized or deepcopy(DEFAULT_FLIGHT_LEVEL_PRESETS)
