from .plugin import GeoDataCatalogPlugin


def classFactory(iface):
    """QGIS plugin entry point."""
    return GeoDataCatalogPlugin(iface)
