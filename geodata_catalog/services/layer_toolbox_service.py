from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import quote

from geodata_catalog.logging_utils import PluginLogger

try:
    from qgis.core import (
        QgsApplication,
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsCategorizedSymbolRenderer,
        QgsFeature,
        QgsFillSymbol,
        QgsField,
        QgsGeometry,
        QgsMapLayerType,
        QgsPointXY,
        QgsProject,
        QgsRasterLayer,
        QgsRectangle,
        QgsRendererCategory,
        QgsRuleBasedRenderer,
        QgsSymbol,
        QgsVectorLayer,
        QgsWkbTypes,
    )
    from qgis.PyQt.QtCore import QVariant
    from qgis.PyQt.QtGui import QColor
except ImportError:  # pragma: no cover
    QgsApplication = None
    QgsCoordinateReferenceSystem = None
    QgsCoordinateTransform = None
    QgsCategorizedSymbolRenderer = None
    QgsFeature = None
    QgsFillSymbol = None
    QgsField = None
    QgsGeometry = None
    QgsMapLayerType = None
    QgsPointXY = None
    QgsProject = None
    QgsRasterLayer = None
    QgsRectangle = None
    QgsRendererCategory = None
    QgsRuleBasedRenderer = None
    QgsSymbol = None
    QgsVectorLayer = None
    QgsWkbTypes = None
    QVariant = None
    QColor = None


class LayerToolboxService:
    """Build and toggle helper layers for loaded QGIS vector layers."""

    VERTEX_SUFFIX = " [Vertices]"
    CONNECTION_SUFFIX = " [Point Connections]"
    HELPER_SOURCE_PROPERTY = "geodata_catalog/helper_source_layer_id"
    HELPER_KIND_PROPERTY = "geodata_catalog/helper_kind"
    BASEMAP_NAME_PROPERTY = "geodata_catalog/basemap_name"
    BASEMAP_KIND = "background_basemap"
    BASEMAP_DEFAULT = "World Map"
    BASEMAP_SETTINGS_KEY = "layer_toolbox/selected_basemap"
    MUAC_EXTENT_WGS84 = (2.0, 49.0, 9.5, 53.8)

    BASEMAPS: tuple[dict[str, str], ...] = (
        {
            "name": "World Map",
            "provider": "ogr",
            "path": "world_map.gpkg",
            "layer_name": "country_polygons",
            "preview_file": "resources/basemap_previews/world_map.svg",
            "aliases": ("World Map (QGIS)",),
        },
        {
            "name": "Nominatim / OpenStreetMap Standard",
            "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            "preview_file": "resources/basemap_previews/nominatim_osm_standard.svg",
            "aliases": ("Nominatim", "OpenStreetMap Standard", "OSM Standard"),
        },
        {
            "name": "CartoDB Positron",
            "url": "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
            "preview_file": "resources/basemap_previews/cartodb_positron.svg",
        },
        {
            "name": "CartoDB Dark Matter (No Labels)",
            "url": "https://a.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png",
            "preview_file": "resources/basemap_previews/cartodb_darkmatter_nolabels.svg",
        },
        {
            "name": "Esri World Gray Canvas",
            "url": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
            "preview_file": "resources/basemap_previews/esri_world_gray_canvas.svg",
        },
    )

    def __init__(self, logger: PluginLogger, project=None, settings_manager=None) -> None:
        self._logger = logger
        self._project = project or (QgsProject.instance() if QgsProject else None)
        self._settings_manager = settings_manager

    def set_polygon_vertices_visible(self, layer, visible: bool) -> None:
        """Toggle a helper point layer that shows all polygon vertices."""
        if self._project is None:
            self._logger.warning("Cannot toggle polygon vertices: QGIS project is unavailable.")
            return
        if not self._is_vector_layer(layer) or not self._is_polygon_layer(layer):
            self._logger.warning("Cannot toggle polygon vertices: selected layer is not polygonal.")
            return

        if not visible:
            self._remove_helper_layer(layer.id(), "vertices")
            return

        helper_name = f"{layer.name()}{self.VERTEX_SUFFIX}"
        self._remove_helper_layer(layer.id(), "vertices")
        helper = self._create_memory_layer("Point", helper_name, layer)
        if helper is None:
            return

        self._tag_helper_layer(helper, layer.id(), "vertices")
        provider = helper.dataProvider()
        features = self._build_vertex_features(layer)
        if features:
            provider.addFeatures(features)
            helper.updateExtents()
        self._project.addMapLayer(helper)
        self._logger.info(
            f"Vertex helper layer created for '{layer.name()}' with {len(features)} vertices."
        )

    def set_point_connections_visible(
        self,
        layer,
        visible: bool,
        group_field: str = "",
        order_field: str = "",
        color_by_group: bool = False,
        line_width: float = 1.5,
    ) -> None:
        """Toggle a helper line layer that connects related points."""
        if self._project is None:
            self._logger.warning("Cannot toggle point connections: QGIS project is unavailable.")
            return
        if not self._is_vector_layer(layer) or not self._is_point_layer(layer):
            self._logger.warning("Cannot toggle point connections: selected layer is not point-based.")
            return

        if not visible:
            self._remove_helper_layer(layer.id(), "point_connections")
            return

        helper_name = f"{layer.name()}{self.CONNECTION_SUFFIX}"
        self._remove_helper_layer(layer.id(), "point_connections")
        helper = self._create_memory_layer("LineString", helper_name, layer)
        if helper is None:
            return

        self._ensure_connection_fields(helper)
        self._tag_helper_layer(helper, layer.id(), "point_connections")
        provider = helper.dataProvider()
        features = self._build_connection_features(layer, group_field=group_field, order_field=order_field)
        if features:
            provider.addFeatures(features)
            helper.updateExtents()
        normalized_line_width = self._normalize_line_width(line_width)
        if color_by_group:
            self._apply_group_color_renderer(helper, normalized_line_width)
        else:
            self._apply_single_color_renderer(helper, normalized_line_width)
        self._project.addMapLayer(helper)
        self._logger.info(
            f"Point-connection helper layer created for '{layer.name()}' with {len(features)} line(s)."
        )

    def has_vertices_helper(self, layer) -> bool:
        return self._find_helper_layer(layer.id(), "vertices") is not None

    def has_point_connections_helper(self, layer) -> bool:
        return self._find_helper_layer(layer.id(), "point_connections") is not None

    def list_basemap_names(self) -> list[str]:
        return [str(item.get("name", "")).strip() for item in self.BASEMAPS if item.get("name")]

    def list_basemap_options(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.BASEMAPS]

    @classmethod
    def default_basemap_name(cls) -> str:
        return cls.BASEMAP_DEFAULT

    @classmethod
    def muac_extent_wgs84(cls) -> tuple[float, float, float, float]:
        return cls.MUAC_EXTENT_WGS84

    def set_basemap(self, basemap_name: str) -> bool:
        if self._project is None:
            self._logger.warning("Cannot set basemap: QGIS project is unavailable.")
            return False

        basemap = self._find_basemap_definition(basemap_name)
        if basemap is None:
            self._logger.warning(f"Cannot set basemap: unknown basemap '{basemap_name}'.")
            return False

        layer_name = str(basemap.get("name"))
        is_vector = str(basemap.get("provider", "")).strip().lower() == "ogr"

        existing_layers = self._find_existing_basemap_layers()
        active_layer = existing_layers[0] if existing_layers else None
        active_layer_id = active_layer.id() if active_layer is not None and hasattr(active_layer, "id") else ""

        for duplicate_layer in existing_layers[1:]:
            self._remove_layer_by_id(duplicate_layer.id())

        if active_layer is not None:
            active_name = str(active_layer.customProperty(self.BASEMAP_NAME_PROPERTY, "")).strip()
            if active_name.casefold() == layer_name.casefold():
                if is_vector:
                    self._apply_world_map_style(active_layer)
                self._save_selected_basemap(layer_name)
                self._logger.info(f"Basemap '{layer_name}' is already active.")
                return True

            # Try in-place swap only for raster-to-raster transitions
            if not is_vector and QgsRasterLayer is not None:
                encoded_url = quote(str(basemap.get("url", "")), safe=":/?&={}%")
                uri = f"type=xyz&url={encoded_url}"
                set_data_source = getattr(active_layer, "setDataSource", None)
                if callable(set_data_source):
                    try:
                        if set_data_source(uri, layer_name, "wms") and active_layer.isValid():
                            if hasattr(active_layer, "setName"):
                                active_layer.setName(layer_name)
                            self._tag_basemap_layer(active_layer, layer_name)
                            if hasattr(active_layer, "triggerRepaint"):
                                active_layer.triggerRepaint()
                            self._save_selected_basemap(layer_name)
                            self._logger.info(f"Basemap '{layer_name}' has been applied.")
                            return True
                    except Exception as exc:
                        self._logger.warning(
                            f"Failed to update existing basemap layer '{layer_name}': {exc}"
                        )

            if not is_vector:
                self._remove_layer_by_id(active_layer.id())

        # Create the new basemap layer
        if is_vector:
            if QgsVectorLayer is None:
                self._logger.warning("Cannot set vector basemap: QgsVectorLayer is unavailable.")
                return False
            path = self._resolve_qgis_world_map_path()
            if not path:
                self._logger.warning(
                    f"Cannot set basemap '{layer_name}': world_map.gpkg not found in QGIS data directory."
                )
                return False
            normalized_path = str(path).replace("\\", "/")
            layer_source_name = str(basemap.get("layer_name", "")).strip()
            candidate_layer_names = [
                layer_source_name,
                "country_polygons",
                "countries",
                "country_boundaries",
                "country_borders",
                "world_countries",
            ]
            candidate_sources = []
            seen_sources: set[str] = set()
            for name in candidate_layer_names:
                clean_name = str(name or "").strip()
                if not clean_name:
                    continue
                source = f"{normalized_path}|layername={clean_name}"
                if source in seen_sources:
                    continue
                seen_sources.add(source)
                candidate_sources.append(source)

            layer = None
            selected_source_uri = ""
            for source_uri in candidate_sources:
                candidate = QgsVectorLayer(source_uri, layer_name, "ogr")
                if candidate is None or not candidate.isValid():
                    continue

                # Accept only likely country-level layers (avoid sub-national admin boundaries).
                has_country_field = False
                try:
                    fields = candidate.fields()
                    if fields is not None and hasattr(fields, "names"):
                        names = {str(name).strip().casefold() for name in fields.names()}
                        expected = {
                            "name",
                            "name_en",
                            "name_long",
                            "admin",
                            "iso_a2",
                            "iso_a3",
                            "country",
                            "cntry_name",
                        }
                        has_country_field = any(key in names for key in expected)
                except Exception:
                    has_country_field = False

                if not has_country_field:
                    continue

                layer = candidate
                selected_source_uri = source_uri
                break
        else:
            if QgsRasterLayer is None:
                self._logger.warning("Cannot set basemap: QgsRasterLayer is unavailable.")
                return False
            encoded_url = quote(str(basemap.get("url", "")), safe=":/?&={}%")
            uri = f"type=xyz&url={encoded_url}"
            layer = QgsRasterLayer(uri, layer_name, "wms")

        if layer is None or not layer.isValid():
            self._logger.warning(f"Failed to create basemap layer '{layer_name}'.")
            return False

        if is_vector and active_layer_id:
            self._remove_layer_by_id(active_layer_id)

        if is_vector:
            self._apply_world_map_style(layer)
            if selected_source_uri:
                self._logger.info(
                    f"World Map basemap loaded from source '{selected_source_uri}'."
                )

        self._tag_basemap_layer(layer, layer_name)
        try:
            self._project.addMapLayer(layer, False)
            root = self._project.layerTreeRoot()
            if root is None or not hasattr(root, "insertLayer"):
                self._project.addMapLayer(layer)
            else:
                try:
                    children = root.children() if hasattr(root, "children") else []
                except Exception:
                    children = []
                root.insertLayer(len(children), layer)
        except Exception as exc:
            self._logger.warning(f"Failed to insert basemap layer '{layer_name}': {exc}")
            return False

        self._save_selected_basemap(layer_name)
        self._logger.info(f"Basemap '{layer_name}' has been applied.")
        return True

    def preferred_basemap_name(self) -> str:
        raw = ""
        if self._settings_manager is not None:
            try:
                raw = str(
                    self._settings_manager.get_json(self.BASEMAP_SETTINGS_KEY, self.BASEMAP_DEFAULT)
                    or ""
                ).strip()
            except Exception:
                raw = ""
        if not raw:
            raw = self.BASEMAP_DEFAULT

        basemap = self._find_basemap_definition(raw)
        if basemap is None:
            return self.BASEMAP_DEFAULT
        return str(basemap.get("name", self.BASEMAP_DEFAULT)).strip() or self.BASEMAP_DEFAULT

    def ensure_preferred_basemap_loaded(self) -> bool:
        if self._find_existing_basemap_layer() is not None:
            return True
        return self.set_basemap(self.preferred_basemap_name())

    def current_basemap_name(self) -> str:
        layer = self._find_existing_basemap_layer()
        if layer is None:
            return self.preferred_basemap_name()

        raw_name = str(layer.customProperty(self.BASEMAP_NAME_PROPERTY, "") or "").strip()
        if not raw_name and hasattr(layer, "name"):
            raw_name = str(layer.name()).strip()

        basemap = self._find_basemap_definition(raw_name)
        if basemap is None:
            return self.BASEMAP_DEFAULT
        return str(basemap.get("name", self.BASEMAP_DEFAULT)).strip() or self.BASEMAP_DEFAULT

    def focus_muac_on_canvas(self, iface) -> bool:
        if iface is None:
            self._logger.warning("Cannot focus MUAC: iface is unavailable.")
            return False
        canvas = getattr(iface, "mapCanvas", lambda: None)()
        if canvas is None:
            self._logger.warning("Cannot focus MUAC: map canvas is unavailable.")
            return False

        extent = self._resolve_muac_extent_for_canvas(canvas)
        if extent is None:
            self._logger.warning("Cannot focus MUAC: failed to resolve map extent.")
            return False

        try:
            canvas.setExtent(extent)
            if hasattr(canvas, "refresh"):
                canvas.refresh()
            self._logger.info("Map focus moved to MUAC control area.")
            return True
        except Exception as exc:
            self._logger.warning(f"Cannot focus MUAC: {exc}")
            return False

    def apply_flight_level_range_rules(
        self,
        layer,
        lower_field: str = "fl_lower",
        upper_field: str = "fl_upper",
    ) -> bool:
        """Apply a rule-based renderer per distinct flight-level range."""
        if not self._is_vector_layer(layer):
            self._logger.warning("Cannot apply FL range rules: selected layer is not vector-based.")
            return False
        if QgsRuleBasedRenderer is None or QgsSymbol is None:
            self._logger.warning("Cannot apply FL range rules: QGIS renderer classes are unavailable.")
            return False

        resolved_lower = self._resolve_layer_field_name(layer, lower_field)
        resolved_upper = self._resolve_layer_field_name(layer, upper_field)
        if not resolved_lower or not resolved_upper:
            self._logger.warning("Cannot apply FL range rules: FL fields are missing on selected layer.")
            return False

        ranges = self._extract_flight_level_ranges(layer.getFeatures(), resolved_lower, resolved_upper)
        if not ranges:
            self._logger.warning("Cannot apply FL range rules: no valid FL ranges found on selected layer.")
            return False

        base_symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        if base_symbol is None:
            self._logger.warning("Cannot apply FL range rules: failed to create base symbol.")
            return False

        renderer = QgsRuleBasedRenderer(base_symbol)
        root_rule = renderer.rootRule()
        try:
            for child in list(root_rule.children()):
                root_rule.removeChild(child)
        except Exception:
            pass

        for lower, upper in ranges:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            if symbol is None:
                continue
            symbol_color = self._color_for_group_key(f"{lower}-{upper}")
            if symbol_color is not None:
                symbol.setColor(symbol_color)

            rule = QgsRuleBasedRenderer.Rule(symbol)
            rule.setLabel(self._format_fl_range_label(lower, upper))
            rule.setFilterExpression(
                self._build_fl_range_expression(resolved_lower, resolved_upper, lower, upper)
            )
            root_rule.appendChild(rule)

        layer.setRenderer(renderer)
        if hasattr(layer, "triggerRepaint"):
            layer.triggerRepaint()
        self._logger.info(
            f"Applied FL range rules on '{layer.name()}' with {len(ranges)} distinct range(s)."
        )
        return True

    def _is_vector_layer(self, layer) -> bool:
        if layer is None or QgsMapLayerType is None:
            return False
        layer_type = getattr(layer, "type", None)
        if not callable(layer_type):
            return False
        try:
            return layer_type() == QgsMapLayerType.VectorLayer
        except Exception:
            return False

    def _is_polygon_layer(self, layer) -> bool:
        if QgsWkbTypes is None or layer is None:
            return False
        wkb_type_fn = getattr(layer, "wkbType", None)
        if not callable(wkb_type_fn):
            return False
        try:
            geom_type = QgsWkbTypes.geometryType(wkb_type_fn())
            return geom_type == QgsWkbTypes.PolygonGeometry
        except Exception:
            return False

    def _is_point_layer(self, layer) -> bool:
        if QgsWkbTypes is None or layer is None:
            return False
        wkb_type_fn = getattr(layer, "wkbType", None)
        if not callable(wkb_type_fn):
            return False
        try:
            geom_type = QgsWkbTypes.geometryType(wkb_type_fn())
            return geom_type == QgsWkbTypes.PointGeometry
        except Exception:
            return False

    def _create_memory_layer(self, geometry_type: str, layer_name: str, source_layer):
        if QgsVectorLayer is None:
            self._logger.warning("Cannot create memory layer: QgsVectorLayer is unavailable.")
            return None
        crs = ""
        try:
            source_crs = source_layer.crs()
            if source_crs is not None and hasattr(source_crs, "authid"):
                crs = source_crs.authid() or ""
        except Exception:
            crs = ""
        uri = f"{geometry_type}?crs={crs}" if crs else geometry_type
        layer = QgsVectorLayer(uri, layer_name, "memory")
        if layer is None or not layer.isValid():
            self._logger.warning(f"Failed to create helper memory layer '{layer_name}'.")
            return None
        return layer

    def _tag_helper_layer(self, helper_layer, source_layer_id: str, kind: str) -> None:
        helper_layer.setCustomProperty(self.HELPER_SOURCE_PROPERTY, source_layer_id)
        helper_layer.setCustomProperty(self.HELPER_KIND_PROPERTY, kind)

    def _tag_basemap_layer(self, layer, basemap_name: str) -> None:
        self._tag_helper_layer(layer, "", self.BASEMAP_KIND)
        layer.setCustomProperty(self.BASEMAP_NAME_PROPERTY, basemap_name)

    def _find_helper_layer(self, source_layer_id: str, kind: str):
        if self._project is None:
            return None
        try:
            for layer in self._project.mapLayers().values():
                source_id = str(layer.customProperty(self.HELPER_SOURCE_PROPERTY, ""))
                helper_kind = str(layer.customProperty(self.HELPER_KIND_PROPERTY, ""))
                if source_id == source_layer_id and helper_kind == kind:
                    return layer
        except Exception:
            return None
        return None

    def _remove_helper_layer(self, source_layer_id: str, kind: str) -> None:
        helper = self._find_helper_layer(source_layer_id, kind)
        if helper is None or self._project is None:
            return
        self._project.removeMapLayer(helper.id())

    def _find_basemap_definition(self, basemap_name: str) -> dict[str, str] | None:
        target = str(basemap_name or "").strip().casefold()
        if not target:
            target = self.BASEMAP_DEFAULT.casefold()
        for item in self.BASEMAPS:
            name = str(item.get("name", "")).strip()
            if name.casefold() == target:
                return item
            aliases = item.get("aliases", ())
            if any(str(alias).strip().casefold() == target for alias in aliases):
                return item
        return None

    def _find_existing_basemap_layer(self):
        layers = self._find_existing_basemap_layers()
        return layers[0] if layers else None

    def _find_existing_basemap_layers(self) -> list[Any]:
        if self._project is None:
            return []
        basemap_layers: list[Any] = []
        try:
            for layer in self._project.mapLayers().values():
                helper_kind = str(layer.customProperty(self.HELPER_KIND_PROPERTY, ""))
                if helper_kind == self.BASEMAP_KIND:
                    basemap_layers.append(layer)
        except Exception:
            return []
        return basemap_layers

    def _remove_layer_by_id(self, layer_id: str) -> None:
        if self._project is None:
            return
        try:
            self._project.removeMapLayer(layer_id)
        except Exception:
            return

    def _save_selected_basemap(self, basemap_name: str) -> None:
        if self._settings_manager is None:
            return
        try:
            self._settings_manager.set_json(self.BASEMAP_SETTINGS_KEY, basemap_name)
        except Exception as exc:
            self._logger.warning(f"Failed to persist selected basemap '{basemap_name}': {exc}")

    def _resolve_qgis_world_map_path(self) -> str:
        """Return the absolute path to the QGIS built-in world_map.gpkg, or empty string if not found."""
        try:
            from pathlib import Path
            from qgis.core import QgsApplication
            pkg = QgsApplication.pkgDataPath()
            if pkg:
                candidate = Path(pkg) / "resources" / "data" / "world_map.gpkg"
                if candidate.exists():
                    return str(candidate)
        except Exception:
            pass
        return ""

    def _apply_world_map_style(self, layer) -> None:
        """Apply a stable cartographic style so country borders remain clearly visible."""
        if layer is None:
            return
        if QgsFillSymbol is None:
            return
        geometry_type = getattr(layer, "geometryType", None)
        if not callable(geometry_type):
            return
        if QgsWkbTypes is None or geometry_type() != QgsWkbTypes.PolygonGeometry:
            return

        try:
            symbol = QgsFillSymbol.createSimple(
                {
                    "color": "#E7E3D6",
                    "outline_color": "#9C9C95",
                    "outline_width": "0.45",
                    "outline_style": "solid",
                }
            )
            renderer = getattr(layer, "renderer", lambda: None)()
            if renderer is not None and hasattr(renderer, "setSymbol"):
                renderer.setSymbol(symbol)
            if hasattr(layer, "triggerRepaint"):
                layer.triggerRepaint()
        except Exception as exc:
            self._logger.warning(f"Failed to apply World Map style: {exc}")

    def _resolve_muac_extent_for_canvas(self, canvas):
        if QgsRectangle is None:
            return None
        extent = QgsRectangle(*self.MUAC_EXTENT_WGS84)

        if (
            QgsCoordinateReferenceSystem is None
            or QgsCoordinateTransform is None
            or self._project is None
        ):
            return extent

        try:
            map_settings = canvas.mapSettings() if hasattr(canvas, "mapSettings") else None
            destination_crs = (
                map_settings.destinationCrs()
                if map_settings is not None and hasattr(map_settings, "destinationCrs")
                else None
            )
            if destination_crs is None or not hasattr(destination_crs, "isValid"):
                return extent
            if not destination_crs.isValid() or str(destination_crs.authid()) == "EPSG:4326":
                return extent

            source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            transform = QgsCoordinateTransform(source_crs, destination_crs, self._project)
            return transform.transformBoundingBox(extent)
        except Exception:
            return extent

    def _build_vertex_features(self, source_layer) -> list[Any]:
        if QgsFeature is None or QgsGeometry is None:
            return []
        features: list[Any] = []
        try:
            for src_feat in source_layer.getFeatures():
                geom = src_feat.geometry()
                if geom is None or geom.isEmpty():
                    continue
                for point in geom.vertices():
                    vertex_feat = QgsFeature()
                    vertex_feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point.x(), point.y())))
                    features.append(vertex_feat)
        except Exception as exc:
            self._logger.warning(f"Failed to build polygon vertices helper: {exc}")
            return []
        return features

    def _build_connection_features(
        self,
        source_layer,
        group_field: str = "",
        order_field: str = "",
    ) -> list[Any]:
        if QgsFeature is None or QgsGeometry is None:
            return []

        grouped_points: dict[str, list[tuple[Any, Any]]] = defaultdict(list)
        try:
            for feat in source_layer.getFeatures():
                geometry = feat.geometry()
                if geometry is None or geometry.isEmpty():
                    continue

                if geometry.isMultipart():
                    points = geometry.asMultiPoint()
                else:
                    points = [geometry.asPoint()]

                for point in points:
                    group_key = self._resolve_group_key(feat, group_field)
                    order_key = self._resolve_order_key(feat, order_field)
                    grouped_points[group_key].append((order_key, QgsPointXY(point.x(), point.y())))

            output: list[Any] = []
            for group_key, ordered_points in grouped_points.items():
                sorted_points = [p for _, p in sorted(ordered_points, key=lambda item: item[0])]
                if len(sorted_points) < 2:
                    continue
                line_feat = QgsFeature()
                line_feat.setGeometry(QgsGeometry.fromPolylineXY(sorted_points))
                line_feat.setAttributes([group_key])
                output.append(line_feat)

            return output
        except Exception as exc:
            self._logger.warning(f"Failed to build point connection helper: {exc}")
            return []

    def _resolve_layer_field_name(self, layer, wanted_field: str) -> str:
        if not wanted_field or layer is None or not hasattr(layer, "fields"):
            return ""
        try:
            names = [str(name) for name in layer.fields().names()]
        except Exception:
            return ""
        if wanted_field in names:
            return wanted_field

        wanted_key = str(wanted_field).casefold()
        for name in names:
            if name.casefold() == wanted_key:
                return name
        return ""

    @staticmethod
    def _extract_flight_level_ranges(features, lower_field: str, upper_field: str) -> list[tuple[int, int]]:
        ranges: set[tuple[int, int]] = set()
        for feature in features:
            try:
                raw_lower = feature[lower_field]
                raw_upper = feature[upper_field]
            except Exception:
                continue

            lower = LayerToolboxService._normalize_flight_level_value(raw_lower)
            upper = LayerToolboxService._normalize_flight_level_value(raw_upper)
            if lower is None or upper is None:
                continue
            if lower > upper:
                lower, upper = upper, lower
            ranges.add((lower, upper))
        return sorted(ranges, key=lambda item: (item[0], item[1]))

    @staticmethod
    def _normalize_flight_level_value(raw_value) -> int | None:
        if raw_value is None:
            return None
        try:
            return int(float(raw_value))
        except Exception:
            text = str(raw_value).strip().upper()
            if text.startswith("FL"):
                text = text[2:].strip()
            try:
                return int(float(text))
            except Exception:
                return None

    @staticmethod
    def _build_fl_range_expression(
        lower_field: str,
        upper_field: str,
        lower_value: int,
        upper_value: int,
    ) -> str:
        escaped_lower = str(lower_field).replace('"', '""')
        escaped_upper = str(upper_field).replace('"', '""')
        return f'"{escaped_lower}" = {int(lower_value)} AND "{escaped_upper}" = {int(upper_value)}'

    @staticmethod
    def _format_fl_range_label(lower_value: int, upper_value: int) -> str:
        return f"{int(lower_value)} - {int(upper_value)}"

    @staticmethod
    def _resolve_group_key(feature, group_field: str) -> str:
        if not group_field:
            return "__all__"
        try:
            raw = feature[group_field]
            if raw is None:
                return "__null__"
            value = str(raw).strip()
            return value or "__empty__"
        except Exception:
            return "__all__"

    @staticmethod
    def _resolve_order_key(feature, order_field: str) -> tuple[int, float, str, int]:
        fallback_fid = int(getattr(feature, "id", lambda: 0)())
        if not order_field:
            return (2, 0.0, "", fallback_fid)

        try:
            raw = feature[order_field]
        except Exception:
            return (2, 0.0, "", fallback_fid)

        if raw is None:
            return (2, 0.0, "", fallback_fid)

        # Numeric values are sorted numerically, otherwise lexically.
        try:
            numeric_value = float(raw)
            return (0, numeric_value, "", fallback_fid)
        except Exception:
            text_value = str(raw).strip().casefold()
            return (1, 0.0, text_value, fallback_fid)

    def _ensure_connection_fields(self, helper_layer) -> None:
        if QgsField is None or QVariant is None:
            return
        try:
            helper_layer.dataProvider().addAttributes([QgsField("group_key", QVariant.String)])
            helper_layer.updateFields()
        except Exception as exc:
            self._logger.warning(f"Failed to add helper connection fields: {exc}")

    def _apply_group_color_renderer(self, helper_layer, line_width: float) -> None:
        if (
            QgsCategorizedSymbolRenderer is None
            or QgsRendererCategory is None
            or QgsSymbol is None
            or QColor is None
        ):
            return

        idx = helper_layer.fields().indexFromName("group_key")
        if idx < 0:
            return

        categories: list[Any] = []
        seen_values: set[str] = set()
        try:
            for feature in helper_layer.getFeatures():
                raw = feature["group_key"]
                value = str(raw or "").strip() or "__all__"
                if value in seen_values:
                    continue
                seen_values.add(value)
                symbol = QgsSymbol.defaultSymbol(helper_layer.geometryType())
                if symbol is None:
                    continue
                color = self._color_for_group_key(value)
                symbol.setColor(color)
                symbol.setWidth(line_width)
                categories.append(QgsRendererCategory(value, symbol, value))

            if not categories:
                return

            renderer = QgsCategorizedSymbolRenderer("group_key", categories)
            helper_layer.setRenderer(renderer)
            helper_layer.triggerRepaint()
        except Exception as exc:
            self._logger.warning(f"Failed to apply grouped connection style: {exc}")

    def _apply_single_color_renderer(self, helper_layer, line_width: float) -> None:
        if QgsSymbol is None:
            return
        try:
            symbol = QgsSymbol.defaultSymbol(helper_layer.geometryType())
            if symbol is None:
                return
            symbol.setWidth(line_width)
            helper_layer.renderer().setSymbol(symbol)
            helper_layer.triggerRepaint()
        except Exception as exc:
            self._logger.warning(f"Failed to apply single-color line style: {exc}")

    @staticmethod
    def _color_for_group_key(group_key: str):
        """Create a stable vivid color for each group key."""
        if QColor is None:
            return None
        seed = abs(hash(group_key))
        hue = seed % 360
        return QColor.fromHsv(hue, 180, 220)

    @staticmethod
    def _normalize_line_width(raw_width: float) -> float:
        try:
            width = float(raw_width)
        except Exception:
            return 1.5
        return max(0.1, min(10.0, width))