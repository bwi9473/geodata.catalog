import base64
import json
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from geodata_catalog.exceptions import ConfigurationException
from geodata_catalog.metadata.layer_config_repository import LayerConfig, LayerConfigRepository
from geodata_catalog.metadata.layer_repository import LayerRepository
from geodata_catalog.metadata.settings_manager import SettingsManager
from geodata_catalog.models.layer_definition import LayerDefinition
from geodata_catalog.services import style_service
from geodata_catalog import svg_markers
from geodata_catalog.svg_markers import portable_svg_reference
from geodata_catalog.ui import layer_config_dialog


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>'
EMBEDDED = "base64:" + base64.b64encode(SVG).decode("ascii")


def test_embed_svg_preserves_exact_content_after_source_is_deleted(tmp_path):
    source = tmp_path / "custom marker.svg"
    source.write_bytes(SVG)
    reference = portable_svg_reference(str(source))
    source.unlink()
    assert reference == EMBEDDED
    assert portable_svg_reference(reference) == EMBEDDED
    assert portable_svg_reference("data:image/svg+xml;base64," + reference[7:]) == EMBEDDED
    assert portable_svg_reference(None) is None
    assert portable_svg_reference("  ") is None


@pytest.mark.parametrize("old_path", [
    "C:/PROGRA~1/QGIS42~1.2/apps/qgis/./svg//transport/transport_airport.svg",
    r"C:\Program Files\QGIS 3.40\apps\qgis-ltr\svg\transport\transport_airport.svg",
    "/usr/share/qgis/svg/transport/transport_airport.svg",
    "transport/transport_airport.svg",
])
def test_old_qgis_paths_resolve_in_current_svg_folders(tmp_path, monkeypatch, old_path):
    root = tmp_path / "current installation" / "svg"
    marker = root / "transport" / "transport_airport.svg"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(SVG)
    monkeypatch.setattr(svg_markers, "QgsApplication", SimpleNamespace(
        svgPaths=lambda: [str(tmp_path / "missing"), str(root)],
    ))
    assert portable_svg_reference(old_path) == EMBEDDED


def test_old_plugin_path_resolves_against_current_plugin(monkeypatch):
    monkeypatch.setattr(svg_markers, "QgsApplication", None)
    marker = Path(svg_markers.__file__).parent / "resources" / "aviation_symbols" / "radar.svg"
    old_path = "Z:/old-profile/python/plugins/geodata_catalog/resources/aviation_symbols/radar.svg"
    assert base64.b64decode(portable_svg_reference(old_path)[7:]) == marker.read_bytes()


@pytest.mark.parametrize("content", [
    b"",
    b"<svg>",
    b"<html/>",
    b'<svg><image href="picture.png"/></svg>',
    b'<svg xmlns:xlink="http://www.w3.org/1999/xlink"><use xlink:href="../symbols.svg#airport"/></svg>',
    b'<svg><style>circle { fill: url(../colors.svg#blue); }</style></svg>',
    b'<svg><style>@import "style.css";</style></svg>',
])
def test_invalid_or_external_svg_resources_are_rejected(content):
    reference = "base64:" + base64.b64encode(content).decode("ascii")
    with pytest.raises(ConfigurationException):
        portable_svg_reference(reference)


def test_internal_svg_references_remain_supported():
    content = b'<svg><defs><circle id="point" r="3"/></defs><use href="#point" fill="url(#color)"/></svg>'
    reference = "base64:" + base64.b64encode(content).decode("ascii")
    assert portable_svg_reference(reference) == reference


def test_missing_svg_and_corrupt_base64_report_explicit_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(svg_markers, "QgsApplication", None)
    with pytest.raises(ConfigurationException, match="not found"):
        portable_svg_reference(str(tmp_path / "missing.svg"))
    with pytest.raises(ConfigurationException, match="base64"):
        portable_svg_reference("base64:not base64!")


def test_layer_configuration_can_be_copied_without_the_original_svg(tmp_path):
    source = tmp_path / "marker.svg"
    source.write_bytes(SVG)
    file_path = tmp_path / "layer_config.json"
    repository = LayerConfigRepository(file_path)
    repository.save(LayerConfig("ds", "airports", svg_marker_path=str(source)))
    copied = tmp_path / "another computer.json"
    copied.write_bytes(file_path.read_bytes())
    source.unlink()
    loaded = LayerConfigRepository(copied).get("ds", "airports")
    assert loaded is not None
    assert loaded.svg_marker_path == EMBEDDED
    assert portable_svg_reference(loaded.svg_marker_path) == EMBEDDED
    assert str(source) not in copied.read_text(encoding="utf-8")


def test_invalid_marker_does_not_overwrite_existing_layer_configuration(tmp_path):
    file_path = tmp_path / "layer_config.json"
    repository = LayerConfigRepository(file_path)
    repository.save(LayerConfig("ds", "airports", svg_marker_path=EMBEDDED))
    original = file_path.read_bytes()
    with pytest.raises(ConfigurationException):
        repository.save(LayerConfig("ds", "airports", svg_marker_path="base64:invalid!"))
    assert file_path.read_bytes() == original


def test_saving_one_layer_does_not_require_repairing_other_legacy_markers(tmp_path):
    file_path = tmp_path / "layer_config.json"
    old = LayerConfig("ds", "other", svg_marker_path=str(tmp_path / "missing.svg"))
    file_path.write_text(json.dumps([old.to_dict()]), encoding="utf-8")
    repository = LayerConfigRepository(file_path)
    repository.save(LayerConfig("ds", "airports", svg_marker_path=EMBEDDED))
    assert repository.get("ds", "airports").svg_marker_path == EMBEDDED
    assert repository.get("ds", "other").svg_marker_path == old.svg_marker_path
    repository.delete("ds", "airports")
    assert repository.get("ds", "other") is not None


class _Settings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


def test_main_config_embeds_layer_metadata_without_mutating_the_layer(tmp_path):
    source = tmp_path / "marker.svg"
    source.write_bytes(SVG)
    file_path = tmp_path / "config.json"
    settings = SettingsManager(settings=_Settings(), storage_file_path=str(file_path))
    layer = LayerDefinition(
        "ds", "airports", "Airports", "ogr", "uri",
        metadata={"svg_marker_path": str(source), "other": "preserved"},
    )
    LayerRepository(settings).upsert(layer)
    copied = tmp_path / "copied_config.json"
    copied.write_bytes(file_path.read_bytes())
    source.unlink()
    copied_settings = SettingsManager(settings=_Settings(), storage_file_path=str(copied))
    loaded = LayerRepository(copied_settings).list_all()[0]
    assert loaded.metadata["svg_marker_path"] == EMBEDDED
    assert loaded.metadata["other"] == "preserved"
    assert layer.metadata["svg_marker_path"] == str(source)
    assert json.loads(copied.read_text())["layers"][0]["metadata"]["svg_marker_path"] == EMBEDDED


def test_main_config_can_save_one_marker_while_another_legacy_file_is_missing(tmp_path):
    settings = SettingsManager(settings=_Settings())
    old = LayerDefinition(
        "ds", "other", "Other", "ogr", "uri",
        metadata={"svg_marker_path": str(tmp_path / "missing.svg")},
    )
    settings.set_json("layers", [old.to_dict()])
    repository = LayerRepository(settings)
    repository.upsert(LayerDefinition(
        "ds", "airports", "Airports", "ogr", "uri", metadata={"svg_marker_path": EMBEDDED},
    ))
    layers = {layer.layer_name: layer for layer in repository.list_all()}
    assert layers["airports"].metadata["svg_marker_path"] == EMBEDDED
    assert layers["other"].metadata["svg_marker_path"] == old.metadata["svg_marker_path"]


class _Geometry(Enum):
    Point = 0
    Polygon = 2


def _style_runtime(monkeypatch):
    symbol = Mock()
    symbol.symbolLayerCount.return_value = 1
    symbol.changeSymbolLayer.return_value = True
    svg_api = Mock()
    marker_api = Mock()
    marker_api.createSimple.return_value = symbol
    monkeypatch.setattr(style_service, "Qgis", SimpleNamespace(GeometryType=_Geometry))
    monkeypatch.setattr(style_service, "QgsWkbTypes", object())
    monkeypatch.setattr(style_service, "QgsMarkerSymbol", marker_api)
    monkeypatch.setattr(style_service, "QgsSvgMarkerSymbolLayer", svg_api)
    layer = Mock()
    layer.name.return_value = "Airports"
    layer.geometryType.return_value = _Geometry.Point
    logger = Mock()
    return style_service.StyleService(logger), layer, logger, svg_api, symbol


def test_style_uses_embedded_data_and_qgis4_scoped_geometry(monkeypatch):
    service, layer, logger, svg_api, symbol = _style_runtime(monkeypatch)
    service.apply_svg_marker(layer, EMBEDDED)
    assert svg_api.create.call_args.args[0]["name"] == EMBEDDED
    layer.renderer().setSymbol.assert_called_once_with(symbol)
    layer.triggerRepaint.assert_called_once()
    logger.warning.assert_not_called()
    assert EMBEDDED not in logger.info.call_args.args[0]


def test_style_missing_marker_preserves_existing_symbol(tmp_path, monkeypatch):
    service, layer, logger, svg_api, _symbol = _style_runtime(monkeypatch)
    service.apply_svg_marker(layer, str(tmp_path / "missing.svg"))
    svg_api.create.assert_not_called()
    layer.renderer().setSymbol.assert_not_called()
    layer.triggerRepaint.assert_not_called()
    assert "not found" in logger.warning.call_args.args[0]


def test_style_failed_symbol_creation_is_reported_without_replacing_renderer(monkeypatch):
    service, layer, logger, svg_api, _symbol = _style_runtime(monkeypatch)
    svg_api.create.return_value = None
    service.apply_svg_marker(layer, EMBEDDED)
    layer.renderer().setSymbol.assert_not_called()
    assert "could not create" in logger.warning.call_args.args[0]


def test_style_does_not_replace_non_point_symbols(monkeypatch):
    service, layer, logger, svg_api, _symbol = _style_runtime(monkeypatch)
    layer.geometryType.return_value = _Geometry.Polygon
    service.apply_svg_marker(layer, EMBEDDED)
    svg_api.create.assert_not_called()
    assert "non-point" in logger.warning.call_args.args[0]


def test_style_qgis3_geometry_fallback(monkeypatch):
    service, layer, _logger, _svg_api, symbol = _style_runtime(monkeypatch)
    monkeypatch.setattr(style_service, "Qgis", SimpleNamespace())
    monkeypatch.setattr(style_service, "QgsWkbTypes", SimpleNamespace(PointGeometry=0))
    layer.geometryType.return_value = 0
    service.apply_svg_marker(layer, EMBEDDED)
    layer.renderer().setSymbol.assert_called_once_with(symbol)


def test_svg_preview_uses_embedded_symbol_not_a_filename(monkeypatch):
    _service, _layer, _logger, svg_api, symbol = _style_runtime(monkeypatch)
    pixmap = Mock()
    pixmap.isNull.return_value = False
    preview = Mock(return_value=pixmap)
    icon = object()
    monkeypatch.setattr(style_service, "QSize", lambda width, height: (width, height))
    monkeypatch.setattr(style_service, "QIcon", lambda image: icon if image is pixmap else None)
    monkeypatch.setattr(style_service, "QgsSymbolLayerUtils", SimpleNamespace(symbolPreviewPixmap=preview))
    assert style_service.generate_svg_preview_icon(EMBEDDED) is icon
    assert svg_api.create.call_args.args[0]["name"] == EMBEDDED
    preview.assert_called_once_with(symbol, (16, 16))


def test_dialog_save_rejects_corrupt_svg_without_closing(monkeypatch):
    dialog = layer_config_dialog.LayerConfigDialog.__new__(layer_config_dialog.LayerConfigDialog)
    dialog._svg_marker_path = "base64:invalid!"
    dialog.accept = Mock()
    warning = Mock()
    monkeypatch.setattr(layer_config_dialog, "QMessageBox", SimpleNamespace(warning=warning))
    dialog._on_save()
    warning.assert_called_once()
    dialog.accept.assert_not_called()


def test_dialog_save_preserves_embedded_svg_and_validates_preview(monkeypatch):
    dialog = layer_config_dialog.LayerConfigDialog.__new__(layer_config_dialog.LayerConfigDialog)
    dialog._svg_marker_path = EMBEDDED
    dialog.accept = Mock()
    preview = Mock()
    monkeypatch.setattr(layer_config_dialog, "generate_svg_preview_icon", preview)
    dialog._on_save()
    preview.assert_called_once_with(EMBEDDED)
    dialog.accept.assert_called_once()
    assert dialog._svg_marker_path == EMBEDDED


class _SvgCombo:
    def __init__(self):
        self.items = [("Simple marker (default)", "")]
        self.index = 0

    def addItem(self, *args):
        self.items.append((args[-2], args[-1]))

    def count(self):
        return len(self.items)

    def itemData(self, index):
        return self.items[index][1]

    def setCurrentIndex(self, index):
        self.index = index


def test_dialog_selection_and_preview_use_the_same_portable_reference(tmp_path, monkeypatch):
    source = tmp_path / "marker.svg"
    source.write_bytes(SVG)
    dialog = layer_config_dialog.LayerConfigDialog.__new__(layer_config_dialog.LayerConfigDialog)
    dialog._svg_marker_combo = _SvgCombo()
    preview = Mock(return_value=object())
    monkeypatch.setattr(layer_config_dialog, "generate_svg_preview_icon", preview)
    dialog._add_svg_marker_item("Airport", str(source))
    source.unlink()
    dialog._set_svg_marker_path(EMBEDDED)
    assert dialog._svg_marker_combo.index == 1
    assert dialog._svg_marker_combo.count() == 2
    assert dialog._svg_marker_path == EMBEDDED
    preview.assert_called_once_with(EMBEDDED)


def test_dialog_reports_missing_configured_svg_and_allows_default_marker(tmp_path, monkeypatch):
    dialog = layer_config_dialog.LayerConfigDialog.__new__(layer_config_dialog.LayerConfigDialog)
    dialog._svg_marker_combo = _SvgCombo()
    warning = Mock()
    monkeypatch.setattr(layer_config_dialog, "QMessageBox", SimpleNamespace(warning=warning))
    source = str(tmp_path / "missing.svg")
    dialog._set_svg_marker_path(source)
    warning.assert_called_once()
    assert dialog._svg_marker_path == source
    dialog._set_svg_marker_path("")
    assert dialog._svg_marker_combo.index == 0
    assert dialog._svg_marker_path == ""
