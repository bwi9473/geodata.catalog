from __future__ import annotations

from pathlib import Path

from geodata_catalog.logging_utils import PluginLogger


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
