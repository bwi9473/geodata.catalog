# Eerste test in QGIS (GeoData Catalog)

## 1. Plugin in QGIS beschikbaar maken

1. Open QGIS 3.22 of nieuwer (ook getest met QGIS 4.0.x).
2. Ga naar de Python plugin map:
   - Windows typisch: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins`
3. Kopieer de volledige workspace-map `geodata.catalog` naar die plugin map.
4. Hernoem de map in de plugin map naar `geodata_catalog`.
  - Gebruik **geen punt** in de mapnaam (dus niet `geodata.catalog`).
5. Controleer dat deze bestanden direct in die map staan:
  - `metadata.txt`
  - `__init__.py`
  - submap `geodata_catalog`
6. Open de submap `geodata_catalog` en controleer dat daar `plugin.py` staat.
7. Herstart QGIS.

## 2. Plugin activeren

1. In QGIS: Plugins > Manage and Install Plugins.
2. Zoek naar **GeoData Catalog**.
3. Vink de plugin aan.
4. Open de plugin via menu **GeoData Catalog** of via toolbar-icoon.

## 3. KML test datasource toevoegen

Gebruik deze lokale testfile:
- `geodata_catalog/resources/aerodromes_sample.kml`

In de plugin:
1. Klik **Add Source**.
2. Name: `Aerodromes KML`.
3. Type: `KML`.
4. Configuration JSON:

```json
{
  "path": "C:/Myworkspace/Copilot/geodata.catalog/geodata_catalog/resources/aerodromes_sample.kml"
}
```

5. Klik **Save**.
6. Selecteer de datasource in de boom en klik **Refresh**.
7. Dubbelklik op de laag of klik **Load Layer**.

## 4. Volledig lokaal testen zonder database

Je kan de plugin volledig lokaal gebruiken met alleen file sources.

Beschikbare lokale testbestanden:
- `geodata_catalog/resources/aerodromes_sample.kml`
- `geodata_catalog/resources/aerodromes_sample.geojson`

Voeg optioneel ook een GeoJSON datasource toe:

```json
{
  "path": "C:/Myworkspace/Copilot/geodata.catalog/geodata_catalog/resources/aerodromes_sample.geojson"
}
```

Datasource instellingen:
1. Name: `Aerodromes GeoJSON`
2. Type: `GeoJSON`
3. Klik **Save**
4. Selecteer datasource > **Refresh** > **Load Layer**

## 5. Verwacht resultaat

- Je ziet een KML-laag met aerodromes (punten) in QGIS.
- Attributen zoals ICAO/IATA/type zijn zichtbaar in de attributentabel.
- Laag wordt geladen in WGS84 (`EPSG:4326`).

## 6. Snelle troubleshooting

- Plugin verschijnt niet:
  - Controleer of de mapnaam exact `geodata_catalog` is.
  - Controleer of `metadata.txt` in die map staat.
- Laag laadt niet:
  - Controleer of het pad in JSON bestaat.
  - Gebruik forward slashes (`/`) in het pad.
- Import errors in logs:
  - Dit is normaal buiten QGIS runtime; test altijd vanuit QGIS zelf.
