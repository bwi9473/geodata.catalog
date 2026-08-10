from pathlib import Path

# QGIS loads this folder as package "geodata_catalog".
# The implementation lives in the nested "geodata_catalog/" directory.
_THIS_DIR = Path(__file__).resolve().parent
_NESTED_SRC = _THIS_DIR / "geodata_catalog"
if _NESTED_SRC.exists() and "__path__" in dir():
    __path__.append(str(_NESTED_SRC))

from geodata_catalog.plugin import GeoDataCatalogPlugin


def classFactory(iface):
    """QGIS plugin entry point for workspace-root installs."""
    return GeoDataCatalogPlugin(iface)
