from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class SavedLayerView:
    """A named, user-local filter and grouping state for one catalog layer."""

    datasource_id: str
    layer_name: str
    layer_display_name: str
    name: str
    filter_state: dict[str, Any]
    grouping: dict[str, str]
    updated_at: str
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid4())
        if not self.updated_at:
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "datasource_id": self.datasource_id,
            "layer_name": self.layer_name,
            "layer_display_name": self.layer_display_name,
            "name": self.name,
            "filter_state": self.filter_state,
            "grouping": self.grouping,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "SavedLayerView":
        return SavedLayerView(
            id=str(value.get("id", "")),
            datasource_id=str(value["datasource_id"]),
            layer_name=str(value["layer_name"]),
            layer_display_name=str(value.get("layer_display_name", value["layer_name"])),
            name=str(value["name"]),
            filter_state=dict(value.get("filter_state", {})),
            grouping=dict(value.get("grouping", {})),
            updated_at=str(value.get("updated_at", "")),
        )