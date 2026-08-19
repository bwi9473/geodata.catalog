# Architecture

This document describes the internal structure of the GeoData Catalog plugin: how the components fit together, the data flow for discovering and loading layers, and how configuration is persisted.

---

## Directory Layout

```
geodata_catalog/           Root package
├── plugin.py              QGIS plugin entry point (GeoDataCatalogPlugin)
├── exceptions.py          Custom exception hierarchy
├── logging_utils.py       PluginLogger — wraps QgsMessageLog
│
├── models/                Plain data models (no QGIS dependency)
│   ├── datasource.py      Datasource, DatasourceType, AuthType
│   └── layer_definition.py LayerDefinition
│
├── connectors/            One connector class per source type
│   ├── base_connector.py  BaseConnector (abstract)
│   ├── geojson_connector.py
│   ├── kml_connector.py
│   ├── oracle_connector.py
│   └── rest_connector.py
│
├── metadata/              Persistence layer (QGIS QSettings)
│   ├── settings_manager.py  SettingsManager — JSON serialisation over QSettings
│   ├── datasource_repository.py
│   ├── layer_repository.py
│   └── layer_config_repository.py  Per-layer display/search config (layer_config.json)
│
├── services/              Business logic
│   ├── datasource_service.py  CRUD + connector factory
│   ├── layer_service.py       Layer discovery + merge with stored metadata
│   ├── layer_filter_service.py Flight-level and attribute filter expressions
│   ├── qgis_loader_service.py Layer loading into QGIS project
│   └── style_service.py       QML style application
│
├── ui/                    Qt widgets
│   ├── catalog_dockwidget.py  Main dock panel (right-click → Edit Layer Config)
│   ├── datasource_dialog.py   Add/Edit datasource dialog (connection params only)
│   ├── layer_config_dialog.py Per-layer layer-name override + label + searchable/custom-view columns dialog
│   ├── layer_custom_view_dock.py Excel-like custom view dock for loaded layer features
│   ├── layer_filter_dialog.py Flight-level + attribute filter dialog
│   └── settings_dialog.py     Plugin settings dialog
│
└── resources/             Bundled test data and example configs
    ├── aerodromes_sample.kml
    ├── aerodromes_sample.geojson
    ├── example_configuration.json
    └── example_configuration_files_only.json
```

---

## Component Overview

```
┌────────────────────────────────────────────────────────────────────┐
│  QGIS                                                              │
│                                                                    │
│  ┌──────────────────────┐    ┌─────────────────────────────────┐  │
│  │  CatalogDockWidget   │◄──►│  GeoDataCatalogPlugin           │  │
│  │  (UI / Qt)           │    │  (plugin.py)                    │  │
│  └──────────────────────┘    └──────┬──────────────────────────┘  │
│                                     │                              │
│                     ┌───────────────┼──────────────────────┐      │
│                     ▼               ▼                      ▼      │
│          ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│          │DatasourceSvc │  │ LayerService │  │QgisLoaderService │ │
│          └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘ │
│                 │                 │                   │            │
│          ┌──────▼───────┐  ┌──────▼───────┐  ┌────────▼─────────┐ │
│          │DatasourceRepo│  │ LayerRepo    │  │  StyleService    │ │
│          └──────┬───────┘  └──────────────┘  └──────────────────┘ │
│                 │                                                  │
│          ┌──────▼───────┐  ┌──────────────────────┐               │
│          │SettingsManager│  │ LayerConfigRepository│               │
│          │               │  │ (layer_config.json)  │               │
│          └──────────────┘  └──────────────────────┘               │
│                                                                    │
│  Connectors (created on demand by DatasourceService.get_connector) │
│  ┌────────┐ ┌────────┐ ┌─────────┐ ┌──────────────┐  │
│  │ Oracle │ │GeoJSON │ │   KML   │ │     REST     │  │
│  └────────┘ └────────┘ └─────────┘ └──────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## Data Models

### `Datasource`

Represents a registered connection to a data source.

| Field | Type | Description |
|---|---|---|
| `id` | `str` | UUID generated at creation time |
| `name` | `str` | User-facing name shown in the catalog tree |
| `datasource_type` | `DatasourceType` | Enum: `oracle`, `geojson`, `kml`, `rest` |
| `config` | `dict` | Connector-specific configuration (see [Adding Sources](adding-sources.md)) |
| `enabled` | `bool` | Reserved for future filtering; currently always `True` |

### `LayerDefinition`

Represents a single layer within a datasource.

| Field | Type | Description |
|---|---|---|
| `datasource_id` | `str` | ID of the owning `Datasource` |
| `layer_name` | `str` | Technical layer identifier (unique within the datasource) |
| `display_name` | `str` | Human-readable name shown in the UI |
| `provider_key` | `str` | QGIS provider string (`ogr`, `oracle`, `postgres`) |
| `provider_uri` | `str` | Full provider connection URI passed to `QgsVectorLayer` |
| `business_group` | `str` | Logical grouping label (default: `"General"`) |
| `geometry_type` | `str\|None` | Geometry type string (e.g. `POINT`, `POLYGON`) |
| `srid` | `int\|None` | Spatial reference system ID |
| `feature_count` | `int\|None` | Approximate feature count |
| `default_crs` | `str\|None` | CRS string applied after loading (e.g. `EPSG:4326`) |
| `default_style_file` | `str\|None` | Absolute path to a `.qml` style file |
| `filter_expression` | `str\|None` | Optional QGIS subset string applied before the layer is added to the project |
| `label_column` | `str\|None` | Field name to use as the QGIS label for each feature (single column, optional) |
| `searchable_columns` | `list[dict]\|None` | Columns exposed as search fields in the Layer Filter. Each dict: `{"name": "COL", "label": "Display label", "type": "varchar\|numeric", "use_distinct": bool}`. When `use_distinct` is `true`, a dropdown with distinct values is shown instead of free-text input. |
| `metadata` | `dict` | Connector-specific extra fields |

### `DatasourceType` enum

| Value | String key |
|---|---|
| `ORACLE` | `"oracle"` |
| `GEOJSON` | `"geojson"` |
| `KML` | `"kml"` |
| `REST` | `"rest"` |

### `AuthType` enum (REST only)

| Value | String key |
|---|---|
| `NONE` | `"none"` |
| `BASIC` | `"basic"` |
| `BEARER` | `"bearer"` |

---

## Data Flow

### Discovering layers (Refresh)

```
UI: user clicks Refresh
  └── CatalogDockWidget.refresh_requested(datasource_id)
        └── GeoDataCatalogPlugin._on_refresh_source(datasource_id)
              ├── DatasourceService.get_datasource(id) → Datasource
              ├── LayerService.discover_layers(datasource)
              │     ├── DatasourceService.get_connector(datasource) → Connector
              │     ├── Connector.get_layers() → list[LayerDefinition]
              │     ├── LayerRepository.list_by_datasource(id) → merge metadata
              │     └── LayerConfigRepository.list_by_datasource(id) → merge label/search config
              ├── plugin caches layers in _layer_cache[datasource_id]
              └── CatalogDockWidget.set_layers(layers) → updates UI list
```

### Loading a layer

```
UI: user double-clicks a layer (or clicks Load Layer)
  └── CatalogDockWidget.load_layer_requested(datasource_id, layer_name)
        └── GeoDataCatalogPlugin._on_load_layer(datasource_id, layer_name)
              ├── DatasourceService.get_datasource(id) → Datasource
              ├── DatasourceService.get_connector(datasource) → Connector
              ├── GeoDataCatalogPlugin._resolve_layer(id, name) → LayerDefinition
              │     └── (uses _layer_cache, re-discovers if not found)
              ├── GeoDataCatalogPlugin._prompt_flightlevel_filter(display_name)
              │     └── FlightLevelFilterDialog collects lower/upper values and the mode
              ├── FlightLevelFilterService.build_expression(filter)
              │     └── Builds a QGIS subset string using fl_lower / fl_upper
              └── QgisLoaderService.load_layer(layer_definition, connector)
                    ├── Connector.load_layer(layer_name) → QgsVectorLayer
                    ├── Validates layer.isValid()
                    ├── Assigns CRS via QgsCoordinateReferenceSystem
                  ├── Applies subset filter when filter_expression is set
                    ├── StyleService.apply_default_style(layer, style_file)
                    └── QgsProject.instance().addMapLayer(layer)
```

---

## Persistence

Configuration is persisted in two user-writable JSON files and mirrored to QGIS application settings (`QSettings`) under the namespace `GeoDataCatalog`.

Primary storage directory: `.../GeoDataCatalog/` (resolved via `QStandardPaths.AppDataLocation`)

- Fallback outside QGIS runtime: `~/.geodata_catalog/GeoDataCatalog/`

This avoids writing configuration into the plugin installation directory, so users can manage configuration safely without modifying plugin code files.

| File | Settings key | Contents |
|---|---|---|
| `config.json` | `GeoDataCatalog/datasources` | JSON array of all `Datasource.to_dict()` objects |
| `config.json` | `GeoDataCatalog/layers` | JSON array of all `LayerDefinition.to_dict()` objects (business metadata overrides) |
| `layer_config.json` | — | Per-layer layer-name override, label column, searchable columns, and custom-view columns, managed by `LayerConfigRepository` |

Settings survive QGIS restarts and are profile-specific. `layer_config.json` is stored in the same directory as `config.json` and is accessed via `SettingsManager.sibling_file_path("layer_config.json")`.

---

## Exception Hierarchy

```
GeoDataCatalogException (base)
├── DatasourceConnectionException   Connection or authentication failure
├── LayerLoadException              Layer creation or validation failure
└── ConfigurationException          Missing or invalid configuration field
```

All exceptions that reach `plugin.py` are caught, logged via `PluginLogger`, and displayed to the user in a `QMessageBox.warning` dialog.

---

## Connector Contract

Every connector must implement `BaseConnector`:

```python
class BaseConnector(ABC):
    def get_layers(self) -> list[LayerDefinition]: ...
    def get_layer_metadata(self, layer_name: str) -> LayerDefinition: ...
    def load_layer(self, layer_name: str): ...           # returns QgsVectorLayer
    def test_connection(self) -> bool: ...
```

The `DatasourceService.get_connector()` method maps `DatasourceType` → connector class:

```python
connector_map = {
    DatasourceType.ORACLE:   OracleConnector,
    DatasourceType.GEOJSON:  GeoJsonConnector,
    DatasourceType.KML:      KmlConnector,
    DatasourceType.REST:     RestConnector,
}
```

See [Development](development.md) for instructions on adding a new connector.

---

## Flight Level Filtering

After a layer is loaded, GeoData Catalog allows filtering by flight levels via the **Flight Level Filter** button in the dock panel.

The dialog supports three modes:

| Mode | Meaning | Expression |
|---|---|---|
| Between lower and upper limits | Show features overlapping a selected interval | `CAST("fl_lower" AS INTEGER) <= upper AND CAST("fl_upper" AS INTEGER) >= lower` |
| At or above a lower limit | Show features whose lower limit is greater than or equal to the chosen value | `CAST("fl_lower" AS INTEGER) >= lower` |
| At or below an upper limit | Show features whose upper limit is less than or equal to the chosen value | `CAST("fl_upper" AS INTEGER) <= upper` |

The filter is applied as a QGIS subset string, so only matching features appear in both the map and the attribute table.

**Filter composition:** If the layer already has a filter (from QGIS or another source), the flight level filter is added to it with `AND` logic. To remove the flight level filter while keeping other filters, select **None** mode in the dialog.

**Mode-aware controls:**

- `Between lower and upper limits`: both lower and upper values are editable.
- `At or above a lower limit`: only lower value is editable.
- `At or below an upper limit`: only upper value is editable.

The default field names are `fl_lower` and `fl_upper`. If your dataset uses different field names, update them in the filter dialog.

For attribute filters, the dialog supports comma-separated values that are translated to SQL `IN (...)` clauses. Numeric searchable columns are validated before applying filters.

## Layer Panel Actions

The QGIS **Layers panel** context menu includes GeoData Catalog actions for the currently active loaded vector layer:

- **Layer Filter…** opens the flight-level + attribute filter dialog for the active layer.
- **Open Custom View…** opens a custom dock with table browsing and export.

- Uses `view_columns` from `layer_config.json` (`Field Name`, `Display Label`, `Data Type`).
- Renders data in an Excel-like table with row checkboxes.
- Supports sorting and paging in the dock.
- Highlights features on the map when selecting rows.
- Supports exporting all rows to CSV.
- Supports exporting all rows to Excel (`.xlsx`) when `openpyxl` is available in the QGIS Python environment.

Per-layer display name override:

- `layer_config.json` can store a `layername` value set in **Edit Layer Config**.
- When `layername` is set, it overrides the discovered source name used in the QGIS Layers panel.
- When `layername` is empty, the plugin keeps the default source-derived layer name.
