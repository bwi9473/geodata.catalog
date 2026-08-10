class GeoDataCatalogException(Exception):
    """Base exception for all plugin errors."""


class DatasourceConnectionException(GeoDataCatalogException):
    """Raised when a datasource connection cannot be established."""


class LayerLoadException(GeoDataCatalogException):
    """Raised when a layer cannot be loaded into QGIS."""


class ConfigurationException(GeoDataCatalogException):
    """Raised for invalid or missing configuration values."""
