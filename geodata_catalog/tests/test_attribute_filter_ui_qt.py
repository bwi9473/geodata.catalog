"""Real Qt UI regressions; run with QGIS Python and unittest, without QGIS stubs."""
from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

try:
    from qgis.core import QgsApplication
except ImportError:
    QgsApplication = None


@unittest.skipIf(QgsApplication is None, "Requires a real QGIS Qt runtime")
class AttributeFilterUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = TemporaryDirectory(prefix="geodata-filter-ui-")
        cls.owns_app = QgsApplication.instance() is None
        cls.app = QgsApplication.instance() or QgsApplication([], False, cls.profile.name)
        if cls.owns_app:
            cls.app.initQgis()

    @classmethod
    def tearDownClass(cls):
        if cls.owns_app:
            cls.app.exitQgis()
        cls.profile.cleanup()

    def setUp(self):
        from geodata_catalog.ui.layer_custom_view_dock import LayerCustomViewWindow

        self.window = LayerCustomViewWindow(
            searchable_columns=[
                *[
                    {"name": name, "input_type": "checkbox"}
                    for name in ("BRU", "DEC", "HAN", "MIL", "YEN", "YBA", "C_TSA_DANGER_GRID")
                ],
                {"name": "AREA_ID", "input_type": "text field", "use_distinct": True},
                {"name": "TSA_APPLICABILITY", "input_type": "dropdown", "filter_by": "AREA_ID"},
                {"name": "SHAPE", "input_type": "dropdown"},
            ],
            distinct_values={
                "AREA_ID": ["A", "B"], "TSA_APPLICABILITY": ["one", "two"],
                "SHAPE": ["circle"],
                "BRU": ["y", "n"],
            },
            filtered_distinct_values={"TSA_APPLICABILITY": {"A": ["one"], "B": ["two"]}},
            show_flight_level=False,
        )
        self.window.resize(1000, 750)
        self.window.show()
        self.app.processEvents()
        self.window._refresh_attribute_fields()
        self.app.processEvents()

    def tearDown(self):
        try:
            self.window.close()
        except RuntimeError:
            pass
        self.app.processEvents()

    def test_text_and_dropdown_fields_precede_compact_inline_checkboxes(self):
        from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel

        window = self.window
        self.assertEqual([name for name, _ in window._attribute_fields],
                         ["AREA_ID", "TSA_APPLICABILITY", "SHAPE"])
        last_field_bottom = max(
            cell.mapToGlobal(cell.rect().bottomLeft()).y()
            for _, cell in window._attribute_fields
        )
        first_check = window._checkbox_fields[0][1]
        self.assertGreater(first_check.mapToGlobal(first_check.rect().topLeft()).y(),
                           last_field_bottom)
        self.assertIsInstance(first_check.layout(), QHBoxLayout)
        self.assertIsInstance(first_check.layout().itemAt(1).widget(), QLabel)
        first_x = first_check.mapToGlobal(first_check.rect().topLeft()).x()
        second = window._checkbox_fields[1][1]
        second_x = second.mapToGlobal(second.rect().topLeft()).x()
        self.assertLess(second_x - first_x, 200)
        self.assertGreater(second_x, first_x)
        window._attr_checks["BRU"].click()
        self.assertIn(window._checkbox_filter_value("BRU", window._attr_checks["BRU"]), ("y", "n"))
        original_columns = window._attribute_layout_key[0]
        window.resize(450, 750)
        self.app.processEvents()
        window._refresh_attribute_fields()
        columns = window._attribute_layout_key[0]
        self.assertLess(columns, original_columns)
        self.assertEqual(window._attribute_grid.getItemPosition(2)[:2], (2 // columns, 2 % columns))

    def test_lov_is_an_embedded_list_action_not_a_label_button(self):
        from qgis.PyQt.QtWidgets import QPushButton

        edit = self.window._attr_edits["AREA_ID"]
        action, = edit.actions()
        self.assertFalse(action.icon().isNull())
        self.assertIn("LOV", action.toolTip())
        self.assertFalse(any(button.text() == "LOV" for button in self.window.findChildren(QPushButton)))
        with patch.object(self.window, "_open_lov_selector") as open_lov:
            action.trigger()
            open_lov.assert_called_once_with("AREA_ID", "AREA_ID")

    def test_lov_dialog_accepts_multiple_values_and_cancel_preserves_text(self):
        from qgis.PyQt.QtCore import QTimer
        from qgis.PyQt.QtWidgets import QApplication, QDialogButtonBox, QListWidget
        from geodata_catalog.ui.layer_custom_view_dock import _qt_enum_value

        edit = self.window._attr_edits["AREA_ID"]
        errors = []

        def accept_values():
            dialog = QApplication.activeModalWidget()
            try:
                values = dialog.findChild(QListWidget)
                values.item(0).setSelected(True)
                values.item(1).setSelected(True)
                buttons = dialog.findChild(QDialogButtonBox)
                buttons.button(_qt_enum_value(QDialogButtonBox, "StandardButton", "Ok")).click()
            except Exception as exc:
                errors.append(exc)
                dialog.reject()

        QTimer.singleShot(0, accept_values)
        self.window._open_lov_selector("AREA_ID", "Area")
        self.assertEqual(errors, [])
        self.assertEqual(edit.text(), "A, B")
        QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
        self.window._open_lov_selector("AREA_ID", "Area")
        self.assertEqual(edit.text(), "A, B")

    def test_lov_parent_updates_dropdown_options_and_preserves_manual_input(self):
        parent = self.window._attr_edits["AREA_ID"]
        child = self.window._attr_combos["TSA_APPLICABILITY"]
        child.setEditText("manual")
        parent.setText("A")
        self.assertEqual([child.itemText(i) for i in range(child.count())], ["one"])
        self.assertEqual(child.currentText(), "manual")
        parent.setText("A, B")
        self.assertEqual([child.itemText(i) for i in range(child.count())], ["one", "two"])

    def test_invalid_checkbox_values_render_as_dropdown_with_warning(self):
        from geodata_catalog.ui.layer_custom_view_dock import LayerCustomViewWindow
        from unittest.mock import Mock

        logger = Mock()
        other = LayerCustomViewWindow(
            searchable_columns=[{"name": "STATE", "input_type": "checkbox"}],
            distinct_values={"STATE": ["open", "closed"]},
            show_flight_level=False, logger=logger,
        )
        try:
            self.assertIn("STATE", other._attr_combos)
            self.assertNotIn("STATE", other._attr_checks)
            logger.warning.assert_called_once()
        finally:
            other.close()

    def test_dropdown_arrow_and_lov_icons_are_distinct_loadable_resources(self):
        from pathlib import Path
        from qgis.PyQt.QtGui import QIcon
        from geodata_catalog.ui import layer_custom_view_dock

        resources = Path(layer_custom_view_dock.__file__).parent.parent / "resources"
        arrow = resources / "filter_dropdown.svg"
        self.assertFalse(QIcon(str(arrow)).pixmap(12, 12).isNull())
        self.assertFalse(QIcon(str(resources / "filter_lov.svg")).pixmap(18, 18).isNull())
        self.assertIn(arrow.as_posix(), self.window.styleSheet())
        self.assertIn("::down-arrow", self.window.styleSheet())

    def test_reset_sits_next_to_search_and_save_is_removed(self):
        from qgis.PyQt.QtWidgets import QPushButton

        window = self.window
        texts = [button.text() for button in window._filter_panel.findChildren(QPushButton)]
        self.assertNotIn("Save", texts)
        self.assertFalse(hasattr(window, "_save_btn"))
        self.assertIsNone(window._filter_tabs.cornerWidget())
        reset, search = window._reset_btn, window._search_btn
        self.assertIs(reset.parentWidget(), search.parentWidget())
        reset_pos = reset.mapTo(window, reset.rect().topLeft())
        search_pos = search.mapTo(window, search.rect().topLeft())
        self.assertEqual(reset_pos.y(), search_pos.y())
        self.assertLess(reset_pos.x(), search_pos.x())
        self.assertGreater(reset_pos.y(), window._filter_tabs.mapTo(window, window._filter_tabs.rect().bottomLeft()).y())

    def test_column_header_click_sorts_like_explorer(self):
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtWidgets import QComboBox, QPushButton
        from geodata_catalog.ui.layer_custom_view_dock import LayerCustomViewWindow, _qt_enum_value

        other = LayerCustomViewWindow(
            columns=[
                {"name": "NAME", "label": "Name", "type": "varchar"},
                {"name": "VERSION_NR", "label": "Version", "type": "numeric"},
            ],
            records=[
                {"__fid": 1, "NAME": "bravo", "VERSION_NR": 10},
                {"__fid": 2, "NAME": "Alpha", "VERSION_NR": 9},
                {"__fid": 3, "NAME": "charlie", "VERSION_NR": 100},
            ],
            show_flight_level=False,
        )
        try:
            other.show()
            self.app.processEvents()
            header = other._table.horizontalHeader()
            ascending = _qt_enum_value(Qt, "SortOrder", "AscendingOrder")
            descending = _qt_enum_value(Qt, "SortOrder", "DescendingOrder")

            def column(idx):
                return [other._table.item(row, idx).text() for row in range(other._table.rowCount())]

            self.assertTrue(header.isSortIndicatorShown())
            self.assertEqual((header.sortIndicatorSection(), header.sortIndicatorOrder()), (1, ascending))
            self.assertEqual(column(1), ["Alpha", "bravo", "charlie"])

            header.sectionClicked.emit(2)
            self.assertEqual(column(2), ["9", "10", "100"])
            self.assertEqual((header.sortIndicatorSection(), header.sortIndicatorOrder()), (2, ascending))
            header.sectionClicked.emit(2)
            self.assertEqual(column(2), ["100", "10", "9"])
            self.assertEqual(header.sortIndicatorOrder(), descending)
            header.sectionClicked.emit(1)
            self.assertEqual(column(1), ["Alpha", "bravo", "charlie"])
            header.sectionClicked.emit(1)
            self.assertEqual(column(1), ["charlie", "bravo", "Alpha"])
            header.sectionClicked.emit(0)
            self.assertEqual((header.sortIndicatorSection(), header.sortIndicatorOrder()), (1, descending))

            self.assertFalse(hasattr(other, "_sort_column_combo"))
            self.assertNotIn("Apply", [b.text() for b in other.findChildren(QPushButton)])
            self.assertFalse(any(c.findText("Ascending") >= 0 for c in other.findChildren(QComboBox)))
        finally:
            other.close()

    def test_attributes_tab_is_first_and_flight_levels_second(self):
        tabs = self.window._filter_tabs
        self.assertEqual(tabs.count(), 2)
        self.assertEqual(tabs.currentIndex(), 0)
        self.assertIs(tabs.widget(0), self.window._attr_scroll_area)
        self.assertEqual(tabs.tabText(0), "Attributes (off)")
        self.assertEqual(tabs.tabText(1), "Flight Levels (not available)")
        self.assertFalse(tabs.isTabEnabled(1))
        self.window._attr_edits["AREA_ID"].setText("A")
        self.assertEqual(tabs.tabText(0), "Attributes (active)")
        self.assertEqual(self.window._filter_panel.title(), "Filter - 1 active")

    def test_flight_level_tab_keeps_status_and_controls(self):
        from geodata_catalog.ui.layer_custom_view_dock import LayerCustomViewWindow

        other = LayerCustomViewWindow(
            searchable_columns=[{"name": "AREA_ID", "input_type": "text field"}],
            show_flight_level=True,
        )
        try:
            tabs = other._filter_tabs
            self.assertEqual(tabs.currentIndex(), 0)
            self.assertTrue(tabs.isTabEnabled(1))
            self.assertEqual(tabs.tabText(1), "Flight Levels (off)")
            self.assertTrue(tabs.widget(1).isAncestorOf(other._enabled_check))
            other._enabled_check.setChecked(True)
            self.assertEqual(tabs.tabText(1), "Flight Levels (FL000 - 600)")
            other._fl_range_slider.setValues(365, 999)
            self.assertEqual(tabs.tabText(1), "Flight Levels (FL365 - 999)")
            other._lower_spin.setValue(95)
            other._upper_spin.setValue(355)
            self.assertEqual(tabs.tabText(1), "Flight Levels (FL095 - 355)")
            with patch.object(other, "_on_search_clicked"):
                other._preset_buttons[-1][0].click()
            self.assertEqual(tabs.tabText(1), "Flight Levels (FL000 - 999)")
            other._enabled_check.setChecked(False)
            self.assertEqual(tabs.tabText(1), "Flight Levels (off)")
            other._fl_range_slider.setValues(100, 400)
            self.assertEqual(tabs.tabText(1), "Flight Levels (off)")
            other._enabled_check.setChecked(True)
            self.assertEqual(tabs.tabText(1), "Flight Levels (FL100 - 400)")
        finally:
            other.close()

    def _fl_window(self, mode="none", enabled=False, lower=0, upper=600):
        from geodata_catalog.services.layer_filter_service import FlightLevelFilter, LayerFilter
        from geodata_catalog.ui.layer_custom_view_dock import LayerCustomViewWindow

        return LayerCustomViewWindow(
            searchable_columns=[{"name": "AREA_ID", "input_type": "text field"}],
            show_flight_level=True,
            initial_filter=LayerFilter(
                flight_level=FlightLevelFilter(mode=mode, lower=lower, upper=upper, enabled=enabled),
            ),
        )

    def test_flight_level_match_modes_are_side_by_side_radios_with_info(self):
        from geodata_catalog.services.layer_filter_service import LayerFilterService as S

        other = self._fl_window()
        try:
            other.resize(1000, 750)
            other.show()
            other._filter_tabs.setCurrentIndex(1)
            self.app.processEvents()
            modes = [S.MODE_OVERLAPS, S.MODE_WITHIN, S.MODE_COVERS]
            radios = [other._fl_mode_buttons[m] for m in modes]
            self.assertEqual([r.text() for r in radios], ["Overlaps", "Fully within", "Covers"])
            self.assertTrue(radios[0].isChecked())
            ys = {r.mapTo(other, r.rect().center()).y() for r in radios}
            xs = [r.mapTo(other, r.rect().topLeft()).x() for r in radios]
            self.assertEqual(len(ys), 1)
            self.assertEqual(xs, sorted(xs))

            # Disabled while the flight level filter is off.
            self.assertFalse(any(r.isEnabled() for r in radios))
            self.assertFalse(any(b.isEnabled() for b in other._fl_mode_info_buttons.values()))
            other._enabled_check.setChecked(True)
            self.assertTrue(all(r.isEnabled() for r in radios))

            other._lower_spin.setValue(0)
            other._upper_spin.setValue(355)
            for mode in modes:
                info = other._fl_mode_info_buttons[mode]
                self.assertTrue(info.autoRaise())
                self.assertFalse(info.icon().isNull())
                with patch("geodata_catalog.ui.layer_custom_view_dock.QMessageBox.information") as info_box:
                    info.click()
                info_box.assert_called_once()
                title, text = info_box.call_args.args[1:3]
                self.assertIn(other._fl_mode_buttons[mode].text(), title)
                self.assertIn("FL0–FL355", text)
            overlaps_text = other._fl_mode_explanation(S.MODE_OVERLAPS, 0, 355)
            within_text = other._fl_mode_explanation(S.MODE_WITHIN, 0, 355)
            self.assertIn("Zone FL45–FL999 → shown", overlaps_text)
            self.assertIn("Zone FL45–FL999 → not shown", within_text)

            radios[1].setChecked(True)
            self.assertEqual(other._current_filter().flight_level.mode, S.MODE_WITHIN)
            radios[2].setChecked(True)
            self.assertEqual(other._current_filter().flight_level.mode, S.MODE_COVERS)
            other._enabled_check.setChecked(False)
            self.assertEqual(other._current_filter().flight_level.mode, S.MODE_NONE)

            with patch.object(other, "_on_search_clicked"):
                other._on_reset_filters()
            self.assertTrue(radios[0].isChecked())
        finally:
            other.close()

    def test_flight_level_match_mode_is_restored_from_initial_filter(self):
        from geodata_catalog.services.layer_filter_service import LayerFilterService as S

        for mode, expected in (
            (S.MODE_WITHIN, S.MODE_WITHIN),
            (S.MODE_COVERS, S.MODE_COVERS),
            (S.MODE_BETWEEN, S.MODE_OVERLAPS),
            (S.MODE_ABOVE, S.MODE_OVERLAPS),
            (S.MODE_BELOW, S.MODE_OVERLAPS),
        ):
            with self.subTest(mode=mode):
                other = self._fl_window(mode=mode, enabled=True, lower=0, upper=355)
                try:
                    self.assertTrue(other._fl_mode_buttons[expected].isChecked())
                    self.assertEqual(other._current_filter().flight_level.mode, expected)
                finally:
                    other.close()

    def test_flight_level_slider_syncs_exact_bounds_and_presets(self):
        other = self._fl_window(enabled=True, lower=95, upper=355)
        try:
            slider = other._fl_range_slider
            self.assertEqual((slider.lowerValue(), slider.upperValue()), (95, 355))
            self.assertEqual(other._filter_tabs.tabText(1), "Flight Levels (FL095 - 355)")
            slider.setValues(120, 400)
            self.assertEqual((other._lower_spin.value(), other._upper_spin.value()), (120, 400))
            other._lower_spin.setValue(450)
            self.assertEqual((slider.lowerValue(), slider.upperValue()), (450, 450))
            other._upper_spin.setValue(95)
            self.assertEqual((slider.lowerValue(), slider.upperValue()), (95, 95))

            self.assertEqual([button.text() for button, _, _ in other._preset_buttons],
                             ["LOWER", "HIGH", "ALL"])
            for button, lower, upper in other._preset_buttons:
                with patch.object(other, "_on_search_clicked") as search:
                    button.click()
                search.assert_called_once()
                self.assertEqual((slider.lowerValue(), slider.upperValue()), (lower, upper))
                self.assertTrue(button.isChecked())
                self.assertEqual(sum(item.isChecked() for item, _, _ in other._preset_buttons), 1)
            with patch.object(other, "_on_search_clicked") as search:
                other._on_reset_filters()
            self.assertEqual((slider.lowerValue(), slider.upperValue()), (0, 600))
            self.assertFalse(slider.isEnabled())
            self.assertFalse(any(button.isEnabled() for button, _, _ in other._preset_buttons))
        finally:
            other.close()

    def test_flight_level_slider_mouse_and_keyboard_apply_on_release(self):
        from qgis.PyQt.QtCore import QPoint, Qt
        from qgis.PyQt.QtTest import QTest

        other = self._fl_window(enabled=True, lower=0, upper=0)
        try:
            other.show()
            other._filter_tabs.setCurrentIndex(1)
            self.app.processEvents()
            slider = other._fl_range_slider
            target = QPoint(slider._value_to_pos(355), 34)
            with patch.object(other, "_on_search_clicked") as search:
                QTest.mousePress(slider, Qt.MouseButton.LeftButton, pos=target)
                search.assert_not_called()
                QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=target)
            search.assert_called_once()
            self.assertEqual(slider.lowerValue(), 0)
            self.assertLessEqual(abs(slider.upperValue() - 355), 3)

            slider.setValues(95, 355)
            with patch.object(other, "_on_search_clicked") as search:
                QTest.keyClick(slider, Qt.Key.Key_Right)
            search.assert_called_once()
            self.assertEqual((slider.lowerValue(), slider.upperValue()), (95, 356))
            QTest.keyClick(slider, Qt.Key.Key_Space)
            with patch.object(other, "_on_search_clicked"):
                QTest.keyClick(slider, Qt.Key.Key_Right)
            self.assertEqual((slider.lowerValue(), slider.upperValue()), (96, 356))
        finally:
            other.close()

    def test_flight_level_controls_fit_compact_horizontal_layout(self):
        other = self._fl_window(enabled=True, lower=95, upper=355)
        try:
            other.show()
            other._filter_tabs.setCurrentIndex(1)
            for width in (450, 1000):
                with self.subTest(width=width):
                    other.resize(width, 750)
                    self.app.processEvents()
                    slider = other._fl_range_slider
                    group = other._flight_group
                    self.assertLess(group.height(), 250)
                    self.assertGreater(slider.width(), 200)
                    self.assertEqual(other._lower_spin.y(), other._upper_spin.y())
                    self.assertLess(other._lower_spin.geometry().right(), other._upper_spin.x())
                    self.assertTrue(group.rect().contains(slider.geometry()))
                    self.assertFalse(slider.grab().toImage().isNull())
        finally:
            other.close()

    def test_flight_level_dialog_uses_same_bounds_and_presets(self):
        from geodata_catalog.ui.layer_filter_dialog import LayerFilterDialog

        other = LayerFilterDialog(flight_level_presets=[
            {"name": "LOWER", "lower": 0, "upper": 355},
            {"name": "HIGH", "lower": 355, "upper": 999},
            {"name": "ENROUTE", "lower": 95, "upper": 355},
        ])
        try:
            self.assertEqual([button.text() for button, _, _ in other._preset_buttons],
                             ["LOWER", "HIGH", "ALL"])
            other._fl_range_slider.setValues(95, 355)
            self.assertEqual((other._lower_spin.value(), other._upper_spin.value()), (95, 355))
            other._upper_spin.setValue(80)
            self.assertEqual((other._fl_range_slider.lowerValue(), other._fl_range_slider.upperValue()),
                             (80, 80))
            with patch.object(other, "_on_apply") as apply_filter:
                other._preset_buttons[-1][0].click()
            apply_filter.assert_called_once()
            self.assertEqual((other._lower_spin.value(), other._upper_spin.value()), (0, 999))
        finally:
            other.close()

    def test_attribute_block_fits_without_scrollbar_on_open(self):
        from geodata_catalog.ui.layer_custom_view_dock import LayerCustomViewWindow

        other = LayerCustomViewWindow(
            searchable_columns=[
                *[{"name": f"TEXT_{i}", "input_type": "text field"} for i in range(12)],
                *[{"name": f"CHECK_{i}", "input_type": "checkbox"} for i in range(8)],
            ],
            show_flight_level=True,
        )
        try:
            initial_filter_height = other._splitter.sizes()[0]
            other.show()
            for _ in range(5):
                self.app.processEvents()
            scroll = other._attr_scroll_area
            self.assertGreater(other._splitter.sizes()[0], initial_filter_height)
            self.assertFalse(scroll.verticalScrollBar().isVisible())
            self.assertGreaterEqual(other._splitter.sizes()[1], 240)
        finally:
            other.close()

    def test_results_can_be_detached_and_reattached(self):
        window = self.window
        results = window._results_widget
        sizes_before = window._splitter.sizes()
        self.assertEqual(window._splitter.count(), 2)
        self.assertEqual(window._detach_results_btn.text(), "Detach results")

        window._detach_results_btn.click()
        self.app.processEvents()
        self.assertTrue(window.is_results_detached())
        self.assertEqual(window._splitter.count(), 1)
        detached = window._results_window
        self.assertTrue(detached.isWindow())
        self.assertTrue(detached.isVisible())
        self.assertIs(results.window(), detached)
        self.assertEqual(window._detach_results_btn.text(), "Attach to filter")

        window._detach_results_btn.click()
        self.app.processEvents()
        self.assertFalse(window.is_results_detached())
        self.assertEqual(window._splitter.count(), 2)
        self.assertIs(window._splitter.widget(1), results)
        self.assertEqual(window._splitter.sizes(), sizes_before)
        self.assertEqual(window._detach_results_btn.text(), "Detach results")

    def test_closing_detached_results_window_reattaches(self):
        window = self.window
        window._detach_results()
        self.app.processEvents()
        window._results_window.close()
        self.app.processEvents()
        self.assertFalse(window.is_results_detached())
        self.assertIs(window._splitter.widget(1), window._results_widget)

    def test_closing_main_window_closes_detached_results(self):
        window = self.window
        window._detach_results()
        detached = window._results_window
        self.app.processEvents()
        window.close()
        self.assertIsNone(window._results_window)
        self.assertFalse(detached.isVisible())

    def test_configuration_migrates_distinct_to_lov_and_saves_without_distinct(self):
        from geodata_catalog.metadata.layer_config_repository import LayerConfig
        from geodata_catalog.ui.layer_config_dialog import LayerConfigDialog

        config = LayerConfig("ds", "layer", field_columns=[
            {"name": "AREA_ID", "input_type": "text field", "use_distinct": True, "search": True},
            {"name": "SHAPE", "input_type": "dropdown", "search": True, "filter_by": "AREA_ID"},
        ])
        dialog = LayerConfigDialog(
            existing_config=config,
            available_fields=[{"name": "AREA_ID"}, {"name": "SHAPE"}],
        )
        try:
            table = dialog._fields_table
            self.assertEqual(table.columnCount(), 9)
            self.assertEqual(table.horizontalHeaderItem(8).text(), "Filter By")
            self.assertEqual(table.cellWidget(0, 3).currentText(), "LOV")
            columns = dialog._field_columns_from_table()
            self.assertEqual(columns[0]["input_type"], "lov")
            self.assertEqual(columns[1]["filter_by"], "AREA_ID")
            self.assertTrue(all("use_distinct" not in column for column in columns))
            dialog._on_attribute_header_clicked(8)
            self.assertEqual(table.cellWidget(1, 8).currentText(), "AREA_ID")
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
