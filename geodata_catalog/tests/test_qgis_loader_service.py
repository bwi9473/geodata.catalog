from geodata_catalog.exceptions import LayerLoadException
from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.services.qgis_loader_service import QgisLoaderService


class FakeLayer:
    def __init__(self, valid=True):
        self._valid = valid
        self.crs = None
        self.subset_string = None
        self.assigned_name = None

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
