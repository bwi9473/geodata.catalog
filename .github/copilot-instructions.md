# Project Guidelines

## QGIS and Qt Compatibility

- Treat QGIS 4 with PyQt6 as the primary runtime for every Qt UI change.
- Preserve QGIS 3/PyQt5 compatibility when a simple compatibility path exists.
- Qt6 scoped enums must be resolved through their enum classes, for example `Qt.AlignmentFlag.AlignTop`, `QHeaderView.ResizeMode.Stretch`, and `Qt.ItemDataRole.UserRole`.
- Do not assume legacy unscoped Qt5 enum attributes exist. Use a small local compatibility resolver when code must run on both bindings.
- Validate changes that touch `qgis.PyQt` APIs against Qt6 enum, signal, dialog-execution, and header/view behavior before finishing.