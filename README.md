# GeoData Catalog (QGIS Plugin)

GeoData Catalog is a metadata-driven QGIS plugin that provides a unified way to discover,
configure, browse, and load business geospatial datasets from Oracle Spatial, GeoJSON,
KML, and REST GeoJSON sources.

## Architecture

- Connector pattern with `BaseConnector` abstraction
- Repository layer over QGIS settings for datasource and layer metadata
- Service layer for datasource lifecycle, discovery, and QGIS loading orchestration
- Thin UI layer (DockWidget and dialogs) with signal-based interaction
- Centralized plugin logging to QGIS message log

## Business Dataset Model

Users browse business-friendly datasets through configured display names and groups, not
technical table names or API endpoint details.

## Database Login

Oracle users log in once per plugin session through **Connect** in the GeoData Catalog
toolbar. QGIS starts without login prompts or automatic database login. The toolbar shows the active `user@database`, environment and configurable
environment color. The login is shared by all enabled sources on that host/port/service.
**Disconnect** removes matching loaded catalog layers after confirmation; disconnect
before selecting another database.

Database passwords are no longer stored in configuration. Temporary encrypted QGIS
Authentication Manager records are used instead and removed on disconnect/unload.
Optionally select **Remember password (encrypted in QGIS)** to retain a separate
encrypted login between sessions. Connect still requires an explicit user action;
**Forget saved login for this database** removes the remembered credentials.
Existing plaintext Oracle settings are migrated automatically. See
[Oracle configuration and session lifecycle](docs/adding-sources.md#login-and-session-lifecycle)
for setup, prerequisites, migration and saved-project behavior.

## Testing

Run unit tests with:

```bash
pytest geodata_catalog/tests -q
```

## Local First Mode (Without Database)

You can run the plugin locally using only file-based datasources:

- KML sample: `geodata_catalog/resources/aerodromes_sample.kml`
- GeoJSON sample: `geodata_catalog/resources/aerodromes_sample.geojson`
- File-only config template: `geodata_catalog/resources/example_configuration_files_only.json`

In this mode, Oracle is not required.
