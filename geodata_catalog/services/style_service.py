from __future__ import annotations

from pathlib import Path

from geodata_catalog.logging_utils import PluginLogger

try:
    from qgis.core import QgsMarkerSymbol, QgsSvgMarkerSymbolLayer, QgsWkbTypes
except ImportError:  # pragma: no cover
    QgsMarkerSymbol = None
    QgsSvgMarkerSymbolLayer = None
    QgsWkbTypes = None


class StyleService:
    """Applies optional QML styles to loaded layers."""

    def __init__(self, logger: PluginLogger) -> None:
        self._logger = logger

    def apply_default_style(self, layer, style_file: str | None) -> None:
        if not style_file:
            return
        style_path = Path(style_file)
        if not style_path.exists():
            self._logger.warning(f"Style file not found: {style_file}")
            return
        ok, error = layer.loadNamedStyle(str(style_path))
        if not ok:
            self._logger.warning(f"Failed applying style '{style_file}': {error}")
            return
        layer.triggerRepaint()
        self._logger.info(f"Applied default style: {style_file}")

    def apply_svg_marker(self, layer, svg_path: str | None) -> None:
        """Apply a configured SVG marker to a point layer."""
        if not svg_path or QgsMarkerSymbol is None or QgsSvgMarkerSymbolLayer is None:
            return
        if QgsWkbTypes is not None and layer.geometryType() != QgsWkbTypes.PointGeometry:
            self._logger.warning(f"SVG marker ignored for non-point layer '{layer.name()}'.")
            return
        try:
            svg_layer = QgsSvgMarkerSymbolLayer.create(
                {"name": str(svg_path), "size": "3", "outline_width": "0"}
            )
            symbol = QgsMarkerSymbol.createSimple({"name": "circle", "size": "2"})
            if svg_layer is None or symbol is None or symbol.symbolLayerCount() == 0:
                return
            symbol.changeSymbolLayer(0, svg_layer)
            renderer = layer.renderer()
            if renderer is None or not hasattr(renderer, "setSymbol"):
                return
            renderer.setSymbol(symbol)
            layer.triggerRepaint()
            self._logger.info(f"Applied SVG marker: {svg_path}")
        except Exception as exc:
            self._logger.warning(f"Failed to apply SVG marker '{svg_path}': {exc}")
