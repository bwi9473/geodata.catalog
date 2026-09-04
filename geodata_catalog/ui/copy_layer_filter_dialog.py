from __future__ import annotations

from collections.abc import Iterable

try:
    from qgis.PyQt.QtWidgets import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QLabel,
        QMessageBox,
        QVBoxLayout,
    )
except ImportError:  # pragma: no cover
    QComboBox = None
    QDialog = object
    QDialogButtonBox = None
    QFormLayout = None
    QLabel = None
    QMessageBox = None
    QVBoxLayout = None


def _dialog_button(name: str):
    button = getattr(QDialogButtonBox, name, None)
    if button is not None:
        return button
    return getattr(QDialogButtonBox.StandardButton, name)


class CopyLayerFilterDialog(QDialog):
    """Choose source and target catalog layers for copying the current filter."""

    def __init__(
        self,
        parent=None,
        layers: Iterable[tuple[str, str, str]] = (),
        selected_from_key: str = "",
    ) -> None:
        if QDialog is object:  # pragma: no cover
            raise RuntimeError("QGIS runtime is not available.")
        super().__init__(parent)
        self.setWindowTitle("Apply Filter to Layer")
        self.setModal(True)
        self.resize(440, 160)

        layer_items = list(layers)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        hint = QLabel("Copy the current filter from one loaded catalog layer to another.", self)
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()
        self._from_combo = QComboBox(self)
        self._to_combo = QComboBox(self)

        for datasource_id, layer_name, display_name in layer_items:
            data = (datasource_id, layer_name, display_name)
            key = f"{datasource_id}:{layer_name}"
            self._from_combo.addItem(display_name, data)
            self._to_combo.addItem(display_name, data)
            if key == selected_from_key:
                self._from_combo.setCurrentIndex(self._from_combo.count() - 1)

        self._select_first_different_target()
        self._from_combo.currentIndexChanged.connect(lambda _index: self._select_first_different_target())

        form.addRow("From layer", self._from_combo)
        form.addRow("To layer", self._to_combo)
        root.addLayout(form)

        buttons = QDialogButtonBox(_dialog_button("Ok") | _dialog_button("Cancel"), self)
        ok_button = buttons.button(_dialog_button("Ok"))
        if ok_button is not None:
            ok_button.setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def selected_from_layer(self) -> tuple[str, str, str]:
        return tuple(self._from_combo.currentData() or ("", "", ""))

    def selected_to_layer(self) -> tuple[str, str, str]:
        return tuple(self._to_combo.currentData() or ("", "", ""))

    def accept(self) -> None:
        from_layer = self.selected_from_layer()
        to_layer = self.selected_to_layer()
        if not from_layer[0] or not to_layer[0]:
            QMessageBox.warning(self, "Apply Filter to Layer", "Choose both a source and target layer.")
            return
        if from_layer[:2] == to_layer[:2]:
            QMessageBox.warning(self, "Apply Filter to Layer", "Choose a different target layer.")
            self._to_combo.setFocus()
            return
        super().accept()

    def _select_first_different_target(self) -> None:
        from_layer = self.selected_from_layer()
        if not from_layer[0]:
            return
        current_to = self.selected_to_layer()
        if current_to[0] and current_to[:2] != from_layer[:2]:
            return
        for index in range(self._to_combo.count()):
            candidate = tuple(self._to_combo.itemData(index) or ("", "", ""))
            if candidate[:2] != from_layer[:2]:
                self._to_combo.setCurrentIndex(index)
                return