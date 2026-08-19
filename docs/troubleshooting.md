# Troubleshooting

This page covers the most common problems encountered when using GeoData Catalog and explains how to diagnose and resolve them.

---

## How to Read the Logs

All plugin messages are written to the QGIS **Log Messages** panel under the tag **GeoData Catalog**.

Open it via: **View → Panels → Log Messages**

When a layer fails to load, look for lines starting with `ERROR`. Example:

```
INFO   Loading layer 'Aerodromes' (provider: ogr, uri: C:/data/aerodromes.kml|layerid=1)
ERROR  Layer 'Aerodromes' is invalid. Error: Unable to open datasource with `ogr` provider
```

The `ERROR` line contains the full reason and is the starting point for diagnosis.

---

## Plugin Does Not Appear in QGIS

**Symptom:** The plugin is not listed in *Manage and Install Plugins*, or it appears but refuses to activate.

**Causes and fixes:**

| Cause | Fix |
|---|---|
| Folder name contains a dot | Rename the folder from `geodata.catalog` to `geodata_catalog` |
| `metadata.txt` is missing | Ensure `metadata.txt` is directly in the `geodata_catalog` folder (not in a subfolder) |
| Python import error | Open the QGIS Python console and type `import geodata_catalog`; read the traceback |
| Wrong QGIS version | Check `qgisMinimumVersion` in `metadata.txt` — the plugin requires QGIS 3.22 or later |

---

## "Discovered 0 layers" After Refresh

**Symptom:** Clicking **Refresh** shows no layers in the layer list, and the log says `Discovered 0 layers`.

### KML source

- Verify the path exists and is readable.
- Open the file in a text editor and check that it is valid XML starting with `<kml ...>`.
- Try adding the file directly in QGIS via *Layer → Add Layer → Add Vector Layer* to confirm QGIS/OGR can open it.
- Check that the KML contains at least one `<Folder>` or `<Placemark>` at the document level.

### GeoJSON source

- Verify the path exists.
- Open the file in a text editor and check the top-level `"type"` field is `"FeatureCollection"` or `"Feature"`.
- If using a **directory** path, check that at least one `.geojson` or `.json` file is present.

### Oracle source

- Verify the connection parameters (host, port, credentials).
- Check that the database user has `SELECT` permission on `ALL_SDO_GEOM_METADATA`.
- No rows in the metadata view means no spatial layers are registered — the database might be empty or the schema filter is too restrictive.

### REST source

- Click **Refresh** while watching the log for HTTP errors (4xx, 5xx).
- Verify the URL is reachable from the machine running QGIS.
- Check that `requests` is installed: open the Python console and type `import requests`.

---

## Layer Appears in List But Does Not Load

**Symptom:** The layer is visible in the catalog layer list, but double-clicking it shows an error dialog or nothing happens.

### Diagnosis

Open the log and look for an `ERROR` line after clicking **Load Layer**. The error message contains the provider URI and the QGIS validation error.

### Common causes

| Log message | Likely cause | Fix |
|---|---|---|
| `Unable to open datasource` | File path no longer valid or file was moved | Update the datasource path in **Edit Source** |
| `Layer ... failed validation: ...` | Provider URI is malformed | Check the provider URI in the log; re-discover layers by clicking **Refresh** |
| `Failed to create layer ... QGIS runtime is not available` | Running outside QGIS | This should not happen in normal use; ensure the plugin is run from within QGIS |
| `QGIS project instance is not available` | Plugin initialisation problem | Restart QGIS and re-activate the plugin |
| `Failed to connect to Oracle datasource` | Network or credentials issue | Test with SQL*Plus or another Oracle client |
| `python-oracledb is not installed` | oracledb package missing | Run `pip install python-oracledb>=2.2.0` in the QGIS Python environment |
| `requests package is not installed` | requests package missing | Run `pip install requests>=2.32.0` in the QGIS Python environment |
| `Excel export failed. Install 'openpyxl'...` | `openpyxl` package missing for `.xlsx` export | Run `pip install openpyxl` in the QGIS Python environment, or export as CSV |

---

## QGIS Layers Panel Menu Shows Only "Open Custom View…"

**Symptom:** Right-clicking a layer in the QGIS **Layers panel** shows only the GeoData Catalog action and none of the normal QGIS items such as Rename, Remove, or Duplicate.

**Cause:** A custom context menu hook replaced the default QGIS layer-tree menu instead of extending it.

**Fix:** Update to a version of GeoData Catalog that appends the custom action via the QGIS context menu signal. If you are testing a local build, reload the plugin after updating.

---

## Opening Custom View Fails With `setAttribute` TypeError

**Symptom:** Opening **Open Custom View…** raises this error:

```
TypeError: setAttribute(self, attribute: Qt.WidgetAttribute, on: bool = True): argument 1 has unexpected type 'int'
```

**Cause:** The plugin used an integer fallback for `WA_DeleteOnClose`. In PyQt6/QGIS4, `setAttribute` requires a `Qt.WidgetAttribute` enum value, not an `int`.

**Fix:** Update to a version that resolves `WA_DeleteOnClose` via PyQt5/PyQt6-compatible enum lookup and only calls `setAttribute` when the enum is available. Reload the plugin after updating.

---

## KML: Layer Loads But Is Empty

**Symptom:** The layer is added to the QGIS Layers panel but shows no features on the map.

**Possible causes:**

- The CRS is wrong. KML files should be WGS84 (`EPSG:4326`). Check the layer's CRS in QGIS (*Layer Properties → Source*) and set it to `EPSG:4326` if it is missing.
- The KML uses `<GroundOverlay>` or `<NetworkLink>` elements instead of `<Placemark>` — these are not vector features and cannot be shown as a vector layer.
- The loaded sublayer is the folder node rather than the actual feature layer. Click **Refresh** again and look for additional sublayers.

---

## KML: "Discovered 2 layers" But Only 1 Is Useful

**Symptom:** The KML file has nested folders and the discovery returns extra "container" sublayers.

**Explanation:** The OGR KML provider can expose intermediate folder nodes as separate sublayers. Container folders may contain 0 features.

**Fix:** Load only the sublayer that has a known geometry (e.g. "Aerodromes") and ignore container sublayers.  
A future enhancement will filter out sublayers with 0 features automatically.

---

## Flight Level Filter Hides All Features

**Symptom:** The layer loads, but after applying the flight level filter the map and attribute table become empty.

**Possible causes:**

- The datasource does not use `fl_lower` / `fl_upper` (case-insensitive matching is supported).
- The selected FL range does not overlap any features.
- The values are stored in a different unit or scale than the filter expects.

**Fix:**

- Check the real field names in the layer attribute table.
- Try disabling the FL filter to confirm that the layer itself loads correctly.
- Ensure your datasource exposes FL lower/upper bounds with names compatible with `fl_lower` / `fl_upper` (case-insensitive).
- If needed, reload/update the plugin so the latest FL field-resolution logic is active.

---

## Layer Filter Dialog Is Too Tall Without Flight Level Controls

**Symptom:** Opening **Layer Filter** for a layer without FL support shows a dialog with excessive empty space below the visible fields.

**Cause:** Older versions used a fixed dialog height formula instead of sizing the window to the controls that were actually rendered.

**Fix:** Update/reload to a version where the dialog uses dynamic sizing (`adjustSize`) with a minimum width. The dialog height now follows the visible field groups.

---

## Layer Filter: FL Slider Crashes With Qt Enum AttributeError

**Symptom:** Opening or using **Layer Filter** raises one of these errors:

```
AttributeError: type object 'QPainter' has no attribute 'Antialiasing'
AttributeError: type object 'Qt' has no attribute 'NoPen'
```

**Cause:** Qt enum values differ between QGIS/PyQt versions (Qt5 vs Qt6), and older plugin code used only one enum form.

**Fix:** Update/reload to a version that resolves both enum variants (`QPainter.Antialiasing` / `QPainter.RenderHint.Antialiasing` and `Qt.NoPen` / `Qt.PenStyle.NoPen`).

---

## Layer Filter: Cleared Dropdown Value Still Stays Active

**Symptom:** In **Layer Filter**, you select a value in a distinct dropdown (for example `flight_sectorid`), click **Apply**, then set that dropdown back to **(no filter)** and click **Apply** again, but the old filter condition still remains active.

**Cause:** Older plugin versions only removed attribute clauses for fields that still had a value at apply time. A field that was cleared could therefore leave its previous clause in the subset string.

**Fix:** Update/reload to a version where apply first removes all configured searchable-column clauses and then rebuilds the filter from current dialog values. After this fix, clearing a dropdown removes that field condition from the layer filter as expected.

---

## REST: Layer Data Is Stale

**Symptom:** The layer shows old data even after re-opening QGIS.

**Explanation:** The REST connector writes the fetched GeoJSON to a temporary file. A layer that is already loaded in QGIS reads from that cached temporary file.

**Fix:** Remove the layer from the QGIS project and load it again via the catalog. Each new **Load Layer** action fetches fresh data from the server.

---

## Configuration JSON Is Rejected

**Symptom:** The **Save** button in the Add/Edit Source dialog returns an error or the datasource does not appear in the tree.

**Checks:**

1. Paste the JSON into a JSON validator (e.g. [jsonlint.com](https://jsonlint.com)) to verify it is valid JSON.
2. Ensure all keys are lowercase strings in double quotes.
3. Check that required fields are present (see [Adding Sources](adding-sources.md) for each type).
4. Numbers such as `port` must be integers (no quotes): `"port": 5432`, not `"port": "5432"`.

---

## Where Is My Configuration Saved?

**Symptom:** You want to back up or manage datasource configuration without touching plugin code files.

**Answer:** GeoData Catalog writes configuration to a user-writable JSON file in the active QGIS profile app-data area (`GeoDataCatalog/config.json`) and mirrors it to QGIS settings keys for compatibility.

**Why this is better than plugin directory storage:**

- Plugin folders are often read-only for end users.
- Plugin updates can overwrite plugin files.
- User profile storage is per-user and intended for user-managed configuration.

---

## Changing a Datasource Type

**Symptom:** After editing a datasource and changing its type, the layer list is empty or shows incorrect layers.

**Fix:** After changing the type, click **Refresh** to re-discover layers with the new connector. The layer cache is cleared on edit.

---

## Import Errors Outside QGIS

If you run the plugin code directly with Python (e.g. for testing), you will see:

```
ModuleNotFoundError: No module named 'qgis'
```

This is expected. The plugin requires the QGIS Python runtime (`qgis.core`, `qgis.PyQt`). Test files use mocks and fakes to bypass this dependency. See [Development](development.md) for how to run tests.
