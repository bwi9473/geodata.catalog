from __future__ import annotations

from geodata_catalog.exceptions import LayerLoadException
from geodata_catalog.logging_utils import PluginLogger
from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.services.style_service import StyleService

try:
    from qgis.core import (
        QgsCoordinateReferenceSystem,
        QgsPalLayerSettings,
        QgsProject,
        QgsTextFormat,
        QgsVectorLayerSimpleLabeling,
    )
except ImportError:  # pragma: no cover
    QgsCoordinateReferenceSystem = None
    QgsPalLayerSettings = None
    QgsProject = None
    QgsTextFormat = None
    QgsVectorLayerSimpleLabeling = None


class QgisLoaderService:
    """Handles loading and registration of layers into QGIS project."""

    def __init__(
        self,
        style_service: StyleService,
        logger: PluginLogger,
        project=None,
    ) -> None:
        self._style_service = style_service
        self._logger = logger
        self._project = project or (QgsProject.instance() if QgsProject else None)

    def load_layer(self, layer_definition: LayerDefinition, connector) -> object:
        self._logger.info(
            f"Loading layer '{layer_definition.display_name}' "
            f"(provider: {layer_definition.provider_key}, "
            f"uri: {layer_definition.provider_uri})"
        )
        try:
            layer = connector.load_layer(
                layer_definition.layer_name,
                key_column=layer_definition.metadata.get("key_column"),
            )
        except Exception as exc:
            self._logger.error(
                f"Connector failed to load layer '{layer_definition.display_name}': {exc}"
            )
            raise LayerLoadException(
                f"Failed to create layer '{layer_definition.display_name}': {exc}"
            ) from exc

        if not layer:
            self._logger.error(
                f"Connector returned None for layer '{layer_definition.display_name}'."
            )
            raise LayerLoadException(
                f"Layer '{layer_definition.display_name}' creation returned None."
            )

        if not layer.isValid():
            error_msg = "No error details available"
            if hasattr(layer, "error"):
                try:
                    error_msg = layer.error().summary()
                except Exception:
                    pass
            self._logger.error(
                f"Layer '{layer_definition.display_name}' is invalid. Error: {error_msg}"
            )
            raise LayerLoadException(
                f"Layer '{layer_definition.display_name}' failed validation: {error_msg}"
            )

        self._logger.info(f"Layer valid, assigning CRS and style for '{layer_definition.display_name}'")
        if hasattr(layer, "setName"):
            try:
                layer.setName(layer_definition.display_name)
            except Exception as exc:
                self._logger.warning(
                    f"Unable to set layer name to '{layer_definition.display_name}': {exc}"
                )
        self._assign_crs(layer, layer_definition.default_crs)
        self._apply_filter(layer, layer_definition.filter_expression)
        self._apply_labels(layer, layer_definition.label_column)
        self._style_service.apply_default_style(layer, layer_definition.default_style_file)
        self._tag_layer_source(layer, layer_definition)

        if self._project is None:  # pragma: no cover
            raise LayerLoadException("QGIS project instance is not available.")

        self._logger.info(f"Adding layer '{layer_definition.display_name}' to QGIS project")
        self._project.addMapLayer(layer)
        self._logger.info(f"Layer successfully loaded: {layer_definition.display_name}")
        return layer

    def _assign_crs(self, layer, crs: str | None) -> None:
        if not crs or QgsCoordinateReferenceSystem is None:
            return
        qgs_crs = QgsCoordinateReferenceSystem(crs)
        if qgs_crs.isValid():
            layer.setCrs(qgs_crs)
        else:
            self._logger.warning(f"Invalid CRS '{crs}' for layer '{layer.name()}'.")

    def _apply_filter(self, layer, filter_expression: str | None) -> None:
        if not filter_expression:
            return
        if hasattr(layer, "setSubsetString"):
            layer.setSubsetString(filter_expression)
            self._logger.info(f"Applied layer filter: {filter_expression}")

    def _apply_labels(self, layer, label_column: str | None) -> None:
        if not label_column or QgsPalLayerSettings is None:
            return
        if not hasattr(layer, "setLabeling"):
            return
        settings = QgsPalLayerSettings()
        settings.fieldName = label_column
        settings.isExpression = False
        settings.enabled = True
        labeling = QgsVectorLayerSimpleLabeling(settings)
        layer.setLabeling(labeling)
        layer.setLabelsEnabled(True)
        if hasattr(layer, "triggerRepaint"):
            layer.triggerRepaint()
        self._logger.info(f"Applied label column '{label_column}' to layer '{layer.name()}'")

    def _tag_layer_source(self, layer, layer_definition) -> None:
        """Store source identifiers as custom properties so the toolbox can look up layer config."""
        if not hasattr(layer, "setCustomProperty"):
            return
        try:
            layer.setCustomProperty("geodata_catalog/datasource_id", layer_definition.datasource_id)
            layer.setCustomProperty("geodata_catalog/source_layer_name", layer_definition.layer_name)
            layer.setCustomProperty(
                "geodata_catalog/key_column", layer_definition.metadata.get("key_column")
            )
        except Exception as exc:
            self._logger.warning(f"Could not tag layer source properties: {exc}")
