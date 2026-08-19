# Development Guide

This guide covers how to run tests, add a new connector, extend models, and contribute to the GeoData Catalog plugin.

---

## Running Tests

Tests are located in `geodata_catalog/tests/`. They use `pytest` and do **not** require a running QGIS instance — all QGIS objects are replaced by lightweight fakes.

### Install test dependencies

```bash
pip install -r requirements-dev.txt
```

`requirements-dev.txt` contains:

```
pytest>=8.0.0
requests>=2.32.0
python-oracledb>=2.2.0
```

### Run all tests

```bash
pytest geodata_catalog/tests/
```

### Run a specific test file

```bash
pytest geodata_catalog/tests/test_kml_connector.py
```

### Run with verbose output

```bash
pytest -v geodata_catalog/tests/
```

### Run with coverage

```bash
pip install pytest-cov
pytest --cov=geodata_catalog --cov-report=term-missing geodata_catalog/tests/
```

---

## Test Strategy

Each test module mocks the QGIS runtime so tests can run with plain Python. The patterns used are:

### Faking QGIS layers

```python
class FakeLayer:
    def __init__(self, valid=True):
        self._valid = valid

    def isValid(self):
        return self._valid

    def setCrs(self, crs):
        pass

    def name(self):
        return "Fake Layer"
```

### Faking the QGIS project

```python
class FakeProject:
    def __init__(self):
        self.layers = []

    def addMapLayer(self, layer):
        self.layers.append(layer)
```

### Monkeypatching connectors

Use `pytest`'s built-in `monkeypatch` fixture to replace internal methods:

```python
def test_something(monkeypatch):
    connector = KmlConnector("ds-1", {"path": "C:/data/file.kml"})
    monkeypatch.setattr(connector, "_resolve_path", lambda: Path("C:/data/file.kml"))
    monkeypatch.setattr(connector, "_discover_sublayers", lambda path: [
        {"name": "Aerodromes", "layer_id": "1"}
    ])
    layers = connector.get_layers()
    assert len(layers) == 1
```

---

## Adding a New Connector

To support a new datasource type, you need to:

1. Add a value to `DatasourceType` in `models/datasource.py`
2. Create a new connector class in `connectors/`
3. Register the connector in `DatasourceService`
4. Register the connector in `connectors/__init__.py`
5. Add a UI entry in `CatalogDockWidget`
6. Write tests

The steps below walk through a concrete example: adding a **GeoPackage** connector.

---

### Step 1 — Add `DatasourceType.GEOPACKAGE`

**File:** `geodata_catalog/models/datasource.py`

```python
class DatasourceType(str, Enum):
    ORACLE = "oracle"
    GEOJSON = "geojson"
    KML = "kml"
    REST = "rest"
    GEOPACKAGE = "geopackage"   # ← add this
```

> **Documentation update:** After adding this, update the [Supported Datasource Types table](index.md) and create a new section in [Adding Sources](adding-sources.md).

---

### Step 2 — Create `connectors/geopackage_connector.py`

Every connector must subclass `BaseConnector` and implement four methods.

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from geodata_catalog.connectors.base_connector import BaseConnector
from geodata_catalog.exceptions import ConfigurationException, LayerLoadException
from geodata_catalog.models.layer_definition import LayerDefinition

try:
    from qgis.core import QgsVectorLayer
except ImportError:
    QgsVectorLayer = None


class GeoPackageConnector(BaseConnector):
    """Connector for local GeoPackage (.gpkg) files."""

    def __init__(self, datasource_id: str, config: dict[str, Any]) -> None:
        self._datasource_id = datasource_id
        self._config = config

    def get_layers(self) -> list[LayerDefinition]:
        path = self._resolve_path()
        sublayers = self._discover_sublayers(path)
        return [
            LayerDefinition(
                datasource_id=self._datasource_id,
                layer_name=sublayer,
                display_name=sublayer,
                provider_key="ogr",
                provider_uri=f"{path}|layername={sublayer}",
                business_group="File Sources",
                default_crs="EPSG:4326",
                technical_name=f"{path}:{sublayer}",
                metadata={"path": str(path), "type": "GeoPackage"},
            )
            for sublayer in sublayers
        ]

    def get_layer_metadata(self, layer_name: str) -> LayerDefinition:
        for layer in self.get_layers():
            if layer.layer_name == layer_name:
                return layer
        raise LayerLoadException(f"GeoPackage layer '{layer_name}' not found.")

    def load_layer(self, layer_name: str):
        if QgsVectorLayer is None:
            raise LayerLoadException("QGIS runtime is not available.")
        metadata = self.get_layer_metadata(layer_name)
        layer = QgsVectorLayer(
            metadata.provider_uri, metadata.display_name, metadata.provider_key
        )
        if not layer.isValid():
            raise LayerLoadException(f"Invalid GeoPackage layer '{metadata.display_name}'.")
        return layer

    def test_connection(self) -> bool:
        _ = self._resolve_path()
        return True

    def _resolve_path(self) -> Path:
        path_value = self._config.get("path")
        if not path_value:
            raise ConfigurationException("GeoPackage datasource requires 'path'.")
        path = Path(path_value)
        if not path.exists() or not path.is_file():
            raise ConfigurationException(f"GeoPackage path does not exist: {path}")
        return path

    def _discover_sublayers(self, path: Path) -> list[str]:
        if QgsVectorLayer is None:
            return []
        probe = QgsVectorLayer(str(path), path.stem, "ogr")
        if not probe.isValid():
            return []
        result = []
        for entry in probe.dataProvider().subLayers():
            parts = entry.split("!!::!!")
            if len(parts) >= 2:
                name = parts[1] if parts[0].isdigit() else parts[0]
                result.append(name.strip())
            else:
                result.append(entry.strip())
        return result
```

---

### Step 3 — Register in `DatasourceService`

**File:** `geodata_catalog/services/datasource_service.py`

```python
from geodata_catalog.connectors.geopackage_connector import GeoPackageConnector  # ← add import

# Inside get_connector():
connector_map: dict[DatasourceType, type[BaseConnector]] = {
    DatasourceType.ORACLE:      OracleConnector,
    DatasourceType.GEOJSON:     GeoJsonConnector,
    DatasourceType.KML:         KmlConnector,
    DatasourceType.REST:        RestConnector,
    DatasourceType.GEOPACKAGE:  GeoPackageConnector,  # ← add entry
}
```

---

### Step 4 — Register in `connectors/__init__.py`

**File:** `geodata_catalog/connectors/__init__.py`

```python
from .geopackage_connector import GeoPackageConnector  # ← add

__all__ = [
    "BaseConnector",
    "GeoJsonConnector",
    "GeoPackageConnector",    # ← add
    "KmlConnector",
    "OracleConnector",
    "RestConnector",
]
```

---

### Step 5 — Add UI entry in `CatalogDockWidget`

**File:** `geodata_catalog/ui/catalog_dockwidget.py`

In `set_datasources`, add a new tree branch:

```python
geopackage_root = QTreeWidgetItem(["GeoPackage"])
file_root.addChild(geopackage_root)

# Inside the for-loop:
elif datasource.datasource_type is DatasourceType.GEOPACKAGE:
    geopackage_root.addChild(item)
```

In `datasource_dialog.py`, add the new type to the type combo:

```python
self._type_combo.addItem("GeoPackage", DatasourceType.GEOPACKAGE)
```

---

### Step 6 — Write tests

Create `geodata_catalog/tests/test_geopackage_connector.py`:

```python
from pathlib import Path
from geodata_catalog.connectors.geopackage_connector import GeoPackageConnector


def test_geopackage_get_layers(monkeypatch):
    connector = GeoPackageConnector("ds-gpkg", {"path": "C:/data/layers.gpkg"})

    monkeypatch.setattr(connector, "_resolve_path", lambda: Path("C:/data/layers.gpkg"))
    monkeypatch.setattr(
        connector,
        "_discover_sublayers",
        lambda path: ["buildings", "roads"],
    )

    layers = connector.get_layers()

    assert len(layers) == 2
    assert layers[0].display_name == "buildings"
    assert layers[0].provider_uri == "C:/data/layers.gpkg|layername=buildings"
    assert layers[1].display_name == "roads"
```

---

## Documentation Update Checklist

When making any of the changes listed below, **always update the corresponding documentation**:

| Change | Documentation to update |
|---|---|
| Add a new `DatasourceType` | [index.md](index.md) table, [adding-sources.md](adding-sources.md) new section, [architecture.md](architecture.md) connector map |
| Add a new config field to a connector | [adding-sources.md](adding-sources.md) field table for that type |
| Change a model field | [architecture.md](architecture.md) data model tables |
| Add a new exception type | [architecture.md](architecture.md) exception hierarchy |
| Change how settings are persisted | [architecture.md](architecture.md) persistence section |
| Fix a common bug | [troubleshooting.md](troubleshooting.md) if the symptom was user-visible |
| Change installation requirements | [getting-started.md](getting-started.md) requirements table |
| Change the UI layout | [getting-started.md](getting-started.md) UI overview section |

---

## Project Conventions

- **Code comments** must be written in English.
- Python 3.9+ syntax (the QGIS bundled Python is 3.9 or later).
- All QGIS imports are wrapped in `try/except ImportError` so the module can be imported outside QGIS for testing.
- Use `dataclass(slots=True)` for models.
- Connectors must not import each other.
- Services must not import UI components.
- Use `PluginLogger` for all log output — never `print()`.
