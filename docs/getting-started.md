# Getting Started

This guide walks you through installing GeoData Catalog, activating the plugin, and loading your first layer in QGIS.

---

## Requirements

| Requirement | Minimum version |
|---|---|
| QGIS | 3.22 |
| Python | 3.9 (bundled with QGIS) |
| `oracledb` | 2.2.0 (only for Oracle sources) |
| `requests` | 2.32.0 (only for REST sources) |

> **File sources (KML, GeoJSON) have no extra Python dependencies.** They work with the standard QGIS/OGR stack.

---

## Installation

### 1. Locate your QGIS plugin directory

| OS | Default path |
|---|---|
| Windows | `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins` |
| macOS | `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins` |
| Linux | `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins` |

### 2. Copy the plugin

Copy the **entire** workspace folder into the plugins directory and **rename the folder to `geodata_catalog`**.  

> The folder name must not contain dots. Rename `geodata.catalog` → `geodata_catalog`.

After copying, the structure must look like this:

```
<plugins>/
  geodata_catalog/           ← the renamed folder
    metadata.txt             ← required by QGIS
    __init__.py
    geodata_catalog/
      plugin.py
      connectors/
      services/
      ...
```

### 3. Install optional Python packages

Open the **OSGeo4W Shell** (Windows) or a terminal where the QGIS Python is on the PATH, then run:

```bash
# For Oracle support
pip install python-oracledb>=2.2.0

# For REST source support
pip install requests>=2.32.0
```

---

## Activating the Plugin

1. Start QGIS.
2. Go to **Plugins → Manage and Install Plugins**.
3. Search for **GeoData Catalog**.
4. Check the checkbox next to it.
5. The **GeoData Catalog** panel appears on the left side of QGIS.

---

## Interactive marker

Use **Interactive Marker** on the GeoData Geometry Toolbox toolbar:

- If no position is configured, click the button, then left-click the map to set and save the marker position.
- If a position is configured, click the button to show the saved marker. Click again to hide it without deleting its saved position.
- Right-click the toolbar button and choose **Change marker position...** to select and save a new position on the map.
- Right-click the map while selecting a position to cancel. The previous saved position is kept.

## Work profiles and layer visibility

The plugin initially selects **User**. The toolbar and plugin menu contain
**Work profile: User...**; choose **Developer** to access Data Source Configuration
and **Manage user profiles...**. The last selected profile is remembered.

Developer always sees all catalog layers and configuration actions. In
**Manage user profiles...**, choose an existing user profile or add a named one:

- Leave **All catalog layers (including future layers)** checked to retain the
  existing unrestricted catalog browsing behavior.
- Uncheck it to choose individual layers. Selecting none gives an empty catalog.
- Use **Uncheck all** to clear every layer selection for the current profile,
  including layers not currently listed. This also turns off **All catalog layers**.
- Save, then switch to that profile to see its Data Panel.

Layer loading, filters, styles, map tools and saved views keep their existing behavior
for visible, available layers. Saved views of hidden layers are hidden as well.
Changing profile does not delete layers already loaded into the QGIS project.

These are freely selectable application work modes, not user authentication,
QGIS user profiles, or database authorization. Profiles and their visibility rules
are stored locally in the plugin's `config.json` (and QSettings), under
`user_profiles`. Database credentials remain separate in QGIS Authentication Manager.
This version does not provide central profile distribution or account synchronization.

### Sharing a catalog between Oracle environments

Add the same explicit `catalog_id` to each related Oracle source's connection JSON,
for example `"catalog_id": "aviation"`. Keep each environment's own host, service,
schema and environment color. Sources without `catalog_id` remain independent.
Only group environments whose schema/table or view names and geometry columns match.

The logical layer ID becomes `aviation:SCHEMA.TABLE`; it does not contain credentials,
host or service. Connect to the required environment using **Connect**. The Data Panel
shows each catalog once, targeting the connected environment rather than listing
duplicate development/production copies. Independent file and REST sources are unchanged.

Existing per-endpoint configuration remains readable. Editing a source copies its
legacy settings to its catalog key; editing a layer thereafter saves one shared
configuration. Original entries are retained, and shared entries take precedence.
Conflicting legacy display/search settings are reported explicitly: align those
settings before grouping the environments. Profile layer selections follow changes
to a source's catalog key. Shared settings survive removal of an environment.

Saved views follow the selected environment too. Their styles and filters are not
reconfigured; the current endpoint and login are used when loading. Views from
hidden layers cannot be loaded through the panel.

Configured but unavailable layers stay in their normal category, marked
**Not available**. Select one to read the reason; the Load button is disabled:

- **Source not found or not accessible with this database login** means discovery
  succeeded but did not find that configured source. A missing object cannot always
  be distinguished from insufficient Oracle privileges.
- **Database not connected or not accessible** means the source could not be queried.

Refresh/reopen the Data Panel after a database change to recheck availability.
Catalog visibility never grants database privileges, including in Developer mode.

## Your First Layer — KML file

The plugin ships with a sample KML file located at:

```
geodata_catalog/resources/aerodromes_sample.kml
```

### Step 1 — Add a datasource

1. Switch to **Developer**, open **Data Source Configuration**, and click **Add Source**.
2. Fill in the dialog:
   - **Name:** `Aerodromes KML`
   - **Type:** `KML`
   - **Configuration JSON:**

```json
{
  "path": "C:/path/to/geodata_catalog/resources/aerodromes_sample.kml"
}
```

> Use forward slashes (`/`) in Windows paths.

3. Click **Save**.

### Step 2 — Discover layers

1. Click on **Aerodromes KML** in the catalog tree.
2. Click **Refresh**.
3. The available sublayers appear in the layers list below the tree.

### Step 3 — Load a layer

Open the **Data Panel** using **Choose map layers**. Double-click a layer, or select
it and click **Load default layer**. You can switch to a user profile before loading.

The layer is added to the QGIS **Layers** panel and rendered on the map canvas.

### Layer Filter after layer is loaded

After a layer has been loaded in QGIS, you can filter it with the **Layer Filter**. This dialog combines two filtering sections:

1. **Attribute Search** — free-text or distinct-value equality filter on columns configured as `searchable_columns`.
2. **Flight Level Filter** — optional range filter (shown below the custom fields) on numeric flight-level fields.

To use the filter:

1. Click on the layer in the QGIS **Layers** panel to make it active.
2. Right-click the layer in the QGIS **Layers** panel.
3. Click **Layer Filter…**.
4. Fill in custom attribute fields first.
5. Adjust the FL range slider when needed.
6. Click **Apply** for manual updates, or release the FL slider handle to apply immediately.

You can also use **Quick presets** above the slider for one-click FL ranges.

**Flight level range behavior:**

| Control | Result |
|---|---|
| Dual FL slider (`FLx` to `FLy`) | Shows all sectors/features that overlap the selected interval |
| Quick preset buttons (`LOWER`, `HIGH`, ...) | Instantly sets a predefined range and applies the filter |
| Slider handle release | Automatically applies the current FL range and refreshes the map |
| **Enable flight level filter** unchecked | Removes FL filtering and keeps only base/attribute filters |

The FL filter uses `fl_lower` and `fl_upper` (case-insensitive match).

**Attribute search:**

The attribute search section appears automatically when the layer has searchable columns configured. Configure them by right-clicking the layer in the catalog list and choosing **Edit Layer Config…**. You can enter one value (`ACTIVE`) or multiple comma-separated values (`ACTIVE, PENDING`). For numeric columns, only numeric tokens are accepted. Leave a field empty to ignore that column.

> **Filters are cumulative:** If the layer already has a base filter, the layer filter is added to it with `AND` logic. Previously applied filter values are automatically restored when you re-open the dialog.

---

### Per-Layer Configuration (right-click)

Each layer in the catalog can have its own layer name override, label column, searchable columns, and custom-view columns configured independently of the datasource connection settings.

**To open the Layer Config dialog:**

1. Expand a datasource in the catalog tree until the layer list is visible.
2. **Right-click** any layer.
3. Choose **Edit Layer Config…**.

| Field | Description |
|---|---|
| **Layer Name** | Name shown for this layer in the QGIS **Layers** panel. Leave empty to keep the default source-discovered name. |
| **Label Column** | Attribute field used as the QGIS feature label. Overrides the global `label_column` from the datasource JSON. |
| **Point marker** | Choose a supplied SVG or use **...** to open the QGIS SVG browser. The SVG itself is embedded in the saved configuration, instead of storing a computer-specific file path. Choose **Simple marker (default)** to remove the override. |
| **Enable Flight Level Filter** | Controls whether the Flight Level section is shown in **Layer Filter…** for this layer. When disabled, only custom attribute filters are available. |
| **Searchable Columns** | Table of columns shown as filters in the Layer Filter (displayed above the FL section). Each row has a **Field Name**, **Display Label**, **Data Type** (`varchar` or `numeric`), **Use Distinct**, and optional **Filter By**. When **Use Distinct** is checked, the Layer Filter shows both a dropdown (for quick distinct-value selection) and a free-text field (for manual multi-value entry). Select **(no filter)** in the dropdown to clear the dropdown selection. |
| **Custom View Columns** | Table of columns shown in the right-click **Open Custom View…** dialog as multi-record blocks. Each row has a **Field Name**, **Display Label**, and **Data Type**. |

Use the **Add Row** / **Remove Row** buttons to manage the list of searchable columns, then click **Save**.

#### Moving SVG markers to another computer

Saved `svg_marker_path` values use QGIS's native `base64:` format and contain the complete SVG.
The marker does not depend on the original file, QGIS installation directory, drive letter, or SVG search paths.
Previews and loaded layers use that same embedded symbol. SVGs with external linked files or stylesheets must first be made self-contained; invalid or missing files are reported instead of saving a broken marker.

Copy the JSON file containing the marker setting: **Edit Layer Config** writes to `layer_config.json`, while business-layer metadata is stored in `config.json`. Copy both files to transfer the datasource and per-layer settings together. No separate SVG files are required for embedded markers. These files may contain connection settings, so share them only with trusted recipients.

Existing absolute SVG paths remain supported. Paths into an old QGIS installation (including Windows short paths and repeated separators) are resolved against the current computer's QGIS SVG folders. Old plugin aviation-symbol paths are resolved against the installed plugin. Saving a layer's configuration rewrites its SVG as embedded data; other layers are left unchanged. A missing custom SVG cannot be recovered from its old path alone: select it again on a computer where it is available and save before transferring the configuration.

When a configured marker cannot be read or created, layer loading preserves the existing layer symbol and records a warning in the plugin log rather than applying a missing-image `?` marker.

### Custom View (QGIS Layers panel)

After loading a layer in QGIS:

1. In the QGIS **Layers** panel, right-click the loaded layer.
2. Click **Open Custom View…**.
3. A separate window opens with an Excel-like table view.
4. Use **Sort by**, **Ascending/Descending**, and page navigation (**Previous/Next**) to browse records.
5. Use **Export CSV** or **Export Excel** to export all records in the current custom-view column layout.
6. Click a row to highlight the feature on the map. Use the checkbox column for selection behavior similar to the QGIS attribute table; multiple checked rows are combined into one map selection.
7. Selecting or deselecting features on the map also updates the checkboxes. Selected records move to the top, keeping the chosen sort order within the selected and unselected groups, and the view returns to the first page. Existing selections are checked when the window opens.
8. Selected records remain visible even when they do not match **Search in results**. The layer filter still applies; records outside the layer's result set are not added. **Selected** shows the total layer selection, including any selected records outside that result set.
9. Use **Clear selection** to uncheck all records across all pages and clear this layer's map selection. Clicking records in the table does not immediately move rows under the mouse; selected-first ordering is applied on the next search, sort, page change, or map selection.

The displayed fields are controlled by **Custom View Columns** in **Edit Layer Config…**.
For layers configured without flight levels, **Flight Levels (not available)** is greyed out and cannot be clicked. Its tooltip explains why flight level filtering is unavailable.

For layers with many filter fields:

- The attribute fields automatically flow into one to four columns as you resize the window.
- Use **Find filter field** to find a field by its technical name or display label. This only changes which input fields are visible; it does not search the result records.
- Enable **Only filled fields** to review the filters you have entered, including checkbox values such as `N`.
- The field counter also indicates filled fields hidden by the field search. Hidden fields keep their values and are still included when you click **Search**.
- Drag the horizontal divider between filters and results to give either section more space. The field search and the **Search**, **Reset**, and **Save** buttons stay outside the scrolling field list.
- **Reset** clears all filter values and restores the full field list.

The QGIS **Layers** panel context menu includes both **Layer Filter…** and **Open Custom View…** entries provided by GeoData Catalog.

---

## Where Configuration Is Stored

| File | Contents |
|---|---|
| `GeoDataCatalog/config.json` | Datasource connection parameters and business layer metadata |
| `GeoDataCatalog/layer_config.json` | Per-layer layer-name override, label column, FL-filter toggle, searchable columns, and custom-view columns (created on first save) |
| `GeoDataCatalog/system_configuration.json` | System-wide options like flight-level quick presets (created automatically with defaults) |

Both files are stored in the active QGIS profile app-data location and are also mirrored to QGIS settings for compatibility. You do not need to edit these files manually.

Default quick preset content:

```json
{
  "flight_level_presets": [
    {"name": "LOWER", "lower": 0, "upper": 355},
    {"name": "HIGH", "lower": 355, "upper": 999}
  ]
}
```

---

## Your First Layer — GeoJSON file

The plugin also ships with a sample GeoJSON file:

```
geodata_catalog/resources/aerodromes_sample.geojson
```

1. Click **Add Source**.
2. Fill in:
   - **Name:** `Aerodromes GeoJSON`
   - **Type:** `GeoJSON`
   - **Configuration JSON:**

```json
{
  "path": "C:/path/to/geodata_catalog/resources/aerodromes_sample.geojson"
}
```

3. Click **Save**, then **Refresh**, then double-click the layer.

---

## User Interface Overview

```
GeoData Catalog panel
├── Datasource Tree
│   ├── Database Sources
│   │   └── Oracle           ← lists Oracle datasources
│   ├── REST Sources         ← lists REST datasources
│   └── File Sources
│       ├── GeoJSON          ← lists GeoJSON datasources
│       └── KML              ← lists KML datasources
├── Layer List               ← shows layers for selected datasource
└── Buttons
    ├── Add Source           ← create a new datasource
    ├── Edit Source          ← modify name/type/config
    ├── Delete Source        ← permanently remove datasource
    ├── Refresh              ← re-discover layers from source
  └── Load Layer           ← load selected layer into QGIS
```

### Keyboard / mouse shortcuts

| Action | How |
|---|---|
| Load a layer | Double-click it in the Layer List |
| Select a datasource | Single-click in the Datasource Tree |
| Refresh layers | Click **Refresh** or single-click a datasource item |

### All loadable layers overview

To see all loadable file sources and database tables in one list:

1. Open the **Data Panel**.
2. The Data Panel opens as a larger separate window centered over the map canvas with an aggregated list across all datasources.
3. Double-click any entry to load it directly.

---

## Checking Logs

If a layer does not load, open the log panel:

**View → Panels → Log Messages** → select the **GeoData Catalog** tab.

You will see messages like:

```
INFO   Loading layer 'Aerodromes' (provider: ogr, uri: C:/...kml|layerid=1)
INFO   Layer valid, assigning CRS and style for 'Aerodromes'
INFO   Adding layer 'Aerodromes' to QGIS project
INFO   Layer successfully loaded: Aerodromes
```

Error messages include the full reason, for example:

```
ERROR  Layer 'Aerodromes' is invalid. Error: Unable to open datasource ...
```

See [Troubleshooting](troubleshooting.md) for common error causes and fixes.
