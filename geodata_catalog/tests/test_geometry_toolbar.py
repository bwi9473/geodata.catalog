from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from geodata_catalog.ui import geometry_toolbar as toolbar_module
from geodata_catalog.ui.geometry_toolbar import GeometryToolbar


class _Action:
    def __init__(self):
        self.checked = False
        self.blocked = False

    def isChecked(self):
        return self.checked

    def setChecked(self, checked):
        self.checked = checked

    def blockSignals(self, blocked):
        previous = self.blocked
        self.blocked = blocked
        return previous


@pytest.fixture
def marker_toolbar(monkeypatch):
    monkeypatch.setattr(
        toolbar_module,
        "Qt",
        SimpleNamespace(MouseButton=SimpleNamespace(LeftButton=1, RightButton=2)),
    )
    monkeypatch.setattr(
        toolbar_module, "QgsMapToolEmitPoint",
        lambda canvas: SimpleNamespace(canvasClicked=Mock()),
    )
    previous_tool = object()
    canvas = Mock()
    canvas.mapTool.return_value = previous_tool
    iface = Mock()
    iface.mapCanvas.return_value = canvas
    toolbar = GeometryToolbar(
        iface, Mock(),
        on_place_marker_requested=Mock(return_value=True),
        on_hide_marker_requested=Mock(),
        has_saved_marker=Mock(return_value=False),
        on_marker_position_selected=Mock(return_value=True),
    )
    toolbar._place_marker_action = _Action()

    def set_tool(tool):
        old = canvas.mapTool.return_value
        canvas.mapTool.return_value = tool
        toolbar._on_map_tool_set(tool, old)

    canvas.setMapTool.side_effect = set_tool
    canvas.unsetMapTool.side_effect = lambda tool: set_tool(None)
    return toolbar, canvas, previous_tool


def test_unconfigured_marker_starts_map_selection(marker_toolbar):
    toolbar, canvas, previous = marker_toolbar
    toolbar._on_place_marker_toggled(True)

    assert canvas.mapTool() is toolbar._marker_map_tool
    assert toolbar._previous_map_tool is previous
    toolbar._marker_map_tool.canvasClicked.connect.assert_called_once_with(
        toolbar._on_canvas_marker_clicked
    )
    toolbar._on_place_marker_requested.assert_not_called()


def test_selecting_marker_saves_and_restores_previous_tool(marker_toolbar):
    toolbar, canvas, previous = marker_toolbar
    toolbar._on_place_marker_toggled(True)
    point = object()
    toolbar._on_canvas_marker_clicked(point, 1)

    toolbar._on_marker_position_selected.assert_called_once_with(point)
    assert toolbar._marker_visible is True
    assert toolbar._place_marker_action.isChecked() is True
    assert canvas.mapTool() is previous


def test_configured_marker_is_shown_and_hidden_without_reset(marker_toolbar):
    toolbar, canvas, previous = marker_toolbar
    toolbar._has_saved_marker.return_value = True
    toolbar._on_place_marker_toggled(True)

    toolbar._on_place_marker_requested.assert_called_once_with()
    assert toolbar._place_marker_action.isChecked() is True
    assert canvas.mapTool() is previous

    toolbar._on_place_marker_toggled(False)
    toolbar._on_hide_marker_requested.assert_called_once_with()
    assert toolbar._marker_visible is False
    toolbar._on_marker_position_selected.assert_not_called()


@pytest.mark.parametrize("visible", [False, True])
def test_cancel_preserves_existing_marker_and_visibility(marker_toolbar, visible):
    toolbar, canvas, previous = marker_toolbar
    toolbar._marker_visible = visible
    toolbar._activate_marker_mode()
    toolbar._on_canvas_marker_clicked(object(), 2)

    toolbar._on_marker_position_selected.assert_not_called()
    toolbar._on_hide_marker_requested.assert_not_called()
    assert toolbar._marker_visible is visible
    assert toolbar._place_marker_action.isChecked() is visible
    assert canvas.mapTool() is previous


def test_change_position_replaces_marker_and_keeps_it_visible(marker_toolbar):
    toolbar, canvas, previous = marker_toolbar
    toolbar._has_saved_marker.return_value = True
    toolbar._marker_visible = True
    toolbar._activate_marker_mode()
    toolbar._activate_marker_mode()
    point = object()
    toolbar._on_canvas_marker_clicked(point, 1)

    toolbar._on_marker_position_selected.assert_called_once_with(point)
    assert toolbar._marker_visible is True
    assert canvas.mapTool() is previous


def test_failed_placement_keeps_selection_active(marker_toolbar):
    toolbar, canvas, _ = marker_toolbar
    toolbar._on_marker_position_selected.return_value = False
    toolbar._activate_marker_mode()
    toolbar._on_canvas_marker_clicked(object(), 1)

    assert toolbar._marker_visible is False
    assert canvas.mapTool() is toolbar._marker_map_tool
    toolbar._logger.warning.assert_called_once()


def test_failed_restore_unchecks_button(marker_toolbar):
    toolbar, _, _ = marker_toolbar
    toolbar._has_saved_marker.return_value = True
    toolbar._on_place_marker_requested.return_value = False
    toolbar._place_marker_action.setChecked(True)
    toolbar._on_place_marker_toggled(True)

    assert toolbar._place_marker_action.isChecked() is False
    assert toolbar._marker_visible is False


def test_switching_tools_cancels_selection_without_saving(marker_toolbar):
    toolbar, canvas, _ = marker_toolbar
    toolbar._place_marker_action.setChecked(True)
    toolbar._activate_marker_mode()
    canvas.setMapTool(object())

    assert toolbar._place_marker_action.isChecked() is False
    toolbar._on_marker_position_selected.assert_not_called()


def test_cancel_without_previous_tool_unsets_marker_tool(marker_toolbar):
    toolbar, canvas, _ = marker_toolbar
    canvas.mapTool.return_value = None
    toolbar._activate_marker_mode()
    toolbar._on_canvas_marker_clicked(object(), 2)

    canvas.unsetMapTool.assert_called_once_with(toolbar._marker_map_tool)
    assert canvas.mapTool() is None


def test_missing_map_tool_resets_button_and_logs(marker_toolbar, monkeypatch):
    toolbar, _, _ = marker_toolbar
    monkeypatch.setattr(toolbar_module, "QgsMapToolEmitPoint", None)
    toolbar._place_marker_action.setChecked(True)
    toolbar._on_place_marker_toggled(True)

    assert toolbar._place_marker_action.isChecked() is False
    toolbar._logger.warning.assert_called_once()


@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize("execute_name", ["exec", "exec_"])
def test_context_menu_offers_position_selection(
    marker_toolbar, monkeypatch, configured, execute_name,
):
    toolbar, _, _ = marker_toolbar
    toolbar._has_saved_marker.return_value = configured
    toolbar._toolbar = Mock()
    action = Mock()
    execute = Mock()
    menu = SimpleNamespace(addAction=Mock(return_value=action))
    setattr(menu, execute_name, execute)
    monkeypatch.setattr(toolbar_module, "QMenu", Mock(return_value=menu))
    position = object()
    toolbar._show_marker_context_menu(position)

    menu.addAction.assert_called_once_with(
        "Change marker position..." if configured else "Set marker position..."
    )
    action.triggered.connect.assert_called_once_with(toolbar._activate_marker_mode)
    button = toolbar._toolbar.widgetForAction.return_value
    execute.assert_called_once_with(button.mapToGlobal.return_value)
    button.mapToGlobal.assert_called_once_with(position)


def test_enum_resolver_supports_qt5_and_qt6():
    assert toolbar_module._enum(
        SimpleNamespace(LeftButton=1), "MouseButton", "LeftButton"
    ) == 1
    assert toolbar_module._enum(
        SimpleNamespace(MouseButton=SimpleNamespace(LeftButton=2)),
        "MouseButton", "LeftButton",
    ) == 2
