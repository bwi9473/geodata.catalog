# Adding Sources

This guide explains how to add every supported datasource type to the GeoData Catalog. For each type you will find:

- A description of what the connector does
- All required and optional configuration fields
- One or more complete, copy-paste-ready JSON examples
- Tips and common pitfalls

---

## How Configuration Works

Every datasource has a **Configuration JSON** object. This object is stored as-is and passed to the connector when layers are discovered or loaded. You enter it in the **Add Source** / **Edit Source** dialog.

The structure is always:

```json
{
  "field_name": "value",
  ...
}
```

Field names are **case-sensitive** and must be lowercase.

---

## Contents

1. [KML / KMZ files](#1-kml--kmz-files)
2. [GeoJSON files](#2-geojson-files)
3. [Oracle Spatial](#3-oracle-spatial)
4. [PostGIS](#4-postgis)
5. [REST GeoJSON endpoints](#5-rest-geojson-endpoints)

---

## 1. KML / KMZ Files

The KML connector reads a local `.kml` or `.kmz` file using the QGIS/OGR provider. It automatically discovers all sublayers (folders / `<Document>` nodes) inside the file.

### Configuration fields

| Field | Required | Type | Description |
|---|---|---|---|
| `path` | ✅ | string | Absolute path to the `.kml` or `.kmz` file. Use forward slashes on Windows. |
| `label_column` | ❌ | string | Field name to use as the QGIS feature label (e.g. `"name"`). Leave empty for no labels. |

### Minimal example

```json
{
  "path": "C:/GIS/data/aerodromes.kml"
}
```

### Example with the bundled sample file

```json
{
  "path": "C:/QGIS/plugins/geodata_catalog/geodata_catalog/resources/aerodromes_sample.kml"
}
```

### How sublayers are discovered

When you click **Refresh**, the connector opens the file with the OGR provider and calls `dataProvider().subLayers()`. Each sublayer string is parsed to extract:

- **Layer name** (used as the layer identifier and display name)
- **Layer ID** (numeric index within the file, preferred when building the provider URI)

The resulting QGIS provider URI takes the form:

```
/path/to/file.kml|layerid=1
```

or, when no numeric ID is available:

```
/path/to/file.kml|layername=Aerodromes
```

### Tips

- The KML file may contain multiple folders. Each folder becomes a separate layer in the catalog list.
- **Always use forward slashes** in the path, even on Windows (`C:/Data/file.kml`, not `C:\Data\file.kml`).
- Network drives are supported as long as QGIS can reach the path.

---

## 2. GeoJSON Files

The GeoJSON connector reads one or more local `.geojson` / `.json` files. It can point to a single file **or** a directory (which is then scanned for all matching files).

### Configuration fields

| Field | Required | Type | Description |
|---|---|---|---|
| `path` | ✅ | string | Absolute path to a single GeoJSON file, **or** a directory that contains GeoJSON files. |
| `label_column` | ❌ | string | Field name to use as the QGIS feature label (e.g. `"name"`). Leave empty for no labels. |

### Single file example

```json
{
  "path": "C:/GIS/data/airports.geojson"
}
```

### Directory example

Loads every `.geojson` and `.json` file found directly in the folder (non-recursive):

```json
{
  "path": "C:/GIS/data/aeronautical"
}
```

### Example with the bundled sample file

```json
{
  "path": "C:/QGIS/plugins/geodata_catalog/geodata_catalog/resources/aerodromes_sample.geojson"
}
```

### What the connector reads

For every file found, the connector:
1. Parses the JSON and validates the `type` field is `FeatureCollection` or `Feature`.
2. Counts features (`feature_count`).
3. Infers the geometry type from the first feature with a geometry.
4. Reads the optional CRS from the `crs.properties.name` field (e.g. `EPSG:4326`).

### Tips

- Only files with the `.geojson` or `.json` extension are discovered in directory mode.
- The layer name in the catalog is the **filename** (including extension, e.g. `airports.geojson`). The display name is the **stem** (e.g. `airports`).
- All GeoJSON files are expected to be in WGS84 (`EPSG:4326`) by default. Override by embedding a `crs` block in the file.

---

## 3. Oracle Spatial

The Oracle connector discovers all spatial tables, views and materialized views that have an entry in `ALL_SDO_GEOM_METADATA`. It uses `python-oracledb` for the database connection and the QGIS Oracle provider for loading.

> **Prerequisite:** `python-oracledb` must be installed in the QGIS Python environment.
> ```bash
> pip install python-oracledb>=2.2.0
> ```

### Configuration fields

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `host` | ✅ | string | — | Oracle server hostname or IP address |
| `port` | | integer | `1521` | Oracle listener port |
| `service_name` | ✅ | string | — | Oracle service name (e.g. `ORCLCDB`) |
| `username` | ✅ | string | — | Database username |
| `password` | ✅ | string | — | Database password |
| `schema` | | string | `null` | Restrict discovery to a single schema/owner. When omitted, all accessible spatial objects are listed. |
| `key_column` | | string | `""` | Primary key column name, used by the QGIS Oracle provider for feature identification. |
| `label_column` | | string | `null` | Global default field name to use as the QGIS feature label for all layers in this source. Can be overridden per layer via **right-click → Edit Layer Config**. |

### Minimal example

```json
{
  "host": "oracle.example.com",
  "service_name": "ORCLCDB",
  "username": "gis_user",
  "password": "secret"
}
```

### Production example with schema filter

```json
{
  "host": "oracle.example.com",
  "port": 1521,
  "service_name": "GISPROD",
  "username": "gis_read",
  "password": "secret",
  "schema": "AIRSPACE",
  "key_column": "OBJECTID"
}
```

### Multiple schemas

To load layers from multiple schemas, create **separate datasources** — one per schema:

**Datasource 1 — Airspace schema:**
```json
{
  "host": "oracle.example.com",
  "service_name": "GISPROD",
  "username": "gis_read",
  "password": "secret",
  "schema": "AIRSPACE"
}
```

**Datasource 2 — Navigation schema:**
```json
{
  "host": "oracle.example.com",
  "service_name": "GISPROD",
  "username": "gis_read",
  "password": "secret",
  "schema": "NAVIGATION"
}
```

### How layers are discovered

The connector queries `ALL_SDO_GEOM_METADATA` joined to `ALL_OBJECTS` and `ALL_TAB_COLUMNS` to find every geometry column. For each spatial object it also:

- Detects the geometry type by sampling `SDO_GTYPE` from the first non-null row.
- Counts features with `SELECT COUNT(*)`.
- Builds a QGIS `QgsDataSourceUri` connection string.

### Tips

- Use a **read-only** database account. The connector never writes to the database.
- The `schema` filter is applied as `UPPER(schema)`, so casing does not matter.
- If `python-oracledb` is missing, a `DatasourceConnectionException` is raised on Refresh.
- Oracle Instant Client is **not** required when using `python-oracledb` in thin mode.

---

## 4. PostGIS

The PostGIS connector discovers all geometry columns registered in `geometry_columns`. It uses `psycopg` (version 3) for the database connection and the QGIS PostgreSQL provider for loading.

> **Prerequisite:** `psycopg[binary]` must be installed in the QGIS Python environment.
> ```bash
> pip install "psycopg[binary]>=3.2.0"
> ```

### Configuration fields

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `host` | ✅ | string | — | PostgreSQL server hostname or IP address |
| `port` | | integer | `5432` | PostgreSQL server port |
| `database` | ✅ | string | — | Database name |
| `username` | ✅ | string | — | Database username |
| `password` | ✅ | string | — | Database password |
| `key_column` | | string | `""` | Primary key column name for the QGIS provider |
| `label_column` | | string | `null` | Global default field name to use as the QGIS feature label for all layers in this source. Can be overridden per layer via **right-click → Edit Layer Config**. |

### Minimal example

```json
{
  "host": "postgis.example.com",
  "database": "gisdb",
  "username": "gis_user",
  "password": "secret"
}
```

### Production example

```json
{
  "host": "postgis.example.com",
  "port": 5432,
  "database": "gisdb",
  "username": "gis_read",
  "password": "secret",
  "key_column": "gid"
}
```

### Local database (Docker / localhost)

```json
{
  "host": "localhost",
  "port": 5432,
  "database": "mydb",
  "username": "postgres",
  "password": "postgres"
}
```

### How layers are discovered

The connector selects all rows from the `geometry_columns` view, ordered by schema and table name. For each row it:

- Reads the schema, table name, geometry column, SRID, and geometry type.
- Counts features with `SELECT COUNT(*)`.
- Builds a QGIS `QgsDataSourceUri` connection string.

Layer names are in the form `schema.table_name` (e.g. `public.airspace_fir`).

### Tips

- Use a **read-only** database role with `SELECT` privileges on the relevant schemas.
- Layers from **all** schemas in `geometry_columns` are discovered unless you filter in your PostgreSQL role.
- The `key_column` field is optional but helps QGIS identify features uniquely — set it to your primary key column (commonly `gid` or `id`).

---

## 5. REST GeoJSON Endpoints

The REST connector fetches GeoJSON from an HTTP endpoint. It supports no authentication, HTTP Basic Authentication, and Bearer token authentication. Multiple datasets (different query parameters on the same base URL) can be grouped under one datasource.

> **Prerequisite:** `requests` must be installed in the QGIS Python environment.
> ```bash
> pip install requests>=2.32.0
> ```

### Configuration fields

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `url` | ✅ | string | — | Base URL of the GeoJSON endpoint |
| `auth_type` | | string | `"none"` | Authentication type: `"none"`, `"basic"`, or `"bearer"` |
| `username` | | string | `""` | Username for `basic` auth |
| `password` | | string | `""` | Password for `basic` auth |
| `token` | | string | `""` | Bearer token for `bearer` auth (sent as `Authorization: Bearer <token>`) |
| `headers` | | object | `{}` | Extra HTTP request headers as key-value pairs |
| `query_params` | | object | `{}` | Query parameters added to every request |
| `datasets` | | array | `[]` | List of named datasets (see below). When empty, one layer is created from the base URL. |
| `display_name` | | string | `"REST Dataset"` | Display name used when `datasets` is empty |
| `timeout` | | number | `30.0` | Request timeout in seconds |
| `label_column` | | string | `null` | Field name to use as the QGIS feature label (e.g. `"name"`). Applied automatically when the layer is loaded. |

#### Dataset object

Each item in `datasets` defines one layer:

| Field | Required | Type | Description |
|---|---|---|---|
| `name` | ✅ | string | Display name for this dataset |
| `params` | | object | Additional query parameters merged with the global `query_params` for this dataset only |

### Example 1 — Simple public endpoint (no auth)

```json
{
  "url": "https://api.example.com/airspace/geojson",
  "display_name": "Airspace"
}
```

### Example 2 — Bearer token with extra headers

```json
{
  "url": "https://api.example.com/flights",
  "auth_type": "bearer",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "headers": {
    "Accept": "application/geo+json",
    "X-Client-Id": "geodata-catalog"
  },
  "timeout": 60.0
}
```

### Example 3 — HTTP Basic Authentication

```json
{
  "url": "https://secure.example.com/features",
  "auth_type": "basic",
  "username": "api_user",
  "password": "secret",
  "display_name": "Secure Features"
}
```

### Example 4 — Multiple datasets from one endpoint

One datasource, multiple layers. Each dataset appends its own `params` to the shared `query_params`:

```json
{
  "url": "https://api.example.com/flights",
  "auth_type": "bearer",
  "token": "my-token",
  "headers": {
    "Accept": "application/geo+json"
  },
  "query_params": {
    "format": "geojson"
  },
  "datasets": [
    {
      "name": "Active Flights",
      "params": {
        "status": "active"
      }
    },
    {
      "name": "Planned Flights",
      "params": {
        "status": "planned"
      }
    },
    {
      "name": "Historical Flights",
      "params": {
        "status": "historical",
        "days": "7"
      }
    }
  ]
}
```

This creates three layers: **Active Flights**, **Planned Flights**, and **Historical Flights**.

### Example 5 — Global query params (no datasets)

```json
{
  "url": "https://api.example.com/restricted-airspace",
  "query_params": {
    "format": "geojson",
    "country": "BE"
  },
  "display_name": "Belgian Restricted Airspace",
  "timeout": 45.0
}
```

### How the REST connector loads layers

1. On **Refresh**: only the layer names / URIs are returned — no HTTP requests are made.
2. On **Load Layer**: the connector fetches the GeoJSON via HTTP, validates the response, writes it to a temporary file, and opens that file with the OGR provider.
3. Each call to **Load Layer** re-fetches fresh data from the server.

### Tips

- The endpoint must return a valid GeoJSON `FeatureCollection` or `Feature` object.
- The `Bearer` token is injected as the `Authorization` header; do not add it manually to `headers`.
- Combine `query_params` (global, always sent) with `datasets[].params` (per-dataset, merged on top) to avoid repetition.
- If the endpoint requires a custom `Content-Type` in the response, add `"Accept": "application/geo+json"` (or `"application/json"`) to `headers`.

---

## Editing and Deleting Sources

### All loadable layers overview

When you want one quick overview of everything that can be loaded as a layer (file sources and database tables), enable **Show all loadable layers** in the GeoData Catalog panel.

- The existing Layer List switches to an aggregated list across all datasources.
- Each row still supports double-click to load the layer directly.
- Disable the option to return to the per-datasource layer list.

### Edit

1. Select the datasource in the tree.
2. Click **Edit Source**.
3. Modify the name, type, or configuration JSON (connection parameters only).
4. Click **Save**.

> Changing the **type** of an existing datasource discards any previously discovered layer cache. Click **Refresh** after saving.

### Delete

1. Select the datasource in the tree.
2. Click **Delete Source**.
3. Confirm the deletion in the dialog.

Deletion removes the datasource configuration from QGIS settings permanently. Layers already loaded into the QGIS project are **not** removed from the map. All associated per-layer configurations in `layer_config.json` are also removed.

---

## Per-Layer Configuration

Each layer in the catalog can have its own **label column**, **flight-level filter toggle**, and **searchable columns** defined independently of the datasource connection settings. This configuration is stored in a separate `layer_config.json` file and is applied on top of any connector defaults.

### Opening the Layer Config dialog

1. Expand a datasource in the catalog tree until the layer list is visible.
2. **Right-click** any layer.
3. Choose **Edit Layer Config…** from the context menu.

### Layer Config fields

| Field | Description |
|---|---|
| **Layer Name** | Name shown for this layer in the QGIS **Layers** panel. Leave empty to keep the default name discovered from the source. |
| **Label Column** | Name of the attribute field used as the QGIS feature label (e.g. `IDENT`, `name`). Overrides the global `label_column` set in the datasource configuration. Leave empty to use the connector default. |
| **Enable Flight Level Filter** | Boolean toggle for this layer. When enabled, the Layer Filter dialog shows the FL range section at the bottom. When disabled, only custom attribute filters are shown. |
| **Searchable Columns** | Table of columns made available as filters in the Layer Filter dialog. These custom fields are shown before the FL section. Each row has a **Field Name** (internal attribute name), a **Display Label** (shown in the UI), a **Data Type** (`varchar` or `numeric`), a **Use Distinct** checkbox, and an optional **Filter By** field. When **Use Distinct** is checked, the Layer Filter shows a dropdown with distinct values instead of a free-text field. When **Filter By** is set to the field name of another (parent) column, the dropdown for this column is automatically narrowed to only the values that co-occur with the currently selected parent value (cascading / dependent dropdowns). |

### Searchable Columns — JSON representation

Internally, searchable columns are stored in `layer_config.json` as an array of objects:

```json
[
  { "name": "STATUS",     "label": "Status",      "type": "varchar", "use_distinct": true },
  { "name": "ROUTE_TYPE", "label": "Route Type",  "type": "varchar", "use_distinct": false },
  { "name": "MIN_FL",     "label": "Min FL",      "type": "numeric",  "use_distinct": false }
]
```

The per-layer configuration object also contains:

```json
{
  "datasource_id": "my_source",
  "layer_name": "MY_LAYER",
  "enable_fl_filter": true,
  "searchable_columns": [
    { "name": "STATUS", "label": "Status", "type": "varchar", "use_distinct": true }
  ]
}
```

Each searchable column object supports the following keys:

| Key | Required | Type | Default | Description |
|---|---|---|---|---|
| `name` | ✅ | string | — | Internal attribute field name as it appears in the layer. |
| `label` | ❌ | string | same as `name` | Display label shown in the Layer Filter dialog. |
| `type` | ❌ | string | `"varchar"` | Data type: `"varchar"` or `"numeric"`. Numeric columns validate that entered values are numbers. |
| `use_distinct` | ❌ | boolean | `false` | When `true`, the Layer Filter shows a dropdown populated with all distinct values of this column instead of a free-text field. |
| `filter_by` | ❌ | string | — | Field name of a **parent** column (also in `searchable_columns` with `use_distinct: true`). When the parent dropdown has a value selected, the dropdown for this column is narrowed to only the values that co-occur with that parent value in the layer data (cascading dropdown). |

### Cascading dropdowns (dependent filters)

When one attribute column depends on another — for example `flight_sectorid` only makes sense in the context of a selected `sectors_combinid` — you can link them with `filter_by`:

```json
[
  {
    "name": "sectors_combinid",
    "label": "Sectors combination",
    "type": "varchar",
    "use_distinct": true
  },
  {
    "name": "flight_sectorid",
    "label": "Flight sector",
    "type": "varchar",
    "use_distinct": true,
    "filter_by": "sectors_combinid"
  },
  {
    "name": "setting_sectorid",
    "label": "Setting sector",
    "type": "varchar",
    "use_distinct": true
  }
]
```

In the **Layer Filter** dialog this configuration produces:

1. A **Sectors combination** dropdown listing all distinct `sectors_combinid` values.
2. A **Flight sector** dropdown that — as long as no parent is selected — shows all `flight_sectorid` values. As soon as a `sectors_combinid` is chosen, the list is automatically narrowed to only the `flight_sectorid` values that exist for that combination.
3. A **Setting sector** dropdown with no dependency (all values always visible).

**Rules and behaviour:**
- Both the parent column and the child column must have `use_distinct: true`.
- If the parent dropdown is reset to **(no filter)**, the child dropdown immediately reverts to its full unfiltered list.
- Any manually typed value in the **custom** free-text field of the child is not affected by the cascade; it is always used as-is.
- Multiple child columns can reference the same parent column.
- Chained / multi-level cascades (grandparent → parent → child) are not supported — only one level of dependency is applied.

### Multi-value search input

In the **Layer Filter** dialog:

- **Free-text input** (when `use_distinct` is unchecked): You can enter multiple values separated by commas (for example: `A, B`).
  - For `varchar` columns, this becomes: `"COLUMN" IN ('A', 'B')`
  - For `numeric` columns, this becomes: `"COLUMN" IN (100, 200)`
  - Single values continue to use `=`.

- **Dropdown selector** (when `use_distinct` is checked): Select a single distinct value from the list using the **select** field, or type one or more comma-separated values manually in the **custom** field below it. Select **(no filter)** from the dropdown to clear the dropdown selection. If both fields contain values, they are combined.

### Flight level range filter

When **Enable Flight Level Filter** is turned on in Layer Config, the Layer Filter dialog shows a dual-handle FL range slider at the bottom:

- Set a lower and upper bound (for example `FL95` to `FL195`).
- The filter keeps all sectors/features that **overlap** the selected interval.
- Releasing either slider handle immediately applies the FL filter and refreshes the map.
- Uncheck **Enable flight level filter** in the Layer Filter dialog to apply only custom attribute filters without FL restriction.

### Storage location

`layer_config.json` is stored in the same directory as the main `config.json` (inside the QGIS profile application-data folder). You do not need to edit it manually — use the **Edit Layer Config…** dialog instead.

### Tips

- Per-layer config survives **Edit Source** operations on the parent datasource.
- If **Layer Name** is set, loaded layers use that value in the QGIS Layers panel; when empty, the source default name is used.
- Deleting a datasource also removes all its per-layer config entries from `layer_config.json`.
- The **Layer Filter** dialog only shows the Attribute Search panel when at least one searchable column is defined for the layer.
- Turn off **Enable Flight Level Filter** in Layer Config for layers where FL filtering is not relevant.
- Use **Use Distinct** checkbox on searchable columns to show a dropdown with pre-filled values instead of free-text input, improving data quality and user experience for columns with enumerated values.
- Use **Filter By** on a searchable column to create a cascading (dependent) dropdown: the child column's options are automatically narrowed when the user selects a value in the parent column. Both columns must have **Use Distinct** enabled.
- In **Custom View**, records are shown in an Excel-like table with sorting, paging, row checkboxes, and map highlighting on row selection.
- Excel export requires `openpyxl` in the QGIS Python environment; CSV export works without extra packages.

### Open Custom View from QGIS Layers panel

After loading the layer, use the **QGIS Layers panel** context menu (not the GeoData Catalog list):

1. In the QGIS **Layers** panel, right-click the loaded vector layer.
2. Click **Open Custom View…**.
3. A separate window opens with:
  - Excel-like table layout
  - Row checkboxes (selection behavior)
  - Feature highlighting on the map when selecting a row
  - CSV / Excel export
  - Sorting, paging, and column configuration

### Open Layer Filter from QGIS Layers panel

After loading the layer, use the **QGIS Layers panel** context menu:

1. In the QGIS **Layers** panel, right-click the loaded vector layer.
2. Click **Layer Filter…**.
3. Configure the flight-level and attribute filters. Click **Apply** for manual updates, or release the FL slider handle for immediate map refresh.
