import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PyQt5.QtCore import QDate, QPoint, QSettings, Qt
from PyQt5.QtGui import QColor, QFont, QPalette, QPixmap
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from screens.maininterface import MainWindow, MealDialog
from screens.settingscreen import SettingsScreen
from screens.weekly_screen import ShoppingDialog
from services.application import configure_qt_plugins
from services.settings_service import SettingsService
from utilities.settings import AppSettings
from utilities.ingredients import Ingredient
from utilities.meal import MealData


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_qt_plugins()
        cls.app = QApplication.instance() or QApplication([])
        cls.default_font = QFont(cls.app.font())

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app.setFont(self.default_font)
        self.database_path = Path(self.directory.name) / "fagaki.db"
        self.settings_path = str(Path(self.directory.name) / "settings.ini")
        self.settings_service = SettingsService(QSettings(self.settings_path, QSettings.IniFormat))
        self.window = MainWindow(self.database_path, self.settings_service)
        self.addCleanup(self.window.close)

    def test_add_edit_and_delete_meal(self):
        def add(dialog):
            dialog.name_input.setText("Φακές")
            dialog.weekday_input.setCurrentIndex(dialog.weekday_input.findData(3))
            dialog.ingredients_input.setPlainText("φακές, νερό")
            dialog.recipe_input.setPlainText("Βράζουμε")
            dialog.fasting_input.setChecked(True)
            return QDialog.Accepted

        with patch.object(MealDialog, "exec_", add):
            self.window.add_meal()
        self.assertEqual(self.window.table.rowCount(), 1)
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            self.assertEqual(
                connection.execute(
                    "SELECT name, selectedday, ulika, isnistisimo, syntagi FROM fagaki"
                ).fetchone(),
                ("Φακές", None, "φακές, νερό", 1, "Βράζουμε"),
            )
            connection.execute(
                "UPDATE fagaki SET selectedday = '2026-03-04', imera_id = 3"
            )
            connection.execute(
                "INSERT INTO ulika (id, name, monada_metrisis) VALUES (1, 'Φακές', 'κιλό')"
            )
            connection.execute(
                "INSERT INTO fagaki_ulika (fagaki_id, ulika_id) SELECT id, 1 FROM fagaki"
            )

        self.window.table.selectRow(0)

        def edit(dialog):
            self.assertEqual(dialog.recipe_input.toPlainText(), "Βράζουμε")
            dialog.name_input.setText("Σούπα")
            dialog.recipe_input.setPlainText("Σιγοβράζουμε")
            dialog.fasting_input.setChecked(False)
            return QDialog.Accepted

        with patch.object(MealDialog, "exec_", edit):
            self.window.edit_meal()
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            self.assertEqual(
                connection.execute(
                    "SELECT name, selectedday, ulika, isnistisimo, syntagi, imera_id FROM fagaki"
                ).fetchone(),
                ("Σούπα", "2026-03-04", "φακές, νερό", 0, "Σιγοβράζουμε", 3),
            )

        self.window.table.selectRow(0)
        with patch.object(QMessageBox, "exec_", return_value=QMessageBox.No):
            self.window.delete_meal()
        self.assertEqual(self.window.table.rowCount(), 1)
        with patch.object(QMessageBox, "exec_", return_value=QMessageBox.Yes):
            self.window.delete_meal()
        self.assertEqual(self.window.table.rowCount(), 0)
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM fagaki").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM fagaki_ulika").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ulika").fetchone()[0], 1)

    def test_empty_name_is_rejected(self):
        dialog = MealDialog()
        dialog.name_input.setText("  ")
        with patch.object(QMessageBox, "warning") as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertNotEqual(dialog.result(), QDialog.Accepted)

    def test_recipe_requires_a_weekday(self):
        dialog = MealDialog()
        dialog.name_input.setText("Φακές")
        with patch.object(QMessageBox, "warning") as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertNotEqual(dialog.result(), QDialog.Accepted)
        dialog.weekday_input.setCurrentIndex(dialog.weekday_input.findData(3))
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(dialog.values().weekday_id, 3)

    def test_cancel_does_not_save(self):
        with patch.object(MealDialog, "exec_", return_value=QDialog.Rejected):
            self.window.add_meal()
        self.assertEqual(self.window.table.rowCount(), 0)

    def test_recipe_sorting_search_filter_and_selection(self):
        for name, day, fasting in (
            ("Φακές", 5, True), ("Κοτόπουλο", 1, False),
            ("Φασόλια", 3, True), ("Σούπα", 7, True),
        ):
            self.window.meal_service.add_meal(MealData(name, "", fasting, "", weekday_id=day))
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                "INSERT INTO fagaki (name, ulika, isnistisimo, imera_id) VALUES (?, '', 0, NULL)",
                ("Χωρίς",),
            )
        self.window.refresh()
        self.window.show()
        self.app.processEvents()
        table = self.window.table
        header = table.horizontalHeader()

        def click_header(column):
            point = QPoint(header.sectionViewportPosition(column) + header.sectionSize(column) // 2,
                           header.height() // 2)
            QTest.mouseClick(header.viewport(), Qt.LeftButton, pos=point)
            self.app.processEvents()

        def displayed():
            return [(table.item(row, 0).text(), table.item(row, 2).text())
                    for row in range(table.rowCount()) if not table.isRowHidden(row)]

        click_header(2)
        if header.sortIndicatorOrder() != Qt.AscendingOrder:
            click_header(2)
        self.assertEqual([day for _, day in displayed()],
                         ["Δευτέρα", "Τετάρτη", "Παρασκευή", "Κυριακή", "Χωρίς ημέρα"])
        click_header(2)
        self.assertEqual([day for _, day in displayed()],
                         ["Χωρίς ημέρα", "Κυριακή", "Παρασκευή", "Τετάρτη", "Δευτέρα"])
        click_header(0)
        names = [name for name, _ in displayed()]
        self.assertEqual(names, sorted(names, reverse=header.sortIndicatorOrder() == Qt.DescendingOrder))

        self.window.search_input.setText("ΦΑΚΕΣ")
        self.assertEqual([name for name, _ in displayed()], ["Φακές"])
        table.selectRow(next(row for row in range(table.rowCount()) if not table.isRowHidden(row)))
        self.window.day_filter.setCurrentIndex(self.window.day_filter.findData(3))
        self.assertEqual(displayed(), [])
        self.assertEqual(table.currentRow(), -1)
        self.window.search_input.setText("ΦΑΣ")
        self.assertEqual([name for name, _ in displayed()], ["Φασόλια"])
        click_header(2)
        self.assertEqual([name for name, _ in displayed()], ["Φασόλια"])
        self.window.refresh()
        self.assertEqual(self.window.day_filter.currentData(), 3)
        self.assertEqual([name for name, _ in displayed()], ["Φασόλια"])
        self.window.search_input.clear()
        self.window.day_filter.setCurrentIndex(self.window.day_filter.findData(0))
        self.assertEqual([name for name, _ in displayed()], ["Χωρίς"])
        self.window.day_filter.setCurrentIndex(self.window.day_filter.findData(None))
        self.assertEqual(len(displayed()), 5)
        self.window.search_input.setText("φα")
        for column in (0, 1, 2):
            click_header(column)
            self.assertEqual({name for name, _ in displayed()}, {"Φακές", "Φασόλια"})

        self.window.day_filter.setCurrentIndex(self.window.day_filter.findData(5))
        visible_row = next(row for row in range(table.rowCount()) if not table.isRowHidden(row))
        table.selectRow(visible_row)
        def edit(dialog):
            self.assertEqual(dialog.name_input.text(), "Φακές")
            dialog.name_input.setText("Φακές νέες")
            return QDialog.Accepted
        with patch.object(MealDialog, "exec_", edit):
            self.window.edit_meal()
        self.assertEqual([name for name, _ in displayed()], ["Φακές νέες"])

    def test_recipe_filter_retranslates_and_preserves_selection(self):
        self.window.meal_service.add_meal(MealData("Φακές", "", True, "", weekday_id=5))
        self.window.refresh()
        self.window.search_input.setText("φακ")
        self.window.day_filter.setCurrentIndex(self.window.day_filter.findData(5))
        self.window.table.selectRow(0)
        def edit_settings(dialog):
            dialog.language_input.setCurrentIndex(dialog.language_input.findData("en"))
            return QDialog.Accepted
        with patch.object(SettingsScreen, "exec_", edit_settings):
            self.window.open_settings()
        self.assertEqual(self.window.search_input.placeholderText(), "Search recipes")
        self.assertEqual(self.window.day_filter.currentText(), "Friday")
        self.assertEqual(self.window.day_filter.currentData(), 5)
        self.assertEqual(self.window.table.item(0, 2).text(), "Friday")
        self.assertFalse(self.window.table.isRowHidden(0))
        self.assertEqual(self.window.table.currentRow(), 0)

    def test_dialog_passes_trimmed_data_as_a_meal(self):
        dialog = MealDialog()
        dialog.name_input.setText(" Φακές ")
        dialog.ingredients_input.setPlainText(" φακές ")
        dialog.recipe_input.setPlainText(" Βράσιμο ")
        dialog.fasting_input.setChecked(True)
        self.assertEqual(dialog.values(), MealData("Φακές", "φακές", True, "Βράσιμο"))

    def test_database_errors_are_shown(self):
        with patch.object(self.window.meal_service, "list_meals",
                          side_effect=sqlite3.OperationalError("database error")):
            with patch.object(QMessageBox, "critical") as critical:
                self.window.refresh()
        critical.assert_called_once_with(self.window, "Σφάλμα βάσης δεδομένων", "database error")

    def test_button_colors_and_carrot_background_are_rendered(self):
        self.window.show()
        self.app.processEvents()
        buttons = [self.window.settings_button, self.window.add_button,
                   self.window.edit_button, self.window.delete_button]
        for button in buttons:
            button.setAttribute(Qt.WA_UnderMouse, False)
            image = button.grab().toImage()
            self.assertEqual(image.pixelColor(0, image.height() // 2).name(), "#55bde8")
            self.assertEqual(image.pixelColor(4, image.height() // 2).name(), "#f28c28")

        with_carrot = self.window.grab().toImage()
        self.window.tabs.widget(0).carrot = QPixmap()
        self.window.tabs.widget(0).update()
        self.app.processEvents()
        without_carrot = self.window.grab().toImage()
        changed_pixels = sum(
            with_carrot.pixel(x, y) != without_carrot.pixel(x, y)
            for y in range(0, with_carrot.height(), 4)
            for x in range(0, with_carrot.width(), 4)
        )
        self.assertGreater(changed_pixels, 100)

    def test_dialog_buttons_use_application_style(self):
        dialog = MealDialog(self.window)
        dialog.show()
        self.app.processEvents()
        buttons = dialog.findChildren(QPushButton)
        self.assertEqual(len(buttons), 4)
        for button in buttons:
            button.setAttribute(Qt.WA_UnderMouse, False)
            image = button.grab().toImage()
            self.assertEqual(image.pixelColor(0, image.height() // 2).name(), "#55bde8")
            self.assertEqual(image.pixelColor(4, image.height() // 2).name(), "#f28c28")
        dialog.close()

    def test_settings_apply_persist_and_translate(self):
        self.window.meal_service.add_meal(MealData("Φακές", "φακές", True, "Βράζουμε", weekday_id=1))
        self.window.refresh()
        self.window.table.selectRow(0)

        def edit_settings(dialog):
            with patch("style.styles.QColorDialog.getColor",
                       side_effect=[QColor("#345678"), QColor("#abcdef")]):
                dialog.choose_background()
                dialog.choose_font_color()
            dialog.font_size_input.setValue(16)
            dialog.language_input.setCurrentIndex(dialog.language_input.findData("en"))
            return QDialog.Accepted

        with patch.object(SettingsScreen, "exec_", edit_settings):
            self.window.settings_button.click()

        expected = AppSettings("#345678", "#abcdef", 16, "en")
        self.assertEqual(self.window.settings, expected)
        self.assertEqual(self.app.palette().color(QPalette.Window).name(), "#345678")
        self.assertEqual(self.app.palette().color(QPalette.WindowText).name(), "#abcdef")
        self.assertEqual(self.app.font().pointSize(), 16)
        self.assertEqual(self.window.title_label.font().pointSize(), 16)
        self.assertEqual(self.window.table.font().pointSize(), 16)
        self.assertEqual(self.window.table.horizontalHeader().font().pointSize(), 16)
        self.assertEqual(self.window.add_button.text(), "Add")
        self.assertEqual(self.window.tabs.tabText(0), "Recipes")
        self.assertEqual(self.window.tabs.tabText(1), "Weekly plan")
        self.assertEqual(self.window.weekly_screen.shopping_button.text(), "Let's go shopping")
        self.assertEqual(self.window.table.horizontalHeaderItem(0).text(), "Recipe")
        self.assertEqual(self.window.table.item(0, 1).text(), "Yes")
        self.assertEqual(self.window.table.currentRow(), 0)
        self.assertEqual(self.settings_service.load(10), expected)

        reloaded = MainWindow(self.database_path, SettingsService(
            QSettings(self.settings_path, QSettings.IniFormat)
        ))
        self.addCleanup(reloaded.close)
        self.assertEqual(reloaded.settings, expected)
        self.assertEqual(reloaded.add_button.text(), "Add")
        self.assertEqual(reloaded.table.item(0, 1).text(), "Yes")
        self.assertEqual(MealDialog(language="en").windowTitle(), "Recipe")

    def test_cancelled_settings_and_color_picker_leave_values_unchanged(self):
        before = self.window.settings

        def cancel_settings(dialog):
            with patch("style.styles.QColorDialog.getColor", return_value=QColor()):
                dialog.choose_background()
            self.assertEqual(dialog.background, before.background)
            dialog.font_size_input.setValue(20)
            return QDialog.Rejected

        with patch.object(SettingsScreen, "exec_", cancel_settings):
            self.window.open_settings()
        self.assertEqual(self.window.settings, before)
        self.assertEqual(self.settings_service.load(before.font_size), before)
        self.assertEqual(self.app.font().pointSize(), before.font_size)

    def test_settings_save_errors_are_shown_without_applying(self):
        before = self.window.settings
        with patch.object(SettingsScreen, "exec_", return_value=QDialog.Accepted):
            with patch.object(self.settings_service, "save", side_effect=OSError("disk error")):
                with patch.object(QMessageBox, "critical") as critical:
                    self.window.open_settings()
        critical.assert_called_once_with(self.window, "Σφάλμα ρυθμίσεων", "disk error")
        self.assertEqual(self.window.settings, before)

    def test_weekly_tabs_create_edit_and_copy_shopping_list(self):
        self.assertEqual(self.window.tabs.tabText(0), "Συνταγές")
        self.assertEqual(self.window.tabs.tabText(1), "Εβδομαδιαίο πρόγραμμα")

        def add(dialog):
            dialog.name_input.setText("Φακές")
            dialog.fasting_input.setChecked(True)
            dialog.weekday_input.setCurrentIndex(dialog.weekday_input.findData(1))
            editor = dialog.ingredient_editor
            editor.name_input.setEditText("Φακές")
            editor.unit_input.setCurrentIndex(editor.unit_input.findData("κιλό"))
            editor.quantity_input.setValue(0.5)
            editor.add_ingredient()
            return QDialog.Accepted

        with patch.object(MealDialog, "exec_", add):
            self.window.add_button.click()
        self.assertEqual(self.window.table.rowCount(), 1)
        meal = self.window.meal_service.get_meal(self.window.meal_service.list_meals()[0].id)
        self.assertEqual(meal.ingredient_items[0].quantity, 0.5)
        for day in range(2, 8):
            self.window.meal_service.add_meal(MealData(
                f"Φακές {day}", "", True, "",
                (Ingredient(None, "Φακές", "κιλό", 0.5),), day,
            ))

        self.window.tabs.setCurrentIndex(1)
        weekly = self.window.weekly_screen
        weekly.week_input.setDate(QDate(2026, 3, 4))
        weekly.create_button.click()
        self.assertEqual(weekly.table.rowCount(), 7)
        self.assertEqual(weekly.table.item(0, 1).text(), "02/03/2026")
        self.assertEqual(weekly.table.cellWidget(2, 2).currentText(), "Φακές 3")

        def check_shopping(dialog):
            self.assertEqual(dialog.list_text.toPlainText(), "Φακές: 3.5 κιλό")
            dialog.copy_button.click()
            self.assertEqual(self.app.clipboard().text(), "Φακές: 3.5 κιλό")
            self.assertTrue(dialog.status_label.text())
            return QDialog.Rejected

        with patch.object(ShoppingDialog, "exec_", check_shopping):
            weekly.shopping_button.click()

    def test_incomplete_legacy_ingredients_warn_before_shopping(self):
        self.window.meal_service.add_meal(MealData("Φακές", "φακές, νερό", True, "", weekday_id=1))
        for day in range(2, 8):
            self.window.meal_service.add_meal(MealData(
                f"Σούπα {day}", "", True, "",
                (Ingredient(None, "Φακές", "κιλό", 0.5),), day,
            ))
        self.window.refresh()
        self.window.weekly_screen.create_plan()
        with patch.object(QMessageBox, "warning") as warning:
            self.window.weekly_screen.show_shopping()
        self.assertIn("Φακές", warning.call_args.args[2])

        def complete(dialog):
            self.assertTrue(dialog.ingredients_input.isReadOnly())
            editor = dialog.ingredient_editor
            editor.name_input.setEditText("Φακές")
            editor.quantity_input.setValue(0.5)
            editor.unit_input.setCurrentIndex(editor.unit_input.findData("κιλό"))
            editor.add_ingredient()
            return QDialog.Accepted

        self.window.table.selectRow(next(
            row for row in range(self.window.table.rowCount())
            if self.window.table.item(row, 0).text() == "Φακές"
        ))
        with patch.object(MealDialog, "exec_", complete):
            self.window.edit_meal()
        self.assertEqual(self.window.weekly_screen.service.shopping_list()[0].quantity, 3.5)

    def test_new_ingredient_requires_explicit_quantity_and_unit(self):
        dialog = MealDialog()
        editor = dialog.ingredient_editor
        editor.name_input.setEditText("Φακές")
        with patch.object(QMessageBox, "warning") as warning:
            editor.add_ingredient()
        self.assertEqual(len(editor.items), 0)
        warning.assert_called_once()
        editor.quantity_input.setValue(0.5)
        with patch.object(QMessageBox, "warning") as warning:
            editor.add_ingredient()
        self.assertEqual(len(editor.items), 0)
        warning.assert_called_once()

    def test_existing_ingredient_allows_distinct_recipe_units(self):
        dialog = MealDialog(available_ingredients=[Ingredient(1, "Αλεύρι", "κιλό")])
        editor = dialog.ingredient_editor
        for unit in ("κιλό", "κ.σ."):
            editor.name_input.setCurrentIndex(0)
            editor.unit_input.setCurrentIndex(editor.unit_input.findData(unit))
            editor.quantity_input.setValue(2)
            editor.add_ingredient()
        self.assertEqual([(item.id, item.unit) for item in editor.items],
                         [(1, "κιλό"), (1, "κ.σ.")])
        editor.name_input.setCurrentIndex(0)
        editor.quantity_input.setValue(1)
        with patch.object(QMessageBox, "warning") as warning:
            editor.add_ingredient()
        warning.assert_called_once()

    def test_new_ingredient_does_not_inherit_the_previous_unit(self):
        dialog = MealDialog(available_ingredients=[Ingredient(1, "Φακές", "κιλό")])
        editor = dialog.ingredient_editor
        editor.name_input.setCurrentIndex(0)
        self.assertEqual(editor.unit_input.currentData(), "κιλό")
        editor.name_input.setEditText("Ρύζι")
        self.assertIsNone(editor.unit_input.currentData())

    def test_change_weekly_recipe_using_combobox(self):
        for day in range(1, 8):
            self.window.meal_service.add_meal(MealData(f"Α {day}", "", True, "", weekday_id=day))
        self.window.meal_service.add_meal(MealData("Β", "", True, "", weekday_id=1))
        self.window.weekly_screen.create_plan()
        combo = self.window.weekly_screen.table.cellWidget(0, 2)
        new_index = 1 - combo.currentIndex()
        expected_id = combo.itemData(new_index)
        combo.setCurrentIndex(new_index)
        self.assertEqual(self.window.weekly_screen.service.load().entries[0].meal_id, expected_id)

    def test_weekly_options_follow_database_day_and_display_changed_assignments(self):
        for day in range(1, 8):
            self.window.meal_service.add_meal(MealData(f"Α {day}", "", True, "", weekday_id=day))
        self.window.weekly_screen.create_plan()
        weekly = self.window.weekly_screen
        for row in range(7):
            combo = weekly.table.cellWidget(row, 2)
            self.assertEqual(combo.count(), 1)
            self.assertEqual(combo.currentText(), f"Α {row + 1}")
        day_one_id = weekly.service.load().entries[0].meal_id
        self.window.meal_service.update_meal(day_one_id, MealData("Α 1", "", True, "", weekday_id=2))
        weekly.refresh()
        combo = weekly.table.cellWidget(0, 2)
        self.assertIn("Μη διαθέσιμη", combo.currentText())
        with patch.object(QMessageBox, "warning") as warning:
            weekly.show_shopping()
        self.assertIn("ημέρα", warning.call_args.args[2])

    def test_weekday_names_are_loaded_from_database(self):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("UPDATE meres SET name = ? WHERE id = 1", ("Custom day",))
        for day in range(1, 8):
            self.window.meal_service.add_meal(MealData(f"Α {day}", "", True, "", weekday_id=day))
        self.window.refresh()
        self.window.weekly_screen.create_plan()
        self.assertEqual(self.window.weekly_screen.table.item(0, 0).text(), "Custom day")
        self.assertEqual(self.window.table.item(0, 2).text(), "Custom day")
        dialog = MealDialog(weekdays=self.window.meal_service.list_weekdays())
        self.assertEqual(dialog.weekday_input.itemText(dialog.weekday_input.findData(1)), "Custom day")

    def test_custom_background_and_text_colors_on_both_tabs(self):
        def edit_settings(dialog):
            dialog.background = "#345678"
            dialog.font_color = "#ffffff"
            return QDialog.Accepted

        with patch.object(SettingsScreen, "exec_", edit_settings):
            self.window.open_settings()
        self.window.show()
        for index, table in ((0, self.window.table), (1, self.window.weekly_screen.table)):
            self.window.tabs.setCurrentIndex(index)
            self.app.processEvents()
            point = table.viewport().mapTo(self.window, QPoint(10, 50))
            image = self.window.grab().toImage()
            self.assertEqual(image.pixelColor(point).name(), "#345678")
            header = table.horizontalHeader().grab().toImage()
            header_color = header.pixelColor(5, 5)
            self.assertLess(header_color.red(), 128)
            self.assertGreater(header_color.blue(), header_color.red())


if __name__ == "__main__":
    unittest.main()
