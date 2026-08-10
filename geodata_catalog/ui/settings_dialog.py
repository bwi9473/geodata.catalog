from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    """UI dialog for plugin-level preferences."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("GeoData Catalog Settings")
        self.resize(420, 180)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.default_crs_edit = QLineEdit()
        self.default_style_path_edit = QLineEdit()
        form.addRow("Default CRS", self.default_crs_edit)
        form.addRow("Default Style Folder", self.default_style_path_edit)

        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def get_settings(self) -> dict[str, str]:
        return {
            "default_crs": self.default_crs_edit.text().strip(),
            "default_style_folder": self.default_style_path_edit.text().strip(),
        }
