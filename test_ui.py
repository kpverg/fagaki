import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from ui import MainWindow, MealDialog


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database_path = Path(self.directory.name) / "fagaki.db"
        self.window = MainWindow(self.database_path)
        self.addCleanup(self.window.close)

    def test_add_edit_and_delete_meal(self):
        def add(dialog):
            dialog.name_input.setText("Φακές")
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
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            self.window.delete_meal()
        self.assertEqual(self.window.table.rowCount(), 1)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
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

    def test_cancel_does_not_save(self):
        with patch.object(MealDialog, "exec_", return_value=QDialog.Rejected):
            self.window.add_meal()
        self.assertEqual(self.window.table.rowCount(), 0)


if __name__ == "__main__":
    unittest.main()
