from __future__ import annotations

import json
from typing import Any

from geodata_catalog.exceptions import ConfigurationException
from geodata_catalog.models.datasource import Datasource, DatasourceType

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


USER_ROLE = getattr(Qt, "UserRole", Qt.ItemDataRole.UserRole)
TEXTEDIT_NO_WRAP = getattr(QTextEdit, "NoWrap", QTextEdit.LineWrapMode.NoWrap)


class DatasourceDialog(QDialog):
    """UI dialog for creating or editing datasource connection definitions.

    This dialog is intentionally limited to connection parameters (host, path,
    credentials, etc.).  Per-layer display settings such as ``label_column`` and
    ``searchable_columns`` are managed via the right-click **Edit Layer Config**
    menu on individual layers.
    """

    def __init__(self, parent=None, datasource: Datasource | None = None) -> None:
        super().__init__(parent)
        self._datasource = datasource
        self.setWindowTitle("Datasource")
        self.setModal(True)
        self.resize(640, 420)
        self._build_ui()
        if datasource:
            self._populate(datasource)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._name_edit = QLineEdit()
        form.addRow(QLabel("Name"), self._name_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItem("Oracle", DatasourceType.ORACLE)
        self._type_combo.addItem("GeoJSON", DatasourceType.GEOJSON)
        self._type_combo.addItem("KML", DatasourceType.KML)
        self._type_combo.addItem("REST", DatasourceType.REST)
        form.addRow(QLabel("Type"), self._type_combo)

        self._config_edit = QTextEdit()
        self._config_edit.setLineWrapMode(TEXTEDIT_NO_WRAP)
        self._config_edit.setPlaceholderText("JSON connection configuration")

        layout.addLayout(form)
        layout.addWidget(QLabel("Connection Configuration (JSON)"))
        layout.addWidget(self._config_edit, stretch=1)

        button_bar = QHBoxLayout()
        button_bar.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        save_btn = QPushButton("Save")
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self.accept)
        button_bar.addWidget(cancel_btn)
        button_bar.addWidget(save_btn)
        layout.addLayout(button_bar)

    def _populate(self, datasource: Datasource) -> None:
        self._name_edit.setText(datasource.name)
        for index in range(self._type_combo.count()):
            if self._type_combo.itemData(index, USER_ROLE) == datasource.datasource_type:
                self._type_combo.setCurrentIndex(index)
                break
        # Exclude internal layer-config keys that belong to layer_config.json
        config_for_display = {
            k: v for k, v in datasource.config.items()
            if k not in ("tables",)
        }
        self._config_edit.setPlainText(json.dumps(config_for_display, indent=2))

    def get_payload(self) -> tuple[str, DatasourceType, dict[str, Any]]:
        name = self._name_edit.text().strip()
        if not name:
            raise ConfigurationException("Datasource name is required.")

        datasource_type = self._type_combo.currentData(USER_ROLE)
        try:
            config = json.loads(self._config_edit.toPlainText() or "{}")
        except json.JSONDecodeError as exc:
            raise ConfigurationException("Invalid datasource configuration JSON.") from exc

        if not isinstance(config, dict):
            raise ConfigurationException("Datasource configuration must be a JSON object.")

        return name, datasource_type, config

    def accept(self) -> None:
        try:
            _ = self.get_payload()
        except ConfigurationException as exc:
            QMessageBox.warning(self, "Datasource", str(exc))
            return
        super().accept()


