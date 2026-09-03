from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LayerConfig:
    """Per-layer display and search configuration stored in layer_config.json."""

    datasource_id: str
    layer_name: str
    layername: str | None = None
    category_label: str | None = None
    label_column: str | None = None
    svg_marker_path: str | None = None
    enable_fl_filter: bool = True
    field_columns: list[dict[str, str | bool]] = field(default_factory=list)
    key_column: str | None = None

    def key(self) -> str:
        return f"{self.datasource_id}:{self.layer_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "datasource_id": self.datasource_id,
            "layer_name": self.layer_name,
            "layername": self.layername,
            "category_label": self.category_label,
            "label_column": self.label_column,
            "svg_marker_path": self.svg_marker_path,
            "enable_fl_filter": self.enable_fl_filter,
            "field_columns": self.field_columns,
            "key_column": self.key_column,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "LayerConfig":
        field_columns = data.get("field_columns") or LayerConfig._legacy_field_columns(data)
        return LayerConfig(
            datasource_id=data["datasource_id"],
            layer_name=data["layer_name"],
            layername=data.get("layername"),
            category_label=data.get("category_label"),
            label_column=data.get("label_column"),
            svg_marker_path=data.get("svg_marker_path"),
            enable_fl_filter=bool(data.get("enable_fl_filter", True)),
            field_columns=field_columns,
            key_column=data.get("key_column"),
        )

    @staticmethod
    def _legacy_field_columns(data: dict[str, Any]) -> list[dict[str, str | bool]]:
        columns: dict[str, dict[str, str | bool]] = {}
        for source, selection in (
            (data.get("searchable_columns", []), "search"),
            (data.get("view_columns", []), "export"),
        ):
            for column in source:
                name = str(column.get("name", "")).strip()
                if not name:
                    continue
                entry = columns.setdefault(
                    name,
                    {
                        "name": name,
                        "label": str(column.get("label", name)),
                        "type": str(column.get("type", "varchar")),
                        "input_type": str(column.get("input_type", "text field")),
                        "position": len(columns),
                    },
                )
                entry[selection] = True
                if selection == "search":
                    entry["use_distinct"] = bool(column.get("use_distinct", False))
                    if column.get("filter_by"):
                        entry["filter_by"] = str(column["filter_by"])
        key_column = data.get("key_column")
        if key_column and key_column in columns:
            columns[str(key_column)]["key"] = True
        return list(columns.values())

    @property
    def searchable_columns(self) -> list[dict[str, str | bool]]:
        return [
            self._runtime_column(column)
            for column in self.field_columns
            if bool(column.get("search", False))
        ]

    @property
    def view_columns(self) -> list[dict[str, str]]:
        return [
            {
                "name": str(column["name"]),
                "label": str(column.get("label", column["name"])),
                "type": str(column.get("type", "varchar")),
                "input_type": str(column.get("input_type", "text field")),
            }
            for column in self.field_columns
            if bool(column.get("export", False))
        ]

    @staticmethod
    def _runtime_column(column: dict[str, str | bool]) -> dict[str, str | bool]:
        return {
            key: column[key]
            for key in ("name", "label", "type", "input_type", "use_distinct", "filter_by")
            if key in column
        }


class LayerConfigRepository:
    """Stores per-layer configuration in a dedicated ``layer_config.json`` file.

    This file is kept separate from the main ``config.json`` (datasources /
    business-layer metadata) so that connection settings and display/search
    configuration can be managed independently.
    """

    def __init__(self, file_path: Path | None) -> None:
        self._file_path = file_path

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def get(self, datasource_id: str, layer_name: str) -> LayerConfig | None:
        for cfg in self._load():
            if cfg.datasource_id == datasource_id and cfg.layer_name == layer_name:
                return cfg
        return None

    def list_by_datasource(self, datasource_id: str) -> list[LayerConfig]:
        return [cfg for cfg in self._load() if cfg.datasource_id == datasource_id]

    def list_all(self) -> list[LayerConfig]:
        return self._load()

    def save(self, config: LayerConfig) -> None:
        configs = self._load()
        replaced = False
        for i, cfg in enumerate(configs):
            if cfg.key() == config.key():
                configs[i] = config
                replaced = True
                break
        if not replaced:
            configs.append(config)
        self._persist(configs)

    def delete(self, datasource_id: str, layer_name: str) -> None:
        configs = [
            cfg
            for cfg in self._load()
            if not (cfg.datasource_id == datasource_id and cfg.layer_name == layer_name)
        ]
        self._persist(configs)

    def delete_by_datasource(self, datasource_id: str) -> None:
        configs = [cfg for cfg in self._load() if cfg.datasource_id != datasource_id]
        self._persist(configs)

    @property
    def file_path(self) -> Path | None:
        return self._file_path

    # ------------------------------------------------------------------ #
    # Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _load(self) -> list[LayerConfig]:
        if self._file_path is None or not self._file_path.exists():
            return []
        try:
            raw = self._file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, list):
                return []
            return [LayerConfig.from_dict(item) for item in data]
        except Exception:
            return []

    def _persist(self, configs: list[LayerConfig]) -> None:
        if self._file_path is None:
            return
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            [c.to_dict() for c in configs],
            indent=2,
            ensure_ascii=False,
        )
        self._file_path.write_text(payload, encoding="utf-8")
