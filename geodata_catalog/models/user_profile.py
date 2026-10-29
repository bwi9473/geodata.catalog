from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class UserProfile:
    id: str
    name: str
    role: str = "user"
    visible_layer_ids: list[str] | None = None

    @property
    def is_developer(self) -> bool:
        return self.role == "developer"

    def can_view(self, layer_id: str) -> bool:
        return (
            self.is_developer
            or self.visible_layer_ids is None
            or layer_id in self.visible_layer_ids
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "visible_layer_ids": self.visible_layer_ids,
        }
