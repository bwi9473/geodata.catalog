from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LayerDefinition:
    datasource_id: str
    layer_name: str
    display_name: str
    provider_key: str
    provider_uri: str
    business_group: str = "General"
    geometry_type: str | None = None
    srid: int | None = None
    feature_count: int | None = None
    geometry_column: str | None = None
    owner: str | None = None
    object_name: str | None = None
    technical_name: str | None = None
    default_crs: str | None = None
    default_style_file: str | None = None
    filter_expression: str | None = None
    label_column: str | None = None
    searchable_columns: list[dict[str, str]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        return f"{self.datasource_id}:{self.layer_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "datasource_id": self.datasource_id,
            "layer_name": self.layer_name,
            "display_name": self.display_name,
            "provider_key": self.provider_key,
            "provider_uri": self.provider_uri,
            "business_group": self.business_group,
            "geometry_type": self.geometry_type,
            "srid": self.srid,
            "feature_count": self.feature_count,
            "geometry_column": self.geometry_column,
            "owner": self.owner,
            "object_name": self.object_name,
            "technical_name": self.technical_name,
            "default_crs": self.default_crs,
            "default_style_file": self.default_style_file,
            "filter_expression": self.filter_expression,
            "label_column": self.label_column,
            "searchable_columns": self.searchable_columns,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "LayerDefinition":
        return LayerDefinition(
            datasource_id=value["datasource_id"],
            layer_name=value["layer_name"],
            display_name=value.get("display_name", value["layer_name"]),
            provider_key=value["provider_key"],
            provider_uri=value["provider_uri"],
            business_group=value.get("business_group", "General"),
            geometry_type=value.get("geometry_type"),
            srid=value.get("srid"),
            feature_count=value.get("feature_count"),
            geometry_column=value.get("geometry_column"),
            owner=value.get("owner"),
            object_name=value.get("object_name"),
            technical_name=value.get("technical_name"),
            default_crs=value.get("default_crs"),
            default_style_file=value.get("default_style_file"),
            filter_expression=value.get("filter_expression"),
            label_column=value.get("label_column"),
            searchable_columns=value.get("searchable_columns"),
            metadata=value.get("metadata", {}),
        )
