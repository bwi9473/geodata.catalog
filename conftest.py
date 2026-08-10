"""Root conftest: install QGIS stubs before any geodata_catalog module is loaded.

This conftest runs before any test collection so that the hard QGIS imports in
ui/catalog_dockwidget.py and ui/datasource_dialog.py do not crash the test run.
All service-layer tests (which have no Qt dependency) can then be collected and
executed without a running QGIS instance.
"""
from __future__ import annotations

import sys
import types


def _make_stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__spec__ = None  # type: ignore[assignment]
    return mod


def _install_qgis_stubs() -> None:
    if "qgis" in sys.modules:
        return  # Running inside QGIS — nothing to do.

    qgis = _make_stub("qgis")
    qgis_core = _make_stub("qgis.core")
    qgis_pyqt = _make_stub("qgis.PyQt")
    qgis_pyqt_core = _make_stub("qgis.PyQt.QtCore")
    qgis_pyqt_widgets = _make_stub("qgis.PyQt.QtWidgets")

    class _FakeQt:
        UserRole = 256
        LeftDockWidgetArea = 1
        Horizontal = 1
        CustomContextMenu = 2
        ItemIsEnabled = 1
        ItemIsUserCheckable = 2
        ItemIsSelectable = 4
        Unchecked = 0
        Checked = 2
        TextSelectableByMouse = 1

        class ItemDataRole:
            UserRole = 256

        class DockWidgetArea:
            LeftDockWidgetArea = 1

        class Orientation:
            Horizontal = 1

        class ContextMenuPolicy:
            CustomContextMenu = 2

    qgis_pyqt_core.Qt = _FakeQt  # type: ignore[attr-defined]
    qgis_pyqt_core.pyqtSignal = lambda *a, **kw: object()  # type: ignore[attr-defined]

    class _FakeSignal:
        def connect(self, *args, **kwargs):
            return None

    class _WidgetStub:
        def __init__(self, *args, **kwargs):
            self._items = []
            self._current_data = None
            self._value = 0
            self.destroyed = _FakeSignal()
            self.itemSelectionChanged = _FakeSignal()
            self.itemChanged = _FakeSignal()
            self.clicked = _FakeSignal()
            self.customContextMenuRequested = _FakeSignal()

        def __getattr__(self, _name):
            def _noop(*_a, **_kw):
                return None

            return _noop

    class _QComboBoxStub(_WidgetStub):
        def addItem(self, text, data=None):
            self._items.append((text, data))
            if self._current_data is None:
                self._current_data = data

        def count(self):
            return len(self._items)

        def currentData(self):
            return self._current_data

    class _QSpinBoxStub(_WidgetStub):
        def setValue(self, value):
            self._value = value

        def value(self):
            return self._value

    class _QTableWidgetItemStub:
        def __init__(self, text=""):
            self._text = text
            self._data = {}

        def setFlags(self, *_args, **_kwargs):
            return None

        def setCheckState(self, *_args, **_kwargs):
            return None

        def setData(self, key, value):
            self._data[key] = value

        def data(self, key):
            return self._data.get(key)

        def column(self):
            return 0

    class _QActionStub:
        def __init__(self, *args, **kwargs):
            self.triggered = _FakeSignal()

    class _QMenuStub(_WidgetStub):
        def addSeparator(self):
            return None

        def addAction(self, *_args, **_kwargs):
            return _QActionStub()

    qgis_pyqt_widgets.QDockWidget = _WidgetStub  # type: ignore[attr-defined]
    qgis_pyqt_widgets.QTableWidget = _WidgetStub  # type: ignore[attr-defined]
    qgis_pyqt_widgets.QTableWidgetItem = _QTableWidgetItemStub  # type: ignore[attr-defined]
    qgis_pyqt_widgets.QComboBox = _QComboBoxStub  # type: ignore[attr-defined]
    qgis_pyqt_widgets.QSpinBox = _QSpinBoxStub  # type: ignore[attr-defined]
    qgis_pyqt_widgets.QAction = _QActionStub  # type: ignore[attr-defined]
    qgis_pyqt_widgets.QMenu = _QMenuStub  # type: ignore[attr-defined]

    # Catch-all: any widget attribute access returns a generic stub class.
    qgis_pyqt_widgets.__class__ = type(
        "AutoStubWidgetsModule",
        (types.ModuleType,),
        {"__getattr__": lambda self, name: object},
    )

    class _TextEditStub:
        NoWrap = 0

        class LineWrapMode:
            NoWrap = 0

    qgis_pyqt_widgets.QTextEdit = _TextEditStub  # type: ignore[attr-defined]

    qgis.core = qgis_core  # type: ignore[attr-defined]
    qgis.PyQt = qgis_pyqt  # type: ignore[attr-defined]

    class _FakeMapLayerType:
        VectorLayer = 0

    qgis_core.QgsMapLayerType = _FakeMapLayerType  # type: ignore[attr-defined]

    for mod_name, mod in [
        ("qgis", qgis),
        ("qgis.core", qgis_core),
        ("qgis.PyQt", qgis_pyqt),
        ("qgis.PyQt.QtCore", qgis_pyqt_core),
        ("qgis.PyQt.QtWidgets", qgis_pyqt_widgets),
    ]:
        sys.modules[mod_name] = mod


_install_qgis_stubs()
