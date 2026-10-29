from __future__ import annotations

from collections.abc import Iterable

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


_ITEM_DATA_ROLE = getattr(Qt, "ItemDataRole", None)
USER_ROLE = getattr(Qt, "UserRole", None)
if USER_ROLE is None and _ITEM_DATA_ROLE is not None:
    USER_ROLE = _ITEM_DATA_ROLE.UserRole


class CatalogNavigation(QFrame):
    selection_changed = pyqtSignal(str)

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("catalogNavigation", True)
        self.setMinimumWidth(150)
        self.setMaximumWidth(230)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(8)
        heading = QLabel(title.upper())
        heading.setProperty("navigationHeading", True)
        layout.addWidget(heading)
        self.list_widget = QListWidget()
        self.list_widget.setProperty("navigationList", True)
        self.list_widget.setFrameShape(self._no_frame())
        self.list_widget.setHorizontalScrollBarPolicy(
            self._scroll_bar_policy("ScrollBarAlwaysOff")
        )
        self.list_widget.setTextElideMode(self._text_elide_mode("ElideRight"))
        self.list_widget.currentItemChanged.connect(self._emit_selection)
        layout.addWidget(self.list_widget, stretch=1)

    def set_entries(
        self,
        entries: Iterable[tuple[str, str, int, QIcon]],
        selected_key: str = "",
    ) -> None:
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        selected_item = None
        for key, label, count, icon in entries:
            item = QListWidgetItem(icon, f"{label}    {count}")
            item.setData(USER_ROLE, key)
            item.setToolTip(f"{label} ({count})")
            self.list_widget.addItem(item)
            if key == selected_key:
                selected_item = item
        if selected_item is None and self.list_widget.count():
            selected_item = self.list_widget.item(0)
        self.list_widget.setCurrentItem(selected_item)
        self.list_widget.blockSignals(False)

    def selected_key(self) -> str:
        item = self.list_widget.currentItem()
        return str(item.data(USER_ROLE) or "") if item is not None else ""

    def _emit_selection(self, item: QListWidgetItem | None) -> None:
        self.selection_changed.emit(
            str(item.data(USER_ROLE) or "") if item is not None else ""
        )

    @staticmethod
    def _no_frame():
        shape = getattr(QFrame, "Shape", None)
        if shape is not None:
            return shape.NoFrame
        return QFrame.NoFrame

    @staticmethod
    def _scroll_bar_policy(name: str):
        policy = getattr(Qt, "ScrollBarPolicy", None)
        if policy is not None:
            return getattr(policy, name)
        return getattr(Qt, name)

    @staticmethod
    def _text_elide_mode(name: str):
        mode = getattr(Qt, "TextElideMode", None)
        if mode is not None:
            return getattr(mode, name)
        return getattr(Qt, name)


class CollapsibleSection(QFrame):
    def __init__(self, title: str, content: QWidget, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("collapsibleSection", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.toggle = QToolButton()
        self.toggle.setProperty("sectionToggle", True)
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setToolButtonStyle(self._text_beside_icon())
        self.toggle.setArrowType(self._arrow("DownArrow"))
        self.toggle.clicked.connect(self._set_expanded)
        layout.addWidget(self.toggle)
        self.content = content
        layout.addWidget(content)

    def _set_expanded(self, expanded: bool) -> None:
        self.content.setVisible(expanded)
        self.toggle.setArrowType(
            self._arrow("DownArrow" if expanded else "RightArrow")
        )

    @staticmethod
    def _arrow(name: str):
        arrow_type = getattr(Qt, "ArrowType", None)
        if arrow_type is not None:
            return getattr(arrow_type, name)
        return getattr(Qt, name)

    @staticmethod
    def _text_beside_icon():
        style = getattr(Qt, "ToolButtonStyle", None)
        if style is not None:
            return style.ToolButtonTextBesideIcon
        return Qt.ToolButtonTextBesideIcon


def catalog_styles(ui_colors: dict[str, str]) -> str:
    primary = str(ui_colors.get("primary", "#59A947"))
    primary_text = str(ui_colors.get("primary_text", "#FFFFFF"))
    panel = str(ui_colors.get("panel_background", "#F7F9FC"))
    window = str(ui_colors.get("window_background", "#FFFFFF"))
    border = str(ui_colors.get("border", "#D7DEE8"))
    text = str(ui_colors.get("text", "#1E293B"))
    header = str(ui_colors.get("header_text", "#0F172A"))
    hover = str(ui_colors.get("hover_background", "#F3F9F4"))
    selected = str(ui_colors.get("selection_background", "#CFE8D1"))
    selected_text = str(ui_colors.get("selection_text", "#172A1B"))
    navigation_background = str(
        ui_colors.get("navigation_background", "#173D26")
    )
    navigation_text = str(ui_colors.get("navigation_text", "#F4F7F4"))
    return "\n".join(
        [
            f"QDockWidget {{ background: {window}; color: {text}; }}",
            f"QWidget {{ background: {window}; color: {text}; }}",
            f"QFrame[catalogNavigation='true'] {{ background: {navigation_background}; border: 0px; }}",
            f"QFrame[catalogNavigation='true'] QLabel {{ background: {navigation_background}; color: {navigation_text}; }}",
            "QLabel[navigationHeading='true'] { font-size: 10px; font-weight: 700; letter-spacing: 1px; }",
            f"QListWidget[navigationList='true'] {{ background: {navigation_background}; color: {navigation_text}; border: 0px; outline: 0; }}",
            f"QListWidget[navigationList='true']::item {{ color: {navigation_text}; min-height: 34px; padding: 3px 7px; border: 0px; }}",
            f"QListWidget[navigationList='true']::item:hover {{ background: {primary}; color: {primary_text}; }}",
            f"QListWidget[navigationList='true']::item:selected {{ background: {primary}; color: {primary_text}; border-left: 3px solid {selected}; }}",
            f"QFrame[collapsibleSection='true'] {{ background: {panel}; border-top: 1px solid {border}; }}",
            f"QToolButton[sectionToggle='true'] {{ background: {panel}; color: {header}; border: 0px; min-height: 34px; padding: 4px 8px; font-weight: 700; text-align: left; }}",
            f"QLineEdit, QComboBox {{ background: {window}; color: {text}; border: 1px solid {border}; border-radius: 4px; min-height: 30px; padding: 2px 8px; }}",
            f"QLineEdit:focus, QComboBox:focus {{ border-color: {primary}; }}",
            f"QPushButton {{ background: {window}; color: {text}; border: 1px solid {border}; border-radius: 4px; min-height: 30px; padding: 2px 12px; }}",
            f"QPushButton:hover, QToolButton:hover {{ border-color: {primary}; background: {hover}; }}",
            f"QPushButton:pressed {{ background: {primary}; color: {primary_text}; }}",
            f"QPushButton:disabled {{ color: {border}; background: {panel}; }}",
            f"QTreeWidget, QListWidget {{ background: {window}; color: {text}; border: 1px solid {border}; outline: 0; }}",
            "QTreeWidget::item, QListWidget::item { min-height: 30px; padding: 2px 6px; }",
            f"QTreeWidget::item:selected, QListWidget::item:selected {{ background: {selected}; color: {selected_text}; }}",
        ]
    )
