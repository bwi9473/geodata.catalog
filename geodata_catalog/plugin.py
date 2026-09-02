from __future__ import annotations

from geodata_catalog.exceptions import GeoDataCatalogException
from geodata_catalog.logging_utils import PluginLogger
from geodata_catalog.metadata.datasource_repository import DatasourceRepository
from geodata_catalog.metadata.layer_config_repository import LayerConfigRepository
from geodata_catalog.metadata.layer_repository import LayerRepository
from geodata_catalog.metadata.settings_manager import SettingsManager
from geodata_catalog.metadata.system_configuration_repository import (
    DEFAULT_FLIGHT_LEVEL_PRESETS,
    DEFAULT_UI_COLORS,
    SystemConfigurationRepository,
)
from geodata_catalog.models.datasource import Datasource, DatasourceType
from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.services.datasource_service import DatasourceService
from geodata_catalog.services.layer_filter_service import (
    FlightLevelFilter,
    LayerFilter,
    LayerFilterService,
)
from geodata_catalog.services.layer_service import LayerService
from geodata_catalog.services.layer_toolbox_service import LayerToolboxService
from geodata_catalog.services.qgis_loader_service import QgisLoaderService
from geodata_catalog.services.style_service import StyleService
from geodata_catalog.ui.catalog_dockwidget import CatalogDockWidget
from geodata_catalog.ui.datasource_dialog import DatasourceDialog
from geodata_catalog.ui.geometry_toolbar import GeometryToolbar
from geodata_catalog.ui.layer_config_dialog import LayerConfigDialog
from geodata_catalog.ui.layer_custom_view_dock import LayerCustomViewDock
from geodata_catalog.ui.loadable_layers_dock import LoadableLayersDockWidget

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction, QApplication, QMenu, QMessageBox

try:
    from qgis.core import QgsMapLayerType
except ImportError:  # pragma: no cover
    QgsMapLayerType = None

try:
    from qgis.gui import QgsLayerTreeViewContextMenuProvider
except ImportError:  # pragma: no cover
    QgsLayerTreeViewContextMenuProvider = None


class GeoDataCatalogPlugin:
    """QGIS plugin implementation for metadata-driven geospatial catalog loading."""

    def __init__(self, iface) -> None:
        self.iface = iface
        self._logger = PluginLogger()

        settings_manager = SettingsManager()
        self._settings_manager = settings_manager
        self._system_configuration_repository = SystemConfigurationRepository(settings_manager)
        datasource_repository = DatasourceRepository(settings_manager)
        layer_repository = LayerRepository(settings_manager)

        # Per-layer display/search config stored in a separate layer_config.json
        layer_config_path = settings_manager.sibling_file_path("layer_config.json")
        self._layer_config_repository = LayerConfigRepository(layer_config_path)

        self._datasource_service = DatasourceService(datasource_repository, self._logger)
        self._layer_service = LayerService(
            self._datasource_service,
            layer_repository,
            self._logger,
            layer_config_repository=self._layer_config_repository,
        )
        self._style_service = StyleService(self._logger)
        self._loader_service = QgisLoaderService(self._style_service, self._logger)
        self._layer_toolbox_service = LayerToolboxService(
            self._logger,
            settings_manager=self._settings_manager,
        )

        self._open_catalog_action: QAction | None = None
        self._dock_widget: CatalogDockWidget | None = None
        self._loadable_layers_dock: LoadableLayersDockWidget | None = None
        self._layer_cache: dict[str, dict[str, LayerDefinition]] = {}
        self._loaded_layer_keys: set[str] = set()
        self._custom_view_docks: list[LayerCustomViewDock] = []
        self._layer_panel_filter_action: QAction | None = None
        self._geometry_toolbar = GeometryToolbar(
            self.iface,
            self._logger,
            on_loadable_layers_requested=self._show_loadable_layers_dock,
            on_focus_muac_requested=self._on_focus_muac_requested,
        )

    def initGui(self) -> None:
        try:
            self._open_catalog_action = QAction("Open GeoData Explorer", self.iface.mainWindow())
            self._open_catalog_action.triggered.connect(self._show_dock)
            self.iface.addPluginToMenu("GeoData Catalog/GeoData Catalog", self._open_catalog_action)

            self._geometry_toolbar.initGui()
            self._show_dock()
            self._logger.info("GeoData Catalog initialized")
        except Exception as exc:
            self._logger.error(f"initGui failed: {exc}")
            raise

    def unload(self) -> None:
        self._geometry_toolbar.unload()

        if self._dock_widget is not None:
            self.iface.removeDockWidget(self._dock_widget)
            self._dock_widget.deleteLater()
            self._dock_widget = None

        if self._loadable_layers_dock is not None:
            self.iface.removeDockWidget(self._loadable_layers_dock)
            self._loadable_layers_dock.deleteLater()
            self._loadable_layers_dock = None

        if self._open_catalog_action is not None:
            self.iface.removePluginMenu("GeoData Catalog/GeoData Catalog", self._open_catalog_action)
            self._open_catalog_action = None

        self._logger.info("GeoData Catalog unloaded")

    def _show_dock(self) -> None:
        if self._dock_widget is None:
            self._dock_widget = CatalogDockWidget(self.iface.mainWindow())
            self._dock_widget.add_source_requested.connect(self._on_add_source)
            self._dock_widget.edit_source_requested.connect(self._on_edit_source)
            self._dock_widget.delete_source_requested.connect(self._on_delete_source)
            self._dock_widget.refresh_requested.connect(self._on_refresh_source)
            self._dock_widget.edit_layer_config_requested.connect(self._on_edit_layer_config)
            self.iface.addDockWidget(self._dock_area(), self._dock_widget)
            self._try_tabify_with_core_docks(self._dock_widget)
        self._dock_widget.show()
        self._refresh_datasources()
        self._ensure_layer_panel_filter_action()

    def _show_loadable_layers_dock(self) -> None:
        if self._loadable_layers_dock is None:
            self._loadable_layers_dock = LoadableLayersDockWidget(self.iface.mainWindow())
            self._loadable_layers_dock.load_layer_requested.connect(self._on_load_layer)
            self._loadable_layers_dock.basemap_selected.connect(self._on_basemap_selected)
            self._configure_as_floating_window(self._loadable_layers_dock)
        self._apply_configured_theme(self._loadable_layers_dock)
        self._size_data_panel_window(self._loadable_layers_dock)
        self._loadable_layers_dock.show()
        self._loadable_layers_dock.raise_()
        self._loadable_layers_dock.activateWindow()
        self._center_on_map_canvas(self._loadable_layers_dock)
        self._loadable_layers_dock.set_basemap_options(
            self._layer_toolbox_service.list_basemap_options(),
            self._layer_toolbox_service.current_basemap_name(),
        )
        self._refresh_all_layers_view()

    def _configure_as_floating_window(self, dock_widget) -> None:
        if hasattr(dock_widget, "setFloating"):
            dock_widget.setFloating(True)

        no_dock_area = getattr(Qt, "NoDockWidgetArea", None)
        if no_dock_area is None:
            dock_widget_area = getattr(Qt, "DockWidgetArea", None)
            if dock_widget_area is not None:
                no_dock_area = getattr(dock_widget_area, "NoDockWidgetArea", None)
        if no_dock_area is not None and hasattr(dock_widget, "setAllowedAreas"):
            dock_widget.setAllowedAreas(no_dock_area)

    def _size_data_panel_window(self, widget) -> None:
        if not hasattr(widget, "resize"):
            return
        available_geometry = self._available_screen_geometry(widget)
        target_geometry = self._data_panel_target_geometry()
        target_width = target_geometry.width() if target_geometry is not None else available_geometry.width()
        target_height = target_geometry.height() if target_geometry is not None else available_geometry.height()

        width = max(460, min(640, int(target_width * 0.34)))
        height = max(620, min(820, int(target_height * 0.82)))
        width = min(width, max(320, available_geometry.width() - 48))
        height = min(height, max(420, available_geometry.height() - 48))

        if hasattr(widget, "setMinimumSize"):
            widget.setMinimumSize(380, 520)
        widget.resize(width, height)

    def _center_on_map_canvas(self, widget) -> None:
        if not hasattr(widget, "move"):
            return
        target_geometry = self._data_panel_target_geometry()
        if target_geometry is None:
            target_geometry = self.iface.mainWindow().frameGeometry()
        available_geometry = self._available_screen_geometry(widget)
        try:
            widget_geometry = widget.frameGeometry()
            target_center = target_geometry.center()
            margin = 12
            x = target_center.x() - widget_geometry.width() // 2
            y = target_center.y() - widget_geometry.height() // 2
            x = max(available_geometry.left() + margin, min(x, available_geometry.right() - widget_geometry.width() - margin))
            y = max(available_geometry.top() + margin, min(y, available_geometry.bottom() - widget_geometry.height() - margin))
            widget.move(x, y)
        except Exception as exc:
            self._logger.warning(f"Failed to center Data Panel window: {exc}")

    def _data_panel_target_geometry(self):
        canvas = self.iface.mapCanvas() if self.iface is not None and hasattr(self.iface, "mapCanvas") else None
        if canvas is not None and hasattr(canvas, "rect") and hasattr(canvas, "mapToGlobal"):
            try:
                rect = canvas.rect()
                top_left = canvas.mapToGlobal(rect.topLeft())
                rect.moveTopLeft(top_left)
                return rect
            except Exception:
                pass

        main_window = self.iface.mainWindow() if self.iface is not None else None
        if main_window is not None and hasattr(main_window, "frameGeometry"):
            return main_window.frameGeometry()
        return None

    def _available_screen_geometry(self, widget):
        screen = widget.screen() if hasattr(widget, "screen") else None
        if screen is None:
            main_window = self.iface.mainWindow() if self.iface is not None else None
            screen = main_window.screen() if main_window is not None and hasattr(main_window, "screen") else None
        if screen is None and QApplication is not None:
            screen = QApplication.primaryScreen()
        if screen is not None and hasattr(screen, "availableGeometry"):
            return screen.availableGeometry()
        main_window = self.iface.mainWindow() if self.iface is not None else None
        return main_window.frameGeometry()

    def _load_ui_colors(self) -> dict[str, str]:
        try:
            return self._system_configuration_repository.load_ui_colors()
        except Exception as exc:
            self._logger.error(f"Failed to load UI colors from system configuration: {exc}")
            return DEFAULT_UI_COLORS

    def _apply_configured_theme(self, widget) -> None:
        apply_theme = getattr(widget, "apply_theme", None)
        if callable(apply_theme):
            apply_theme(self._load_ui_colors())

    def _on_basemap_selected(self, basemap_name: str) -> None:
        if not basemap_name:
            return
        self._layer_toolbox_service.set_basemap(basemap_name)
        if self._loadable_layers_dock is not None:
            self._loadable_layers_dock.set_basemap_options(
                self._layer_toolbox_service.list_basemap_options(),
                self._layer_toolbox_service.current_basemap_name(),
            )

    def _on_focus_muac_requested(self) -> None:
        self._layer_toolbox_service.focus_muac_on_canvas(self.iface)

    def _ensure_layer_panel_filter_action(self) -> None:
        """Register quick search action and hook into layer panel context menu events."""
        if self._layer_panel_filter_action is not None:
            return

        layer_tree_view = getattr(self.iface, "layerTreeView", lambda: None)()
        if layer_tree_view is None:
            return

        self._layer_panel_filter_action = QAction("Quick Search", self.iface.mainWindow())
        self._layer_panel_filter_action.triggered.connect(self._on_open_layer_filter)

        if hasattr(layer_tree_view, "contextMenuAboutToShow"):
            try:
                layer_tree_view.contextMenuAboutToShow.connect(
                    self._on_layer_tree_context_menu_about_to_show
                )
                return
            except Exception as exc:
                self._logger.warning(f"Failed to connect context menu signal: {exc}")

        # Legacy fallback for older QGIS builds without contextMenuAboutToShow.
        if hasattr(layer_tree_view, "setContextMenuPolicy"):
            context_policy = getattr(Qt, "CustomContextMenu", None)
            if context_policy is None:
                context_policy = Qt.ContextMenuPolicy.CustomContextMenu
            layer_tree_view.setContextMenuPolicy(context_policy)
            layer_tree_view.customContextMenuRequested.connect(self._on_layer_tree_context_menu)

    def _on_layer_tree_context_menu_about_to_show(self, menu) -> None:
        if menu is None:
            return

        layer = self._active_layer()
        if layer is not None:
            geo_menu = self._build_geodata_context_menu(layer)
            if geo_menu is not None:
                menu.addSeparator()
                menu.addMenu(geo_menu)

    def _on_layer_tree_context_menu(self, pos) -> None:
        layer_tree_view = getattr(self.iface, "layerTreeView", lambda: None)()
        if layer_tree_view is None:
            return

        create_menu = getattr(layer_tree_view, "createContextMenu", None)
        if callable(create_menu):
            menu = create_menu()
            if menu is None:
                return
            layer = self._active_layer()
            if layer is not None:
                geo_menu = self._build_geodata_context_menu(layer)
                if geo_menu is not None:
                    menu.addSeparator()
                    menu.addMenu(geo_menu)
            menu.exec(layer_tree_view.viewport().mapToGlobal(pos))
            return

        # Final fallback: build a minimal menu only when the QGIS API cannot supply one.
        menu = QMenu(layer_tree_view)
        layer = self._active_layer()
        if layer is not None:
            geo_menu = self._build_geodata_context_menu(layer)
            if geo_menu is not None:
                menu.addMenu(geo_menu)
        menu.exec(layer_tree_view.viewport().mapToGlobal(pos))

    def _build_geodata_context_menu(self, layer):
        if layer is None:
            return None

        geo_menu = QMenu("GeoData", self.iface.mainWindow() if self.iface is not None else None)
        layer_def = self._find_layer_definition_for_qgis_layer(layer)

        quick_search_action = getattr(self, "_layer_panel_filter_action", None)
        if quick_search_action is not None:
            geo_menu.addAction(quick_search_action)

        if self._supports_vertices_actions(layer):
            if not geo_menu.isEmpty():
                geo_menu.addSeparator()

            show_vertices_action = QAction("Show Vertices", geo_menu)
            show_vertices_action.triggered.connect(
                lambda _checked=False: self._layer_toolbox_service.set_vertices_visible(layer, True)
            )
            geo_menu.addAction(show_vertices_action)

            hide_vertices_action = QAction("Hide Vertices", geo_menu)
            hide_vertices_action.triggered.connect(
                lambda _checked=False: self._layer_toolbox_service.set_vertices_visible(layer, False)
            )
            geo_menu.addAction(hide_vertices_action)

        group_menu = QMenu("Group By", geo_menu)
        group_fields = []
        if layer_def is not None and getattr(layer_def, "searchable_columns", None):
            group_fields = [
                str(column.get("name", "")).strip()
                for column in layer_def.searchable_columns
                if str(column.get("name", "")).strip()
            ]

        flight_level_grouping_enabled = bool(
            layer_def is not None
            and layer_def.metadata.get("enable_fl_filter", True)
        )

        if group_fields or flight_level_grouping_enabled:
            for field_name in group_fields:
                action = QAction(field_name, group_menu)
                action.triggered.connect(
                    lambda _checked=False, field_name=field_name: self._layer_toolbox_service.apply_value_grouping_rules(
                        layer, field_name
                    )
                )
                group_menu.addAction(action)
            if flight_level_grouping_enabled:
                flight_level_action = QAction("Flight Level Band", group_menu)
                flight_level_action.triggered.connect(
                    lambda _checked=False: self._layer_toolbox_service.apply_flight_level_range_rules(layer)
                )
                group_menu.addAction(flight_level_action)
                preset_grouping_action = QAction("Flight Level Presets", group_menu)
                preset_grouping_action.triggered.connect(
                    lambda _checked=False: self._apply_flight_level_preset_grouping(layer)
                )
                group_menu.addAction(preset_grouping_action)
        else:
            placeholder = QAction("(no configured fields)", group_menu)
            placeholder.setEnabled(False)
            group_menu.addAction(placeholder)

        geo_menu.addMenu(group_menu)
        return geo_menu

    def _apply_flight_level_preset_grouping(self, layer) -> bool:
        try:
            presets = self._system_configuration_repository.load_flight_level_presets()
        except Exception as exc:
            self._logger.warning(f"Unable to load flight-level presets for grouping: {exc}")
            presets = DEFAULT_FLIGHT_LEVEL_PRESETS
        return self._layer_toolbox_service.apply_flight_level_preset_rules(layer, presets)

    def _supports_vertices_actions(self, layer) -> bool:
        if layer is None or self._layer_toolbox_service is None:
            return False

        try:
            if hasattr(layer, "wkbType"):
                geometry_type = layer.wkbType()
                if hasattr(self._layer_toolbox_service, "_is_vertex_source_layer"):
                    return self._layer_toolbox_service._is_vertex_source_layer(layer)
                return True
            return False
        except Exception:
            return False

    def _dock_area(self):
        # Compatibility helper for QGIS 3.x (PyQt5) and QGIS 4.x (PyQt6).
        dock_area = getattr(Qt, "LeftDockWidgetArea", None)
        if dock_area is not None:
            return dock_area
        return Qt.DockWidgetArea.LeftDockWidgetArea

    def _refresh_datasources(self) -> None:
        if self._dock_widget is None:
            return
        datasources = self._datasource_service.list_datasources()
        self._dock_widget.set_datasources(datasources)
        if self._loadable_layers_dock is not None:
            self._refresh_all_layers_view()

    def _on_add_source(self) -> None:
        dialog = DatasourceDialog(self.iface.mainWindow())
        if self._run_dialog(dialog) != self._accepted_code(dialog):
            return
        try:
            name, datasource_type, config = dialog.get_payload()
            self._datasource_service.create_datasource(name, datasource_type, config)
            self._refresh_datasources()
        except GeoDataCatalogException as exc:
            self._show_error("Add Datasource", str(exc))

    def _on_edit_source(self, datasource_id: str) -> None:
        datasource = self._datasource_service.get_datasource(datasource_id)
        dialog = DatasourceDialog(self.iface.mainWindow(), datasource=datasource)
        if self._run_dialog(dialog) != self._accepted_code(dialog):
            return
        try:
            name, datasource_type, config = dialog.get_payload()
            datasource.name = name
            datasource.datasource_type = datasource_type
            datasource.config = config
            self._datasource_service.update_datasource(datasource)
            self._refresh_datasources()
        except GeoDataCatalogException as exc:
            self._show_error("Edit Datasource", str(exc))

    def _on_delete_source(self, datasource_id: str) -> None:
        yes_button = self._messagebox_yes_button()
        no_button = self._messagebox_no_button()
        answer = QMessageBox.question(
            self.iface.mainWindow(),
            "Delete Datasource",
            "Delete selected datasource?",
            yes_button | no_button,
            no_button,
        )
        if answer != yes_button:
            return
        try:
            self._datasource_service.delete_datasource(datasource_id)
            self._layer_config_repository.delete_by_datasource(datasource_id)
            self._layer_cache.pop(datasource_id, None)
            self._refresh_datasources()
            if self._dock_widget is not None:
                self._dock_widget.layers_list.clear()
        except GeoDataCatalogException as exc:
            self._show_error("Delete Datasource", str(exc))

    def _on_refresh_source(self, datasource_id: str) -> None:
        if self._dock_widget is None:
            return
        if self._dock_widget.is_show_all_layers_enabled():
            self._refresh_all_layers_view()
            return
        try:
            datasource = self._datasource_service.get_datasource(datasource_id)
            layers = self._layer_service.discover_layers(datasource)
            self._layer_cache[datasource_id] = {layer.layer_name: layer for layer in layers}
            self._dock_widget.set_layers(datasource_id, layers)
        except GeoDataCatalogException as exc:
            datasource = self._datasource_service.get_datasource(datasource_id)
            fallback_layers = self._fallback_layers_for_unavailable_datasource(datasource)
            if fallback_layers:
                self._layer_cache[datasource_id] = {
                    layer.layer_name: layer for layer in fallback_layers
                }
                self._dock_widget.set_layers(datasource_id, fallback_layers)
                self._logger.warning(
                    "Datasource unavailable; showing fallback layers for "
                    f"'{datasource.name}': {exc}"
                )
                return
            self._show_error("Refresh Datasource", str(exc))

    def _on_show_all_layers_toggled(self, enabled: bool) -> None:
        if not enabled:
            if self._dock_widget is not None:
                self._dock_widget.layers_list.clear()
                selected_id = self._dock_widget.selected_datasource_id()
                if selected_id:
                    self._on_refresh_source(selected_id)
            return
        self._refresh_all_layers_view()

    def _refresh_all_layers_view(self) -> None:
        """Build a combined list of loadable layers from all datasources."""
        if self._loadable_layers_dock is None:
            return
        rows: list[dict[str, str | LayerDefinition]] = []
        try:
            datasources = self._datasource_service.list_datasources()
            for datasource in datasources:
                unavailable = False
                try:
                    layers = self._layer_service.discover_layers(datasource)
                except GeoDataCatalogException as exc:
                    layers = self._fallback_layers_for_unavailable_datasource(datasource)
                    unavailable = bool(layers)
                    if unavailable:
                        self._logger.warning(
                            "Datasource unavailable during all-layers refresh; using fallback layers for "
                            f"'{datasource.name}': {exc}"
                        )
                    else:
                        self._logger.warning(
                            f"Datasource '{datasource.name}' unavailable and no fallback layers exist: {exc}"
                        )

                self._layer_cache[datasource.id] = {layer.layer_name: layer for layer in layers}
                for layer in layers:
                    business_group = (
                        "Database not available"
                        if unavailable and datasource.datasource_type is DatasourceType.ORACLE
                        else layer.business_group
                    )
                    rows.append(
                        {
                            "datasource_id": datasource.id,
                            "source_name": datasource.name,
                            "source_type": datasource.datasource_type.value,
                            "layer": layer,
                            "loadable": not unavailable,
                            "business_group": business_group,
                            "availability_reason": "Database not available" if unavailable else "",
                        }
                    )
            rows.sort(
                key=lambda r: (
                    str(r.get("availability_reason", "")).casefold(),
                    str(r.get("source_name", "")).casefold(),
                    str((r.get("layer") or LayerDefinition("", "", "", "", "")).display_name).casefold(),
                )
            )
            self._loadable_layers_dock.set_rows(rows, self._loaded_layer_keys, "#2777B5")
            self._logger.info(f"All-layers view refreshed with {len(rows)} loadable layers")
        except GeoDataCatalogException as exc:
            self._show_error("Refresh All Layers", str(exc))

    def _on_load_layer(self, datasource_id: str, layer_name: str) -> None:
        try:
            if self._is_layer_marked_unavailable(datasource_id, layer_name):
                self._show_error("Load Layer", "Database not available for this layer.")
                return
            datasource = self._datasource_service.get_datasource(datasource_id)
            connector = self._datasource_service.get_connector(datasource)
            layer_definition = self._resolve_layer(datasource_id, layer_name)
            self._loader_service.load_layer(layer_definition, connector)
            self._layer_toolbox_service.ensure_default_basemap_for_empty_project()
            self._loaded_layer_keys.add(layer_definition.key())
            if self._loadable_layers_dock is not None:
                self._loadable_layers_dock.refresh_loaded_state(self._loaded_layer_keys)
        except GeoDataCatalogException as exc:
            self._show_error("Load Layer", str(exc))

    def _on_edit_layer_config(self, datasource_id: str, layer_name: str) -> None:
        """Open the per-layer config dialog and persist the result."""
        layer_def = self._resolve_layer(datasource_id, layer_name)
        datasource = self._datasource_service.get_datasource(datasource_id)
        existing_config = self._layer_config_repository.get(datasource_id, layer_name)

        dialog = LayerConfigDialog(
            self.iface.mainWindow(),
            datasource_id=datasource_id,
            layer_name=layer_name,
            display_name=layer_def.display_name,
            source_name=self._layer_config_source_label(datasource, layer_def),
            existing_config=existing_config,
            available_fields=self._discover_layer_fields(datasource_id, layer_name),
            refresh_fields=lambda: self._discover_layer_fields(datasource_id, layer_name),
        )
        if self._run_dialog(dialog) != self._accepted_code(dialog):
            return

        config = dialog.get_config()
        self._layer_config_repository.save(config)
        # Invalidate cache so next Refresh picks up the new config
        self._layer_cache.pop(datasource_id, None)
        self._logger.info(
            f"Layer config saved for '{layer_def.display_name}': "
            f"label_column={config.label_column}, "
            f"enable_fl_filter={config.enable_fl_filter}, "
            f"searchable_columns={config.searchable_columns}"
        )

    @staticmethod
    def _layer_config_source_label(datasource: Datasource, layer_def: LayerDefinition) -> str:
        if datasource.datasource_type in {DatasourceType.GEOJSON, DatasourceType.KML}:
            return str(
                layer_def.metadata.get("path")
                or datasource.config.get("path")
                or layer_def.layer_name
            )
        if datasource.datasource_type is DatasourceType.REST:
            return str(datasource.config.get("url") or layer_def.provider_uri or layer_def.layer_name)
        return layer_def.layer_name

    def _discover_layer_fields(self, datasource_id: str, layer_name: str) -> list[dict[str, str]]:
        """Read the field schema from a connector without adding the layer to the project."""
        try:
            datasource = self._datasource_service.get_datasource(datasource_id)
            connector = self._datasource_service.get_connector(datasource)
            get_layer_fields = getattr(connector, "get_layer_fields", None)
            if callable(get_layer_fields):
                return get_layer_fields(layer_name)
            layer = connector.load_layer(layer_name)
            fields = layer.fields()
            result: list[dict[str, str]] = []
            for position, field in enumerate(fields):
                type_name = str(field.typeName() if hasattr(field, "typeName") else "varchar")
                data_type = "numeric" if type_name.casefold() in {
                    "int", "integer", "long", "double", "real", "numeric", "decimal", "float"
                } else "varchar"
                result.append({
                    "name": str(field.name()),
                    "label": str(field.name()),
                    "type": data_type,
                    "position": position,
                })
            return result
        except Exception as exc:
            self._logger.warning(f"Failed to read fields for layer '{layer_name}': {exc}")
            return []

    def _on_open_layer_filter(self) -> None:
        layer = self._active_layer()
        if layer is None:
            self._show_error("Quick Search", "No active QGIS layer is selected.")
            return
        layer_def = self._find_layer_definition_for_qgis_layer(layer)
        self._open_unified_filter_custom_view(layer, layer_def)

    def _open_custom_view_for_layer_definition(self, qgis_layer, layer_def: LayerDefinition) -> None:
        self._open_unified_filter_custom_view(qgis_layer, layer_def)

    def _open_unified_filter_custom_view(self, layer, layer_def: LayerDefinition | None) -> None:
        # If a window is already open for this layer, bring it to focus instead of opening a second one.
        # Use layer.id() for comparison because QGIS may return different Python wrapper objects
        # for the same underlying layer, making identity checks ('is') unreliable.
        try:
            incoming_layer_id = layer.id() if layer is not None and hasattr(layer, "id") else None
        except Exception:
            incoming_layer_id = None

        if incoming_layer_id is not None:
            for existing_window in list(self._custom_view_docks):
                try:
                    existing_id = existing_window._layer.id() if existing_window._layer is not None and hasattr(existing_window._layer, "id") else None
                except Exception:
                    existing_id = None
                if existing_id is not None and existing_id == incoming_layer_id:
                    existing_window.raise_()
                    existing_window.activateWindow()
                    return

        existing_subset = layer.subsetString() or ""
        current_fl = LayerFilterService.parse_fl_from_subset_string(existing_subset)

        searchable_columns = layer_def.searchable_columns if layer_def else None
        show_flight_level = True
        if layer_def is not None:
            show_flight_level = bool(layer_def.metadata.get("enable_fl_filter", True))

        current_attrs = []
        if searchable_columns:
            current_attrs = LayerFilterService.parse_attribute_filters_from_subset(
                existing_subset, searchable_columns
            )

        fl_filter = current_fl or FlightLevelFilter(
            mode=LayerFilterService.MODE_NONE,
            lower=0,
            upper=600,
            enabled=False,
        )
        if not show_flight_level:
            fl_filter = FlightLevelFilter(
                mode=LayerFilterService.MODE_NONE,
                lower=0,
                upper=600,
                enabled=False,
                lower_field="fl_lower",
                upper_field="fl_upper",
            )
        fl_filter = self._normalize_flight_level_fields(layer, fl_filter)

        initial_filter = LayerFilter(
            flight_level=fl_filter,
            attributes=current_attrs,
        )

        flight_level_presets = DEFAULT_FLIGHT_LEVEL_PRESETS
        try:
            flight_level_presets = self._system_configuration_repository.load_flight_level_presets()
        except Exception as exc:
            self._logger.error(f"Failed to load flight level presets from system configuration: {exc}")

        ui_colors = self._load_ui_colors()

        distinct_values: dict[str, list[str]] = {}
        filtered_distinct_values: dict[str, dict[str, list[str]]] = {}
        if searchable_columns:
            distinct_values, filtered_distinct_values = self._collect_distinct_values(layer, searchable_columns)

        display_name = layer_def.display_name if layer_def else layer.name()
        view_columns = self._resolve_view_columns(layer, layer_def)
        records = self._collect_layer_records(layer, view_columns)

        window = LayerCustomViewDock(
            self.iface.mainWindow(),
            layer=layer,
            map_canvas=self.iface.mapCanvas(),
            layer_name=display_name,
            columns=view_columns,
            records=records,
            logger=self._logger,
            initial_filter=initial_filter,
            searchable_columns=searchable_columns,
            distinct_values=distinct_values,
            filtered_distinct_values=filtered_distinct_values,
            show_flight_level=show_flight_level,
            flight_level_presets=flight_level_presets,
            on_filter_applied=lambda f: self._apply_layer_filter(layer, f),
            ui_colors=ui_colors,
        )
        window.destroyed.connect(lambda *_: self._on_custom_view_window_closed(window))
        window.show()
        self._custom_view_docks.append(window)

    def _resolve_view_columns(self, qgis_layer, layer_def: LayerDefinition | None) -> list[dict[str, str]]:
        if layer_def is not None:
            if "view_columns" in layer_def.metadata:
                configured = layer_def.metadata["view_columns"] or []
                return [c for c in configured if c.get("name")]

        if not hasattr(qgis_layer, "fields"):
            return []
        try:
            names = qgis_layer.fields().names()
        except Exception:
            return []
        return [{"name": str(name), "label": str(name), "type": "varchar"} for name in names]

    def _on_custom_view_window_closed(self, window: LayerCustomViewDock) -> None:
        if window in self._custom_view_docks:
            self._custom_view_docks.remove(window)

    def _collect_layer_records(self, qgis_layer, columns: list[dict[str, str]]) -> list[dict[str, object]]:
        """Extract visible feature values for configured columns from a loaded QGIS layer."""
        col_names = [c.get("name", "") for c in columns if c.get("name", "")]
        layer_field_names = set(qgis_layer.fields().names()) if hasattr(qgis_layer, "fields") else set()
        records: list[dict[str, object]] = []
        try:
            for feat in qgis_layer.getFeatures():
                rec: dict[str, object] = {"__fid": int(feat.id()) if hasattr(feat, "id") else -1}
                for col_name in col_names:
                    rec[col_name] = feat[col_name] if col_name in layer_field_names else None
                records.append(rec)
        except Exception as exc:
            self._logger.error(f"Failed to collect records for custom view: {exc}")
            return []
        return records

    def _collect_distinct_values(
        self, qgis_layer, searchable_columns: list[dict[str, str | bool]] | None
    ) -> tuple[dict[str, list[str]], dict[str, dict[str, list[str]]]]:
        """Extract distinct values for columns marked with use_distinct=True.

        Also collects per-parent-value mappings for columns that specify a
        ``filter_by`` parent column.  Both collections are built in a single
        feature scan for efficiency.

        Returns
        -------
        distinct_values:
            Mapping of column name to sorted list of all distinct values.
        filtered_distinct_values:
            Nested mapping {child_col: {parent_val: [child_val, ...]}} used
            to cascade dropdown options in the Layer Filter dialog.
        """
        if not searchable_columns:
            return {}, {}

        layer_field_names = set(qgis_layer.fields().names()) if hasattr(qgis_layer, "fields") else set()

        # Build filter_by relationships from config
        filter_by_map: dict[str, str] = {}  # child_col -> parent_col
        for col_def in searchable_columns:
            col_name = col_def.get("name", "")
            filter_by = col_def.get("filter_by", "")
            if col_name and filter_by:
                filter_by_map[col_name] = str(filter_by)

        # Determine which columns need distinct value collection
        distinct_cols: set[str] = {
            col_def.get("name", "")
            for col_def in searchable_columns
            if col_def.get("name") and col_def.get("use_distinct") and col_def.get("name") in layer_field_names
        }
        distinct_cols.discard("")

        if not distinct_cols:
            return {}, {}

        try:
            value_sets: dict[str, set[str]] = {col: set() for col in distinct_cols}
            # {child_col: {parent_val: set(child_vals)}}
            filtered_sets: dict[str, dict[str, set[str]]] = {
                child: {}
                for child in filter_by_map
                if child in distinct_cols and filter_by_map[child] in layer_field_names
            }

            for feat in qgis_layer.getFeatures():
                for col in distinct_cols:
                    val = feat[col]
                    if val is not None:
                        value_sets[col].add(str(val).strip())

                for child_col, parent_col in filter_by_map.items():
                    if child_col not in distinct_cols or parent_col not in layer_field_names:
                        continue
                    parent_val = feat[parent_col]
                    child_val = feat[child_col]
                    if parent_val is not None and child_val is not None:
                        pv = str(parent_val).strip()
                        cv = str(child_val).strip()
                        if pv and cv:
                            if pv not in filtered_sets[child_col]:
                                filtered_sets[child_col][pv] = set()
                            filtered_sets[child_col][pv].add(cv)

            distinct_values: dict[str, list[str]] = {
                col: sorted(v for v in vals if v) for col, vals in value_sets.items()
            }
            filtered_distinct_values: dict[str, dict[str, list[str]]] = {
                child_col: {pv: sorted(cvs) for pv, cvs in parent_map.items()}
                for child_col, parent_map in filtered_sets.items()
            }

        except Exception as exc:
            self._logger.warning(f"Failed to collect distinct values: {exc}")
            return {}, {}

        return distinct_values, filtered_distinct_values


    def _apply_layer_filter(self, layer, layer_filter: LayerFilter) -> None:
        normalized_fl = self._normalize_flight_level_fields(layer, layer_filter.flight_level)
        fl_expression = LayerFilterService.build_fl_expression(normalized_fl)
        attr_expression = LayerFilterService.build_attribute_expression(layer_filter.attributes)

        existing_subset = layer.subsetString() or ""
        # Always strip all configured searchable columns first.
        # This ensures previously selected dropdown values are removed when
        # the user clears a selection and clicks Apply again.
        configured_attr_columns: list[str] = []
        layer_def = self._find_layer_definition_for_qgis_layer(layer)
        if layer_def and layer_def.searchable_columns:
            configured_attr_columns = [
                str(col.get("name", "")).strip()
                for col in layer_def.searchable_columns
                if str(col.get("name", "")).strip()
            ]
        active_attr_columns = [a.column for a in layer_filter.attributes if a.column]
        attr_columns = list(dict.fromkeys(configured_attr_columns + active_attr_columns))
        base_filter = LayerFilterService.strip_fl_from_subset_string(existing_subset)
        base_filter = LayerFilterService.strip_attribute_filters_from_subset(base_filter, attr_columns)

        parts: list[str] = []
        if base_filter.strip():
            parts.append(f"({base_filter})")
        if fl_expression:
            parts.append(f"({fl_expression})")
        if attr_expression:
            parts.append(f"({attr_expression})")

        combined = " AND ".join(parts)
        layer.setSubsetString(combined)
        if hasattr(layer, "triggerRepaint"):
            layer.triggerRepaint()
        iface = getattr(self, "iface", None)
        canvas = getattr(iface, "mapCanvas", lambda: None)() if iface is not None else None
        if canvas is not None and hasattr(canvas, "refresh"):
            canvas.refresh()
        self._logger.info(f"Applied layer filter to '{layer.name()}': {combined or '(none)'}")

    def _normalize_flight_level_fields(self, layer, flight_filter: FlightLevelFilter) -> FlightLevelFilter:
        """Resolve FL field names against layer fields in a case-insensitive way."""
        lower_field = self._resolve_layer_field_name(layer, flight_filter.lower_field)
        upper_field = self._resolve_layer_field_name(layer, flight_filter.upper_field)
        return FlightLevelFilter(
            mode=flight_filter.mode,
            lower=flight_filter.lower,
            upper=flight_filter.upper,
            enabled=flight_filter.enabled,
            lower_field=lower_field,
            upper_field=upper_field,
        )

    def _resolve_layer_field_name(self, layer, field_name: str) -> str:
        """Return the real layer field name when only case differs; otherwise keep input."""
        if not field_name:
            return field_name
        if not hasattr(layer, "fields"):
            return field_name
        try:
            names = layer.fields().names()
        except Exception:
            return field_name

        # Exact match first.
        if field_name in names:
            return field_name

        # Case-insensitive fallback for databases exposing uppercase column names.
        wanted = field_name.casefold()
        for name in names:
            if str(name).casefold() == wanted:
                return str(name)
        return field_name

    def _active_layer(self):
        if self.iface is None:
            return None
        return self.iface.activeLayer()

    def _find_layer_definition_for_qgis_layer(self, qgis_layer) -> LayerDefinition | None:
        """Find the cached LayerDefinition that matches a QGIS layer by display name."""
        display_name = qgis_layer.name()
        for layers_by_name in self._layer_cache.values():
            for layer_def in layers_by_name.values():
                if layer_def.display_name == display_name:
                    return layer_def
        return None

    def _resolve_layer(self, datasource_id: str, layer_name: str) -> LayerDefinition:
        by_source = self._layer_cache.get(datasource_id, {})
        layer = by_source.get(layer_name)
        if layer is None:
            datasource = self._datasource_service.get_datasource(datasource_id)
            layers = self._layer_service.discover_layers(datasource)
            by_source = {item.layer_name: item for item in layers}
            self._layer_cache[datasource_id] = by_source
            layer = by_source.get(layer_name)
        if layer is None:
            raise GeoDataCatalogException(f"Layer '{layer_name}' not found in current catalog.")
        return layer

    def _show_error(self, title: str, message: str) -> None:
        self._logger.error(f"{title}: {message}")
        QMessageBox.warning(
            self.iface.mainWindow(),
            title,
            message,
        )

    def _fallback_layers_for_unavailable_datasource(self, datasource) -> list[LayerDefinition]:
        configured_layers = self._layer_service.list_configured_layers(datasource.id)
        fallback: list[LayerDefinition] = []
        for layer in configured_layers:
            fallback_layer = LayerDefinition.from_dict(layer.to_dict())
            fallback_layer.business_group = "Database not available"
            fallback_layer.metadata["unavailable"] = True
            fallback_layer.metadata["unavailable_reason"] = "Database not available"
            fallback.append(fallback_layer)
        return fallback

    def _is_layer_marked_unavailable(self, datasource_id: str, layer_name: str) -> bool:
        by_source = self._layer_cache.get(datasource_id, {})
        layer = by_source.get(layer_name)
        if layer is None:
            return False
        return bool(layer.metadata.get("unavailable", False))

    def _try_tabify_with_core_docks(self, dock_widget) -> None:
        if dock_widget is None:
            return

        tabified = False
        for attr_name in ("browserDockWidget", "layerTreeDockWidget"):
            getter = getattr(self.iface, attr_name, None)
            candidate = getter() if callable(getter) else None
            if candidate is not None and hasattr(self.iface, "tabifyDockWidget"):
                self.iface.tabifyDockWidget(candidate, dock_widget)
                tabified = True

        if tabified and hasattr(dock_widget, "raise_"):
            dock_widget.raise_()

    @staticmethod
    def _run_dialog(dialog) -> int:
        exec_fn = getattr(dialog, "exec", None)
        if callable(exec_fn):
            return exec_fn()
        return dialog.exec_()

    @staticmethod
    def _accepted_code(dialog) -> int:
        accepted = getattr(dialog, "Accepted", None)
        if accepted is not None:
            return accepted
        return dialog.DialogCode.Accepted

    @staticmethod
    def _messagebox_yes_button():
        yes_button = getattr(QMessageBox, "Yes", None)
        if yes_button is not None:
            return yes_button
        return QMessageBox.StandardButton.Yes

    @staticmethod
    def _messagebox_no_button():
        no_button = getattr(QMessageBox, "No", None)
        if no_button is not None:
            return no_button
        return QMessageBox.StandardButton.No


