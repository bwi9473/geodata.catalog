from __future__ import annotations

from pathlib import Path

from geodata_catalog.exceptions import ConfigurationException
from geodata_catalog.logging_utils import PluginLogger
from geodata_catalog.svg_markers import portable_svg_reference

try:
    from qgis.core import (
        QgsMarkerSymbol,
        QgsRenderContext,
        QgsSvgMarkerSymbolLayer,
        QgsSymbolLayerUtils,
        QgsVectorLayer,
        QgsWkbTypes,
    )
except ImportError:  # pragma: no cover
    QgsMarkerSymbol = None
    QgsRenderContext = None
    QgsSvgMarkerSymbolLayer = None
    QgsSymbolLayerUtils = None
    QgsVectorLayer = None
    QgsWkbTypes = None

try:
    from qgis.core import Qgis
except ImportError:  # pragma: no cover
    Qgis = None

try:
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QIcon
except ImportError:  # pragma: no cover
    QSize = None
    QIcon = None

# Geometry types probed (in order) when rendering a preview icon for a QML
# style, since a style file only applies cleanly to a matching geometry type.
_PREVIEW_GEOMETRIES = ("Point", "LineString", "Polygon", "NoGeometry")

# Cache of generated preview icons keyed by style file path, invalidated when
# the file's modification time changes. Populated lazily (on first UI use),
# never eagerly scanned on plugin/QGIS startup.
_PREVIEW_ICON_CACHE: dict[str, tuple[float, "QIcon"]] = {}


def _load_named_style(layer, style_path: str) -> tuple[bool, object]:
    """Normalize QGIS 3/4 loadNamedStyle return values to ``(success, error)``."""
    result = layer.loadNamedStyle(style_path)
    if isinstance(result, tuple) and len(result) == 2:
        first, second = result
        if isinstance(second, bool):
            return second, first
        if isinstance(first, bool):
            return first, second
    if isinstance(result, bool):
        return result, ""
    return bool(result), result


def list_style_files(folder: str | Path | None) -> list[tuple[str, str]]:
    """Return ``(display_name, path)`` pairs for ``.qml`` files in ``folder``.

    The folder is scanned on demand (e.g. when the layer configuration
    dialog opens) rather than at QGIS startup: listing a directory of style
    files is a cheap, near-instant filesystem operation, so there is no
    performance benefit to pre-loading it at startup and it would only
    delay plugin initialization and risk showing stale results.
    """
    if not folder:
        return []
    directory = Path(folder)
    if not directory.is_dir():
        return []
    return sorted(
        ((qml_path.stem, str(qml_path)) for qml_path in directory.glob("*.qml")),
        key=lambda pair: pair[0].casefold(),
    )


def generate_style_preview_icon(style_path: str | None, size: int = 16):
    """Render a small preview icon for a QML style file, or ``None`` if unavailable.

    Results are cached per file path (invalidated on modification time
    change) so repeated dialog opens do not re-parse the same style.
    """
    if not style_path or QIcon is None or QgsVectorLayer is None:
        return None
    path = Path(style_path)
    if not path.is_file():
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None

    cached = _PREVIEW_ICON_CACHE.get(style_path)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    icon = _render_style_preview_icon(str(path), size)
    if icon is not None:
        _PREVIEW_ICON_CACHE[style_path] = (mtime, icon)
    return icon


def _render_style_preview_icon(style_path: str, size: int):
    for geom_type in _PREVIEW_GEOMETRIES:
        probe_layer = QgsVectorLayer(f"{geom_type}?crs=EPSG:4326", "style_preview", "memory")
        if not probe_layer.isValid():
            continue
        ok, _error = _load_named_style(probe_layer, style_path)
        if not ok:
            continue
        renderer = probe_layer.renderer()
        if renderer is None or not hasattr(renderer, "symbols"):
            continue
        try:
            symbols = renderer.symbols(QgsRenderContext())
        except TypeError:  # pragma: no cover - older API signature fallback
            symbols = renderer.symbols()
        if not symbols:
            continue
        pixmap = QgsSymbolLayerUtils.symbolPreviewPixmap(symbols[0], QSize(size, size))
        if pixmap is None or pixmap.isNull():
            continue
        return QIcon(pixmap)
    return None


def _svg_marker_symbol(reference: str):
    try:
        svg_layer = QgsSvgMarkerSymbolLayer.create(
            {"name": reference, "size": "3", "outline_width": "0"}
        )
        symbol = QgsMarkerSymbol.createSimple({"name": "circle", "size": "2"})
        if svg_layer is None or symbol is None or symbol.symbolLayerCount() == 0:
            raise ConfigurationException("QGIS could not create the SVG marker symbol.")
        if not symbol.changeSymbolLayer(0, svg_layer):
            raise ConfigurationException("QGIS could not attach the SVG marker symbol layer.")
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ConfigurationException("QGIS could not create the SVG marker symbol.") from exc
    return symbol


def generate_svg_preview_icon(svg_reference: str, size: int = 16):
    """Render the same embedded SVG symbol used when loading a layer."""
    if any(api is None for api in (QIcon, QSize, QgsMarkerSymbol, QgsSvgMarkerSymbolLayer, QgsSymbolLayerUtils)):
        return None
    reference = portable_svg_reference(svg_reference)
    if not reference:
        return None
    try:
        pixmap = QgsSymbolLayerUtils.symbolPreviewPixmap(_svg_marker_symbol(reference), QSize(size, size))
        if pixmap is None or pixmap.isNull():
            raise ConfigurationException("QGIS could not render the SVG marker preview.")
        return QIcon(pixmap)
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ConfigurationException("QGIS could not render the SVG marker preview.") from exc


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
        ok, error = _load_named_style(layer, str(style_path))
        if not ok:
            self._logger.warning(f"Failed applying style '{style_file}': {error}")
            return
        layer.triggerRepaint()
        self._logger.info(f"Applied default style: {style_file}")

    def apply_svg_marker(self, layer, svg_path: str | None) -> None:
        """Apply a configured SVG marker to a point layer."""
        if not svg_path:
            return
        if QgsMarkerSymbol is None or QgsSvgMarkerSymbolLayer is None:
            self._logger.warning("SVG marker could not be applied: QGIS symbol APIs are unavailable.")
            return
        point_geometry = getattr(getattr(Qgis, "GeometryType", None), "Point", None)
        if point_geometry is None and QgsWkbTypes is not None:
            point_geometry = getattr(QgsWkbTypes, "PointGeometry", None)
        if point_geometry is None:
            self._logger.warning("SVG marker could not be applied: QGIS point geometry type is unavailable.")
            return
        if layer.geometryType() != point_geometry:
            self._logger.warning(f"SVG marker ignored for non-point layer '{layer.name()}'.")
            return
        try:
            reference = portable_svg_reference(svg_path)
            if not reference:
                return
            symbol = _svg_marker_symbol(reference)
            renderer = layer.renderer()
            if renderer is None or not hasattr(renderer, "setSymbol"):
                self._logger.warning(
                    f"SVG marker not applied to '{layer.name()}': its renderer does not support a single symbol."
                )
                return
            renderer.setSymbol(symbol)
            layer.triggerRepaint()
            self._logger.info(f"Applied embedded SVG marker to '{layer.name()}'.")
        except (ConfigurationException, RuntimeError, TypeError, ValueError) as exc:
            self._logger.warning(f"Failed to apply SVG marker to '{layer.name()}': {exc}")
