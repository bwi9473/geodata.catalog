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

DATASOURCE_CONFIG_TEMPLATES: dict[DatasourceType, dict[str, Any]] = {
    DatasourceType.ORACLE: {
        "host": "oracle.example.com",
        "port": 1521,
        "service_name": "ORCLCDB",
        "username": "",
        "password": "",
        "schema": "",
    },
    DatasourceType.GEOJSON: {
        "path": "C:/GIS/data/dataset.geojson",
    },
    DatasourceType.KML: {
        "path": "C:/GIS/data/dataset.kml",
    },
    DatasourceType.REST: {
        "url": "https://api.example.com/dataset.geojson",
        "auth_type": "none",
        "headers": {},
        "query_params": {},
    },
}


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
        self._updating_type = False
        self._selected_type_index = 0
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
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)

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

        self._set_config_template(self._type_combo.currentData(USER_ROLE))

    def _on_type_changed(self, _index: int) -> None:
        if self._updating_type:
            return
        previous_index = self._selected_type_index
        existing_config = self._config_edit.toPlainText().strip()
        if self._datasource is not None and existing_config:
            standard_button = getattr(QMessageBox, "StandardButton", QMessageBox)
            yes_button = standard_button.Yes
            no_button = standard_button.No
            response = QMessageBox.warning(
                self,
                "Replace Configuration",
                "Changing the datasource type will replace the existing JSON configuration. Continue?",
                yes_button | no_button,
                no_button,
            )
            if response != yes_button:
                self._updating_type = True
                self._type_combo.setCurrentIndex(previous_index)
                self._updating_type = False
                return
        self._selected_type_index = self._type_combo.currentIndex()
        self._set_config_template(self._type_combo.currentData(USER_ROLE))

    def _set_config_template(self, datasource_type: DatasourceType) -> None:
        template = DATASOURCE_CONFIG_TEMPLATES.get(datasource_type, {})
        self._config_edit.setPlainText(json.dumps(template, indent=2))

    def _populate(self, datasource: Datasource) -> None:
        self._name_edit.setText(datasource.name)
        self._updating_type = True
        for index in range(self._type_combo.count()):
            if self._type_combo.itemData(index, USER_ROLE) == datasource.datasource_type:
                self._type_combo.setCurrentIndex(index)
                self._selected_type_index = index
                break
        self._updating_type = False
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


