from geodata_catalog.exceptions import LayerLoadException
from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.services.qgis_loader_service import QgisLoaderService


class FakeLayer:
    def __init__(self, valid=True):
        self._valid = valid
        self.crs = None
        self.subset_string = None
        self.assigned_name = None
        self.labels_enabled = False
        self.labeling = None
        self.repaint_calls = 0

    def isValid(self):
        return self._valid

    def setCrs(self, crs):
        self.crs = crs

    def setSubsetString(self, expression):
        self.subset_string = expression

    def name(self):
        return "Fake Layer"

    def setName(self, name):
        self.assigned_name = name

    def setLabeling(self, labeling):
        self.labeling = labeling

    def setLabelsEnabled(self, enabled):
        self.labels_enabled = bool(enabled)

    def triggerRepaint(self):
        self.repaint_calls += 1


class FakeConnector:
    def __init__(self, layer):
        self._layer = layer

    def load_layer(self, layer_name):
        return self._layer


class FakeStyleService:
    def __init__(self):
        self.applied = None

    def apply_default_style(self, layer, style_file):
        self.applied = (layer, style_file)


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))

    def error(self, message):
        self.messages.append(("error", message))


class FakeProject:
    def __init__(self):
        self.layers = []

    def addMapLayer(self, layer):
        self.layers.append(layer)


def test_loader_adds_valid_layer_to_project():
    style_service = FakeStyleService()
    logger = FakeLogger()
    project = FakeProject()
    service = QgisLoaderService(style_service, logger, project=project)

    layer_definition = LayerDefinition(
        datasource_id="ds",
        layer_name="airspace",
        display_name="Airspace",
        provider_key="ogr",
        provider_uri="path",
        default_style_file="style.qml",
        filter_expression='"fl_lower" <= 355 AND "fl_upper" >= 265',
    )

    layer = service.load_layer(layer_definition, FakeConnector(FakeLayer(valid=True)))

    assert layer in project.layers
    assert style_service.applied[1] == "style.qml"
    assert layer.subset_string == '"fl_lower" <= 355 AND "fl_upper" >= 265'
    assert layer.assigned_name == "Airspace"


def test_loader_rejects_invalid_layer():
    style_service = FakeStyleService()
    logger = FakeLogger()
    project = FakeProject()
    service = QgisLoaderService(style_service, logger, project=project)

    layer_definition = LayerDefinition(
        datasource_id="ds",
        layer_name="airspace",
        display_name="Airspace",
        provider_key="ogr",
        provider_uri="path",
    )

    try:
        service.load_layer(layer_definition, FakeConnector(FakeLayer(valid=False)))
    except LayerLoadException:
        pass
    else:
        raise AssertionError("Expected LayerLoadException")


class _FakePalLayerSettings:
    def __init__(self):
        self.fieldName = ""
        self.isExpression = False
        self.enabled = False


class _FakeSimpleLabeling:
    def __init__(self, settings):
        self.settings = settings


def test_apply_labels_enables_labeling_and_repaints(monkeypatch):
    import geodata_catalog.services.qgis_loader_service as loader_module

    monkeypatch.setattr(loader_module, "QgsPalLayerSettings", _FakePalLayerSettings)
    monkeypatch.setattr(loader_module, "QgsVectorLayerSimpleLabeling", _FakeSimpleLabeling)

    service = QgisLoaderService(FakeStyleService(), FakeLogger(), project=FakeProject())
    layer = FakeLayer(valid=True)

    service._apply_labels(layer, "ROUTE")

    assert isinstance(layer.labeling, _FakeSimpleLabeling)
    assert layer.labeling.settings.fieldName == "ROUTE"
    assert layer.labeling.settings.enabled is True
    assert layer.labels_enabled is True
    assert layer.repaint_calls == 1
