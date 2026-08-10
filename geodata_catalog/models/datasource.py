from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DatasourceType(str, Enum):
    ORACLE = "oracle"
    POSTGIS = "postgis"
    GEOJSON = "geojson"
    KML = "kml"
    REST = "rest"


class AuthType(str, Enum):
    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"


@dataclass(slots=True)
class Datasource:
    id: str
    name: str
    datasource_type: DatasourceType
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "datasource_type": self.datasource_type.value,
            "config": self.config,
            "enabled": self.enabled,
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "Datasource":
        return Datasource(
            id=value["id"],
            name=value["name"],
            datasource_type=DatasourceType(value["datasource_type"]),
            config=value.get("config", {}),
            enabled=value.get("enabled", True),
        )
