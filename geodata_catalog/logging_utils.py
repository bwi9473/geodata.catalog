from __future__ import annotations

from enum import Enum
from typing import Optional

try:
    from qgis.core import Qgis, QgsMessageLog
except ImportError:  # pragma: no cover
    Qgis = None
    QgsMessageLog = None


class LogLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class PluginLogger:
    """Centralized logging for GeoData Catalog plugin."""

    def __init__(self, tag: str = "GeoData Catalog") -> None:
        self._tag = tag

    def log(self, message: str, level: LogLevel = LogLevel.INFO) -> None:
        if QgsMessageLog is None or Qgis is None:  # pragma: no cover
            return
        qgis_level = {
            LogLevel.INFO: Qgis.Info,
            LogLevel.WARNING: Qgis.Warning,
            LogLevel.ERROR: Qgis.Critical,
        }[level]
        QgsMessageLog.logMessage(message, self._tag, qgis_level)

    def info(self, message: str) -> None:
        self.log(message, LogLevel.INFO)

    def warning(self, message: str) -> None:
        self.log(message, LogLevel.WARNING)

    def error(self, message: str) -> None:
        self.log(message, LogLevel.ERROR)
