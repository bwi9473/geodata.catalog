import geodata_catalog.services.layer_toolbox_service as layer_toolbox_module

from geodata_catalog.services.layer_toolbox_service import LayerToolboxService


class _FakeLogger:
    def info(self, _message: str) -> None:
        return

    def warning(self, _message: str) -> None:
        return


class _FakeRasterLayer:
    created_layers: list["_FakeRasterLayer"] = []

    def __init__(self, uri: str, name: str, provider: str) -> None:
        self._uri = uri
        self._name = name
        self._provider = provider
        self._custom_properties: dict[str, object] = {}
        self._valid = True
        self.repaint_calls = 0
        self._id = f"layer-{len(self.created_layers) + 1}"
        self.created_layers.append(self)

    def isValid(self) -> bool:
        return self._valid

    def setDataSource(self, uri: str, name: str, provider: str) -> bool:
        self._uri = uri
        self._name = name
        self._provider = provider
        return True

    def setName(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name

    def setCustomProperty(self, key: str, value) -> None:
        self._custom_properties[key] = value

    def customProperty(self, key: str, default=None):
        return self._custom_properties.get(key, default)

    def triggerRepaint(self) -> None:
        self.repaint_calls += 1

    def id(self) -> str:
        return self._id


class _FakeLayerTreeRoot:
    def __init__(self) -> None:
        self.inserted_layers: list[_FakeRasterLayer] = []

    def children(self) -> list[_FakeRasterLayer]:
        return list(self.inserted_layers)

    def insertLayer(self, index: int, layer: _FakeRasterLayer) -> None:
        self.inserted_layers.insert(index, layer)


class _FakeProject:
    def __init__(self, *layers: _FakeRasterLayer) -> None:
        self._layers = {layer.id(): layer for layer in layers}
        self._root = _FakeLayerTreeRoot()
        self.add_calls = 0
        self.remove_calls: list[str] = []

    def mapLayers(self) -> dict[str, _FakeRasterLayer]:
        return dict(self._layers)

    def addMapLayer(self, layer: _FakeRasterLayer, add_to_legend: bool = True) -> None:
        self.add_calls += 1
        self._layers[layer.id()] = layer
        if add_to_legend and layer not in self._root.inserted_layers:
            self._root.inserted_layers.append(layer)

    def removeMapLayer(self, layer_id: str) -> None:
        self.remove_calls.append(layer_id)
        self._layers.pop(layer_id, None)
        self._root.inserted_layers = [layer for layer in self._root.inserted_layers if layer.id() != layer_id]

    def layerTreeRoot(self) -> _FakeLayerTreeRoot:
        return self._root


class _FakeFeature:
    def __init__(self, values: dict[str, object], fid: int) -> None:
        self._values = dict(values)
        self._fid = fid

    def __getitem__(self, key: str):
        return self._values[key]

    def id(self) -> int:
        return self._fid


class _FakeSettingsManager:
    def __init__(self, initial: dict[str, object] | None = None) -> None:
        self._values = dict(initial or {})

    def get_json(self, key: str, default):
        return self._values.get(key, default)

    def set_json(self, key: str, value) -> None:
        self._values[key] = value


def test_resolve_group_key_defaults_to_all_without_group_field():
    feat = _FakeFeature({"grp": "A"}, fid=5)

    assert LayerToolboxService._resolve_group_key(feat, "") == "__all__"


def test_resolve_group_key_normalizes_empty_and_null_values():
    feat_none = _FakeFeature({"grp": None}, fid=6)
    feat_empty = _FakeFeature({"grp": "   "}, fid=7)

    assert LayerToolboxService._resolve_group_key(feat_none, "grp") == "__null__"
    assert LayerToolboxService._resolve_group_key(feat_empty, "grp") == "__empty__"


def test_resolve_order_key_uses_numeric_values_when_possible():
    feat = _FakeFeature({"ord": "10"}, fid=11)

    assert LayerToolboxService._resolve_order_key(feat, "ord") == (0, 10.0, "", 11)


def test_resolve_order_key_falls_back_to_text_then_feature_id():
    feat = _FakeFeature({"ord": "BRAVO"}, fid=12)
    fallback = _FakeFeature({}, fid=13)

    assert LayerToolboxService._resolve_order_key(feat, "ord") == (1, 0.0, "bravo", 12)
    assert LayerToolboxService._resolve_order_key(fallback, "missing") == (2, 0.0, "", 13)


def test_normalize_line_width_clamps_and_defaults_values():
    assert LayerToolboxService._normalize_line_width(0.01) == 0.1
    assert LayerToolboxService._normalize_line_width(50) == 10.0
    assert LayerToolboxService._normalize_line_width("invalid") == 1.5


def test_default_basemap_and_catalog_include_expected_entries():
    service = LayerToolboxService(logger=None, project=None)

    assert service.default_basemap_name() == "Nominatim / OpenStreetMap Standard"
    names = service.list_basemap_names()
    assert "Nominatim / OpenStreetMap Standard" in names
    assert "CartoDB Positron" in names
    assert "CartoDB Dark Matter (No Labels)" in names
    assert "Esri World Gray Canvas" in names
    assert len(names) == 4

    options = service.list_basemap_options()
    assert all(str(item.get("preview_file", "")).strip() for item in options)


def test_find_basemap_definition_supports_openstreetmap_alias():
    service = LayerToolboxService(logger=None, project=None)

    basemap = service._find_basemap_definition("OpenStreetMap Standard")
    assert basemap is not None
    assert basemap["name"] == "Nominatim / OpenStreetMap Standard"


def test_set_basemap_reuses_existing_layer_when_switching(monkeypatch):
    monkeypatch.setattr(layer_toolbox_module, "QgsRasterLayer", _FakeRasterLayer)
    _FakeRasterLayer.created_layers.clear()

    existing = _FakeRasterLayer("type=xyz&url=old", "Nominatim / OpenStreetMap Standard", "wms")
    project = _FakeProject(existing)
    settings = _FakeSettingsManager()
    service = LayerToolboxService(logger=_FakeLogger(), project=project, settings_manager=settings)
    service._tag_basemap_layer(existing, "Nominatim / OpenStreetMap Standard")

    created_before = len(_FakeRasterLayer.created_layers)
    result = service.set_basemap("CartoDB Positron")

    assert result is True
    assert len(_FakeRasterLayer.created_layers) == created_before
    assert existing.name() == "CartoDB Positron"
    assert existing.customProperty(service.BASEMAP_NAME_PROPERTY, "") == "CartoDB Positron"
    assert existing.repaint_calls == 1
    assert project.remove_calls == []
    assert settings.get_json(service.BASEMAP_SETTINGS_KEY, "") == "CartoDB Positron"


def test_set_basemap_is_noop_when_selection_is_already_active(monkeypatch):
    monkeypatch.setattr(layer_toolbox_module, "QgsRasterLayer", _FakeRasterLayer)
    _FakeRasterLayer.created_layers.clear()

    existing = _FakeRasterLayer("type=xyz&url=current", "Nominatim / OpenStreetMap Standard", "wms")
    project = _FakeProject(existing)
    settings = _FakeSettingsManager()
    service = LayerToolboxService(logger=_FakeLogger(), project=project, settings_manager=settings)
    service._tag_basemap_layer(existing, "Nominatim / OpenStreetMap Standard")

    created_before = len(_FakeRasterLayer.created_layers)
    result = service.set_basemap("OpenStreetMap Standard")

    assert result is True
    assert len(_FakeRasterLayer.created_layers) == created_before
    assert existing.name() == "Nominatim / OpenStreetMap Standard"
    assert existing.repaint_calls == 0
    assert project.add_calls == 0
    assert project.remove_calls == []
    assert settings.get_json(service.BASEMAP_SETTINGS_KEY, "") == "Nominatim / OpenStreetMap Standard"


def test_preferred_basemap_name_uses_persisted_alias_value():
    settings = _FakeSettingsManager({"layer_toolbox/selected_basemap": "OpenStreetMap Standard"})
    service = LayerToolboxService(logger=_FakeLogger(), project=None, settings_manager=settings)

    assert service.preferred_basemap_name() == "Nominatim / OpenStreetMap Standard"


def test_ensure_preferred_basemap_loaded_applies_saved_choice(monkeypatch):
    monkeypatch.setattr(layer_toolbox_module, "QgsRasterLayer", _FakeRasterLayer)
    _FakeRasterLayer.created_layers.clear()

    settings = _FakeSettingsManager({"layer_toolbox/selected_basemap": "Esri World Gray Canvas"})
    project = _FakeProject()
    service = LayerToolboxService(logger=_FakeLogger(), project=project, settings_manager=settings)

    result = service.ensure_preferred_basemap_loaded()

    assert result is True
    layers = list(project.mapLayers().values())
    assert len(layers) == 1
    assert layers[0].name() == "Esri World Gray Canvas"


def test_muac_extent_wgs84_has_expected_bounds():
    assert LayerToolboxService.muac_extent_wgs84() == (2.0, 48.5, 12.5, 56.0)


def test_extract_flight_level_ranges_collects_unique_sorted_ranges():
    features = [
        _FakeFeature({"fl_lower": 355, "fl_upper": 999}, fid=1),
        _FakeFeature({"fl_lower": "375", "fl_upper": "999"}, fid=2),
        _FakeFeature({"fl_lower": "FL355", "fl_upper": "FL999"}, fid=3),
        _FakeFeature({"fl_lower": 999, "fl_upper": 375}, fid=4),
    ]

    ranges = LayerToolboxService._extract_flight_level_ranges(features, "fl_lower", "fl_upper")
    assert ranges == [(355, 999), (375, 999)]


def test_extract_flight_level_ranges_ignores_invalid_rows():
    features = [
        _FakeFeature({"fl_lower": None, "fl_upper": 999}, fid=1),
        _FakeFeature({"fl_lower": "", "fl_upper": "999"}, fid=2),
        _FakeFeature({"fl_lower": "ABC", "fl_upper": "999"}, fid=3),
    ]

    ranges = LayerToolboxService._extract_flight_level_ranges(features, "fl_lower", "fl_upper")
    assert ranges == []


def test_build_fl_range_expression_and_label():
    expr = LayerToolboxService._build_fl_range_expression("fl_lower", "fl_upper", 355, 999)
    label = LayerToolboxService._format_fl_range_label(355, 999)

    assert expr == '"fl_lower" = 355 AND "fl_upper" = 999'
    assert label == "355 - 999"


class _FakeWkbTypes:
    PolygonGeometry = 1
    LineGeometry = 2
    PointGeometry = 3

    @staticmethod
    def geometryType(value):
        return value


class _FakeVectorLayerForGeometry:
    def __init__(self, geometry_type: int) -> None:
        self._geometry_type = geometry_type

    def wkbType(self) -> int:
        return self._geometry_type


def test_vertex_source_layer_accepts_polygon_and_linestring(monkeypatch):
    monkeypatch.setattr(layer_toolbox_module, "QgsWkbTypes", _FakeWkbTypes)
    service = LayerToolboxService(logger=_FakeLogger(), project=None)

    polygon_layer = _FakeVectorLayerForGeometry(_FakeWkbTypes.PolygonGeometry)
    line_layer = _FakeVectorLayerForGeometry(_FakeWkbTypes.LineGeometry)
    point_layer = _FakeVectorLayerForGeometry(_FakeWkbTypes.PointGeometry)

    assert service._is_vertex_source_layer(polygon_layer) is True
    assert service._is_vertex_source_layer(line_layer) is True
    assert service._is_vertex_source_layer(point_layer) is False