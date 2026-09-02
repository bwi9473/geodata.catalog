from __future__ import annotations

from collections.abc import Iterable, Mapping

try:
    from qgis.PyQt.QtWidgets import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QVBoxLayout,
    )
except ImportError:  # pragma: no cover
    QComboBox = None
    QDialog = object
    QDialogButtonBox = None
    QFormLayout = None
    QLabel = None
    QLineEdit = None
    QMessageBox = None
    QVBoxLayout = None


def _dialog_button(name: str):
    button = getattr(QDialogButtonBox, name, None)
    if button is not None:
        return button
    return getattr(QDialogButtonBox.StandardButton, name)


class SaveLayerViewDialog(QDialog):
    """Collect a target layer and name for a user-local saved view."""

    def __init__(
        self,
        parent=None,
        layers: Iterable[tuple[str, str, str]] = (),
        selected_key: str = "",
        existing_names: Mapping[str, Iterable[str]] | Iterable[str] = (),
    ) -> None:
        if QDialog is object:  # pragma: no cover
            raise RuntimeError("QGIS runtime is not available.")
        super().__init__(parent)
        self._existing_names_by_layer = (
            {key: {name.strip().casefold() for name in names if name.strip()} for key, names in existing_names.items()}
            if isinstance(existing_names, Mapping)
            else {selected_key: {name.strip().casefold() for name in existing_names if name.strip()}}
        )
        self._existing_names: set[str] = set()
        self.setWindowTitle("Save Layer View")
        self.setModal(True)
        self.resize(440, 180)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        hint = QLabel("Save the current filter and grouping for this layer.", self)
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()
        self._layer_combo = QComboBox(self)
        for datasource_id, layer_name, display_name in layers:
            key = f"{datasource_id}:{layer_name}"
            self._layer_combo.addItem(display_name, (datasource_id, layer_name, display_name))
            if key == selected_key:
                self._layer_combo.setCurrentIndex(self._layer_combo.count() - 1)
        self._layer_combo.setEnabled(not bool(selected_key))
        self._layer_combo.currentIndexChanged.connect(self._refresh_existing_names)
        self._refresh_existing_names()
        form.addRow("Layer", self._layer_combo)

        self._name_edit = QLineEdit(self)
        self._name_edit.setPlaceholderText("Name of this view")
        self._name_edit.returnPressed.connect(self.accept)
        form.addRow("View name", self._name_edit)
        root.addLayout(form)

        buttons = QDialogButtonBox(_dialog_button("Save") | _dialog_button("Cancel"), self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def selected_layer(self) -> tuple[str, str, str]:
        return tuple(self._layer_combo.currentData() or ("", "", ""))

    def _refresh_existing_names(self, _index: int = -1) -> None:
        datasource_id, layer_name, _display_name = self.selected_layer()
        self._existing_names = self._existing_names_by_layer.get(
            f"{datasource_id}:{layer_name}", set()
        )

    def view_name(self) -> str:
        return self._name_edit.text().strip()

    def accept(self) -> None:
        name = self.view_name()
        if not name:
            QMessageBox.warning(self, "Save Layer View", "Enter a name for the layer view.")
            self._name_edit.setFocus()
            return
        if name.casefold() in self._existing_names:
            response = QMessageBox.question(
                self,
                "Overwrite Layer View",
                f"A view named '{name}' already exists for this layer. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if response != QMessageBox.Yes:
                return
        super().accept()