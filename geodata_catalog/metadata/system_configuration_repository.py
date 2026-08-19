from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_FLIGHT_LEVEL_PRESETS: list[dict[str, int | str]] = [
    {"name": "LOWER", "lower": 0, "upper": 355},
    {"name": "HIGH", "lower": 355, "upper": 999},
]

DEFAULT_UI_COLORS: dict[str, str] = {
    "primary": "#59A947",
    "primary_text": "#FFFFFF",
    "panel_background": "#F7F9FC",
    "window_background": "#FFFFFF",
    "text": "#1E293B",
    "border": "#D7DEE8",
    "header_background": "#EEF3FA",
    "header_text": "#0F172A",
}


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

    def load_ui_colors(self) -> dict[str, str]:
        payload = self.load()
        return payload["ui_colors"]

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
        return {
            "flight_level_presets": deepcopy(DEFAULT_FLIGHT_LEVEL_PRESETS),
            "ui_colors": deepcopy(DEFAULT_UI_COLORS),
        }

    @classmethod
    def _normalize_payload(cls, payload: Any) -> dict[str, Any]:
        normalized: dict[str, Any] = dict(payload) if isinstance(payload, dict) else {}
        normalized["flight_level_presets"] = cls._normalize_presets(
            normalized.get("flight_level_presets")
        )
        normalized["ui_colors"] = cls._normalize_ui_colors(normalized.get("ui_colors"))
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

    @staticmethod
    def _normalize_ui_colors(raw_colors: Any) -> dict[str, str]:
        if not isinstance(raw_colors, dict):
            return deepcopy(DEFAULT_UI_COLORS)

        normalized = deepcopy(DEFAULT_UI_COLORS)
        for key in DEFAULT_UI_COLORS:
            value = raw_colors.get(key)
            if not isinstance(value, str):
                continue
            candidate = value.strip()
            if len(candidate) == 7 and candidate.startswith("#"):
                hex_part = candidate[1:]
                if all(ch in "0123456789abcdefABCDEF" for ch in hex_part):
                    normalized[key] = candidate
        return normalized
