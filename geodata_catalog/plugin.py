from __future__ import annotations

from geodata_catalog.exceptions import GeoDataCatalogException
from geodata_catalog.logging_utils import PluginLogger
from geodata_catalog.metadata.datasource_repository import DatasourceRepository
from geodata_catalog.metadata.layer_config_repository import LayerConfigRepository
from geodata_catalog.metadata.layer_repository import LayerRepository
from geodata_catalog.metadata.settings_manager import SettingsManager
from geodata_catalog.metadata.system_configuration_repository import (
    DEFAULT_FLIGHT_LEVEL_PRESETS,
    SystemConfigurationRepository,
)
from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.services.datasource_service import DatasourceService
from geodata_catalog.services.layer_filter_service import (
    FlightLevelFilter,
    LayerFilter,
    LayerFilterService,
)
from geodata_catalog.services.layer_service import LayerService
from geodata_catalog.services.qgis_loader_service import QgisLoaderService
from geodata_catalog.services.style_service import StyleService
from geodata_catalog.ui.catalog_dockwidget import CatalogDockWidget
from geodata_catalog.ui.datasource_dialog import DatasourceDialog
from geodata_catalog.ui.layer_config_dialog import LayerConfigDialog
from geodata_catalog.ui.layer_custom_view_dock import LayerCustomViewDock
from geodata_catalog.ui.layer_filter_dialog import LayerFilterDialog

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction, QMenu, QMessageBox

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

        self._action: QAction | None = None
        self._dock_widget: CatalogDockWidget | None = None
        self._layer_cache: dict[str, dict[str, LayerDefinition]] = {}
        self._layer_filter_dialog: LayerFilterDialog | None = None
        self._custom_view_docks: list[LayerCustomViewDock] = []
        self._layer_panel_custom_view_action: QAction | None = None
        self._layer_panel_filter_action: QAction | None = None

    def initGui(self) -> None:
        try:
            self._action = QAction("GeoData Catalog", self.iface.mainWindow())
            self._action.triggered.connect(self._show_dock)
            self.iface.addPluginToMenu("GeoData Catalog", self._action)
            self.iface.addToolBarIcon(self._action)
            self._show_dock()
            self._logger.info("GeoData Catalog initialized")
        except Exception as exc:
            self._logger.error(f"initGui failed: {exc}")
            raise

    def unload(self) -> None:
        if self._dock_widget is not None:
            self.iface.removeDockWidget(self._dock_widget)
            self._dock_widget.deleteLater()
            self._dock_widget = None

        if self._action is not None:
            self.iface.removePluginMenu("GeoData Catalog", self._action)
            self.iface.removeToolBarIcon(self._action)
            self._action = None

        self._logger.info("GeoData Catalog unloaded")

    def _show_dock(self) -> None:
        if self._dock_widget is None:
            self._dock_widget = CatalogDockWidget(self.iface.mainWindow())
            self._dock_widget.add_source_requested.connect(self._on_add_source)
            self._dock_widget.edit_source_requested.connect(self._on_edit_source)
            self._dock_widget.delete_source_requested.connect(self._on_delete_source)
            self._dock_widget.refresh_requested.connect(self._on_refresh_source)
            self._dock_widget.show_all_layers_toggled.connect(self._on_show_all_layers_toggled)
            self._dock_widget.load_layer_requested.connect(self._on_load_layer)
            self._dock_widget.edit_layer_config_requested.connect(self._on_edit_layer_config)
            self.iface.addDockWidget(self._dock_area(), self._dock_widget)
        self._dock_widget.show()
        self._refresh_datasources()
        self._ensure_layer_panel_custom_view_action()

    def _ensure_layer_panel_custom_view_action(self) -> None:
        """Register custom view action in layer panel context menu."""
        if self._layer_panel_custom_view_action is not None:
            return

        layer_tree_view = getattr(self.iface, "layerTreeView", lambda: None)()
        if layer_tree_view is None:
            return

        self._layer_panel_custom_view_action = QAction("Open Custom View…", self.iface.mainWindow())
        self._layer_panel_custom_view_action.triggered.connect(
            self._on_open_custom_view_from_layer_panel
        )

        self._layer_panel_filter_action = QAction("Layer Filter…", self.iface.mainWindow())
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

        actions_to_add = []
        if self._layer_panel_filter_action is not None:
            actions_to_add.append(self._layer_panel_filter_action)
        if self._layer_panel_custom_view_action is not None:
            actions_to_add.append(self._layer_panel_custom_view_action)

        if not actions_to_add:
            return

        menu.addSeparator()
        for action in actions_to_add:
            menu.addAction(action)

    def _on_layer_tree_context_menu(self, pos) -> None:
        layer_tree_view = getattr(self.iface, "layerTreeView", lambda: None)()
        if layer_tree_view is None:
            return

        create_menu = getattr(layer_tree_view, "createContextMenu", None)
        if callable(create_menu):
            menu = create_menu()
            if menu is None:
                return
            actions_to_add = []
            if self._layer_panel_filter_action is not None:
                actions_to_add.append(self._layer_panel_filter_action)
            if self._layer_panel_custom_view_action is not None:
                actions_to_add.append(self._layer_panel_custom_view_action)

            if actions_to_add:
                menu.addSeparator()
                for action in actions_to_add:
                    menu.addAction(action)
            menu.exec(layer_tree_view.viewport().mapToGlobal(pos))
            return

        # Final fallback: build a minimal menu only when the QGIS API cannot supply one.
        menu = QMenu(layer_tree_view)
        if self._layer_panel_filter_action is not None:
            menu.addAction(self._layer_panel_filter_action)
        if self._layer_panel_custom_view_action is not None:
            menu.addAction(self._layer_panel_custom_view_action)
        menu.exec(layer_tree_view.viewport().mapToGlobal(pos))

    def _on_open_custom_view_from_layer_panel(self) -> None:
        layer = self._active_layer()
        if layer is None:
            self._show_error("Custom View", "No active QGIS layer is selected.")
            return

        layer_def = self._find_layer_definition_for_qgis_layer(layer)
        if layer_def is None:
            self._show_error(
                "Custom View",
                "The selected QGIS layer is not managed by GeoData Catalog or was not refreshed yet.",
            )
            return

        self._open_custom_view_for_layer_definition(layer, layer_def)

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
        if self._dock_widget.is_show_all_layers_enabled():
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
        answer = QMessageBox.question(
            self.iface.mainWindow(),
            "Delete Datasource",
            "Delete selected datasource?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
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
        if self._dock_widget is None:
            return
        rows: list[dict[str, str | LayerDefinition]] = []
        try:
            datasources = self._datasource_service.list_datasources()
            for datasource in datasources:
                layers = self._layer_service.discover_layers(datasource)
                self._layer_cache[datasource.id] = {layer.layer_name: layer for layer in layers}
                for layer in layers:
                    rows.append(
                        {
                            "datasource_id": datasource.id,
                            "source_name": datasource.name,
                            "source_type": datasource.datasource_type.value,
                            "layer": layer,
                        }
                    )
            rows.sort(
                key=lambda r: (
                    str(r.get("source_name", "")).casefold(),
                    str((r.get("layer") or LayerDefinition("", "", "", "", "")).display_name).casefold(),
                )
            )
            self._dock_widget.set_all_layers(rows)
            self._logger.info(f"All-layers view refreshed with {len(rows)} loadable layers")
        except GeoDataCatalogException as exc:
            self._show_error("Refresh All Layers", str(exc))

    def _on_load_layer(self, datasource_id: str, layer_name: str) -> None:
        try:
            datasource = self._datasource_service.get_datasource(datasource_id)
            connector = self._datasource_service.get_connector(datasource)
            layer_definition = self._resolve_layer(datasource_id, layer_name)
            self._loader_service.load_layer(layer_definition, connector)
        except GeoDataCatalogException as exc:
            self._show_error("Load Layer", str(exc))

    def _on_edit_layer_config(self, datasource_id: str, layer_name: str) -> None:
        """Open the per-layer config dialog and persist the result."""
        layer_def = self._resolve_layer(datasource_id, layer_name)
        existing_config = self._layer_config_repository.get(datasource_id, layer_name)

        dialog = LayerConfigDialog(
            self.iface.mainWindow(),
            datasource_id=datasource_id,
            layer_name=layer_name,
            display_name=layer_def.display_name,
            existing_config=existing_config,
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

    def _on_open_layer_filter(self) -> None:
        # If the dialog is already open, bring it to the foreground.
        if self._layer_filter_dialog is not None:
            self._layer_filter_dialog.raise_()
            self._layer_filter_dialog.activateWindow()
            return

        layer = self._active_layer()
        if layer is None:
            self._show_error("Layer Filter", "No active QGIS layer is selected.")
            return

        existing_subset = layer.subsetString() or ""
        current_fl = LayerFilterService.parse_fl_from_subset_string(existing_subset)

        # Resolve LayerDefinition to get configured searchable_columns.
        layer_def = self._find_layer_definition_for_qgis_layer(layer)
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
        
        # Collect distinct values for columns that use them
        distinct_values: dict[str, list[str]] = {}
        filtered_distinct_values: dict[str, dict[str, list[str]]] = {}
        if searchable_columns:
            distinct_values, filtered_distinct_values = self._collect_distinct_values(layer, searchable_columns)

        dialog = LayerFilterDialog(
            self.iface.mainWindow(),
            layer_name=layer.name(),
            initial_filter=initial_filter,
            searchable_columns=searchable_columns,
            distinct_values=distinct_values,
            filtered_distinct_values=filtered_distinct_values,
            show_flight_level=show_flight_level,
            flight_level_presets=flight_level_presets,
        )
        dialog.filter_applied.connect(lambda f: self._apply_layer_filter(layer, f))
        dialog.finished.connect(self._on_layer_filter_dialog_closed)
        self._layer_filter_dialog = dialog
        dialog.show()

    def _open_custom_view_for_layer_definition(self, qgis_layer, layer_def: LayerDefinition) -> None:
        view_columns = layer_def.metadata.get("view_columns", []) or []
        if not view_columns:
            self._show_error(
                "Custom View",
                "No custom view columns configured. Use Edit Layer Config first.",
            )
            return

        records = self._collect_layer_records(qgis_layer, view_columns)
        window = LayerCustomViewDock(
            self.iface.mainWindow(),
            layer=qgis_layer,
            layer_name=layer_def.display_name,
            columns=view_columns,
            records=records,
            logger=self._logger,
        )
        window.destroyed.connect(lambda *_: self._on_custom_view_window_closed(window))
        window.show()
        self._custom_view_docks.append(window)

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
        canvas = getattr(self.iface, "mapCanvas", lambda: None)()
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

    def _on_layer_filter_dialog_closed(self) -> None:
        self._layer_filter_dialog = None

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


