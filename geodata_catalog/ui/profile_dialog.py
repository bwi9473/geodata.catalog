from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)

from geodata_catalog.models.user_profile import UserProfile
from geodata_catalog.ui.geometry_toolbar import _enum


class ProfileDialog(QDialog):
    """Edit user work profiles without touching layer styles or loading settings."""

    def __init__(
        self, profiles: list[UserProfile], layers: list[tuple[str, str]], parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("User profiles")
        self.resize(620, 560)
        self.profiles = [
            replace(profile, visible_layer_ids=(
                list(profile.visible_layer_ids) if profile.visible_layer_ids is not None else None
            )) for profile in profiles
        ]
        self._editing_id = ""
        self._known_layer_ids = {key for key, _label in layers}
        root = QVBoxLayout(self)
        hint = QLabel(
            "Profiles are freely selectable work modes, not access control. "
            "Developer always sees all layers. User profiles only show the data panel."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)
        row = QHBoxLayout()
        self.profile_combo = QComboBox()
        for profile in self.profiles:
            if not profile.is_developer:
                self.profile_combo.addItem(profile.name, profile.id)
        row.addWidget(self.profile_combo, stretch=1)
        add_button = QPushButton("Add user profile")
        add_button.clicked.connect(self._add_profile)
        row.addWidget(add_button)
        root.addLayout(row)
        self.name_edit = QLineEdit()
        root.addWidget(QLabel("Profile name"))
        root.addWidget(self.name_edit)
        self.all_layers = QCheckBox("All catalog layers (including future layers)")
        selection_row = QHBoxLayout()
        selection_row.addWidget(self.all_layers, stretch=1)
        uncheck_all = QPushButton("Uncheck all")
        uncheck_all.setToolTip(
            "Clear all layer selections for this profile, including layers not currently listed."
        )
        uncheck_all.clicked.connect(self._uncheck_all)
        selection_row.addWidget(uncheck_all)
        root.addLayout(selection_row)
        self.layers_list = QListWidget()
        for key, label in layers:
            item = QListWidgetItem(label)
            item.setData(_enum(Qt, "ItemDataRole", "UserRole"), key)
            item.setFlags(item.flags() | _enum(Qt, "ItemFlag", "ItemIsUserCheckable"))
            item.setCheckState(_enum(Qt, "CheckState", "Unchecked"))
            self.layers_list.addItem(item)
        root.addWidget(self.layers_list, stretch=1)
        self.all_layers.toggled.connect(lambda checked: self.layers_list.setEnabled(not checked))
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        self._on_profile_changed()

    def _uncheck_all(self) -> None:
        self.all_layers.setChecked(False)
        for index in range(self.layers_list.count()):
            self.layers_list.item(index).setCheckState(_enum(Qt, "CheckState", "Unchecked"))
        for profile in self.profiles:
            if profile.id == self._editing_id:
                profile.visible_layer_ids = []

    def _store_current(self) -> None:
        if not self._editing_id:
            return
        profile = next(profile for profile in self.profiles if profile.id == self._editing_id)
        profile.name = self.name_edit.text().strip()
        if self.all_layers.isChecked():
            profile.visible_layer_ids = None
        else:
            # Keep permissions for configured layers not currently discoverable.
            selected = set(profile.visible_layer_ids or []) - self._known_layer_ids
            for index in range(self.layers_list.count()):
                item = self.layers_list.item(index)
                if item.checkState() == _enum(Qt, "CheckState", "Checked"):
                    selected.add(item.data(_enum(Qt, "ItemDataRole", "UserRole")))
            profile.visible_layer_ids = sorted(selected)

    def _on_profile_changed(self, _index: int = 0) -> None:
        self._store_current()
        self._editing_id = self.profile_combo.currentData()
        profile = next((profile for profile in self.profiles if profile.id == self._editing_id), None)
        if profile is None:
            return
        self.name_edit.setText(profile.name)
        self.all_layers.setChecked(profile.visible_layer_ids is None)
        self.layers_list.setEnabled(profile.visible_layer_ids is not None)
        for index in range(self.layers_list.count()):
            item = self.layers_list.item(index)
            key = item.data(_enum(Qt, "ItemDataRole", "UserRole"))
            item.setCheckState(_enum(Qt, "CheckState", "Checked" if profile.can_view(key) else "Unchecked"))

    def _add_profile(self) -> None:
        name, accepted = QInputDialog.getText(self, "Add user profile", "Profile name:")
        if accepted and name.strip():
            profile = UserProfile(str(uuid4()), name.strip(), visible_layer_ids=[])
            self.profiles.append(profile)
            self.profile_combo.addItem(profile.name, profile.id)
            self.profile_combo.setCurrentIndex(self.profile_combo.count() - 1)

    def accept(self) -> None:
        self._store_current()
        if any(not profile.name for profile in self.profiles):
            QMessageBox.warning(self, "User profiles", "Every profile needs a name.")
            return
        super().accept()
