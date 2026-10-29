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

## Work Profiles and Database Environments

- The default **User** work profile exposes the Data Panel, without configuration actions.
- Use **Work profile...** on the toolbar or plugin menu to switch freely to **Developer**.
  Developer can manage sources, layer configuration, and user profiles.
- **Manage user profiles...** lets developers create named user profiles and select
  their visible layers. An empty selection shows no layers; **All catalog layers**
  also includes layers added later.
- Oracle sources with identical technical layer names can share a `catalog_id` in
  their connection JSON. Configuration and profile visibility then follow the
  logical layer across environments, using only the currently authenticated endpoint.
- Configured layers missing from the current database remain visible with a
  **Not available** status and an explanation; loading them is blocked.

Profiles are local, freely selectable work modes, **not access control**. They do
not replace Oracle permissions or remove layers already loaded into a QGIS project.
See [Getting Started](docs/getting-started.md#work-profiles-and-layer-visibility)
for setup and migration details.

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
