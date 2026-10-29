from __future__ import annotations

from collections.abc import Callable

from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout,
)

from geodata_catalog.exceptions import GeoDataCatalogException
from geodata_catalog.models.datasource import Datasource
from geodata_catalog.ui.geometry_toolbar import _enum


class DatabaseLoginDialog(QDialog):
    def __init__(
        self, datasources: list[Datasource], parent=None,
        saved_credentials: Callable[[Datasource], tuple[str, str] | None] | None = None,
        forget_credentials: Callable[[Datasource], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._saved_credentials = saved_credentials
        self._forget_credentials = forget_credentials
        self.setWindowTitle("Connect to database")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Log in once for all catalog layers on this database."))
        form = QFormLayout()
        self._database = QComboBox()
        for source in datasources:
            config = source.config
            self._database.addItem(
                f"{source.name} - {config.get('service_name', '')} "
                f"({config.get('host', '')}:{config.get('port', 1521)})",
                source,
            )
        self._username = QLineEdit()
        self._password = QLineEdit()
        self._password.setEchoMode(_enum(QLineEdit, "EchoMode", "Password"))
        self._remember = QCheckBox("Remember password (encrypted in QGIS)")
        self._database.currentIndexChanged.connect(self._on_database_changed)
        form.addRow("Database", self._database)
        form.addRow("Username", self._username)
        form.addRow("Password", self._password)
        layout.addLayout(form)
        layout.addWidget(self._remember)
        forget = QPushButton("Forget saved login for this database")
        forget.clicked.connect(self._on_forget_credentials)
        layout.addWidget(forget)
        layout.addWidget(QLabel(
            "Remembered credentials remain encrypted after disconnect; otherwise they are temporary.\n"
            "QGIS may ask for its authentication master password."
        ))
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        connect = QPushButton("Connect")
        connect.setDefault(True)
        cancel.clicked.connect(self.reject)
        connect.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(connect)
        layout.addLayout(buttons)
        self._on_database_changed()

    def _on_database_changed(self, *_args) -> None:
        source = self._database.currentData()
        self._username.setText(str(source.config.get("username", "")))
        self._password.clear()
        self._remember.setChecked(False)
        if self._saved_credentials is not None:
            try:
                credentials = self._saved_credentials(source)
            except GeoDataCatalogException as exc:
                QMessageBox.warning(self, "Saved database login", str(exc))
            else:
                if credentials is not None:
                    username, password = credentials
                    self._username.setText(username)
                    self._password.setText(password)
                    self._remember.setChecked(True)

    def _on_forget_credentials(self) -> None:
        if self._forget_credentials is not None:
            try:
                self._forget_credentials(self._database.currentData())
            except GeoDataCatalogException as exc:
                QMessageBox.warning(self, "Forget database login", str(exc))
                return
        self._password.clear()
        self._remember.setChecked(False)

    def remember_password(self) -> bool:
        return self._remember.isChecked()

    def credentials(self) -> tuple[Datasource, str, str]:
        return self._database.currentData(), self._username.text().strip(), self._password.text()

    def clear_password(self) -> None:
        self._password.clear()
