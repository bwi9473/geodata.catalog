# GeoData Catalog — Documentation

**Version:** 1.0.0  
**QGIS compatibility:** 3.22 and later (including 4.x)

GeoData Catalog is a metadata-driven QGIS plugin that provides a unified catalog for discovering, configuring and loading geospatial datasets from multiple source types: Oracle Spatial, PostGIS, local GeoJSON files, local KML files, and GeoJSON REST endpoints.

---

## Table of Contents

| Document | Description |
|---|---|
| [Getting Started](getting-started.md) | Installation, first run and plugin setup |
| [Adding Sources](adding-sources.md) | Complete guide with JSON examples for every source type |
| [Architecture](architecture.md) | Code structure, component overview and data flow |
| [Development](development.md) | Adding new connectors, running tests, contributing |
| [Troubleshooting](troubleshooting.md) | Common problems and how to resolve them |

---

## Supported Datasource Types

| Type | Key | Description |
|---|---|---|
| KML | `kml` | Local `.kml` or `.kmz` file with OGR/QGIS sublayer discovery |
| GeoJSON | `geojson` | Local `.geojson` / `.json` file or directory |
| Oracle Spatial | `oracle` | Oracle database with SDO_GEOMETRY columns |
| PostGIS | `postgis` | PostgreSQL/PostGIS database via `geometry_columns` |
| REST GeoJSON | `rest` | HTTP endpoint returning GeoJSON `FeatureCollection` |

---

## Quick Start

1. Copy the plugin folder to your QGIS plugins directory.
2. Activate **GeoData Catalog** in *Plugins → Manage and Install Plugins*.
3. Click **Add Source** in the catalog panel and choose a source type.
4. Paste the appropriate configuration JSON (see [Adding Sources](adding-sources.md)).
5. Click **Refresh** to discover layers, then double-click a layer to load it.

---

## Log Messages

All plugin activity is written to the QGIS **Log Messages** panel under the tag `GeoData Catalog`.  
Open it via *View → Panels → Log Messages* to diagnose loading issues.
