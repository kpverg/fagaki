import os
import re
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QPainter, QTextDocument
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtWidgets import QApplication

from screens.weekly_screen import ShoppingDialog
from utilities.ingredients import ShoppingItem
from utilities.weekly_export import export_shopping_list_pdf
from utilities.weekly_plan import WeeklyPlan


class ShoppingListPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_list_fits_one_page_with_all_items(self):
        for count in (0, 8, 100):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                items = [
                    ShoppingItem(f"Υλικό {index}", "κιλό", Decimal("1.5"), "άλλα")
                    for index in range(count)
                ]
                documents = []
                scales = []
                page_sizes = []

                class RecordingDocument(QTextDocument):
                    def __init__(self):
                        super().__init__()
                        documents.append(self)

                class RecordingPainter(QPainter):
                    def begin(self, device):
                        page_sizes.append(device.pageRect(QPrinter.DevicePixel).size())
                        return super().begin(device)

                    def scale(self, x, y):
                        scales.append((x, y))
                        return super().scale(x, y)

                destination = Path(directory) / "shopping.pdf"
                with patch("utilities.weekly_export.QTextDocument", RecordingDocument), \
                        patch("utilities.weekly_export.QPainter", RecordingPainter):
                    export_shopping_list_pdf(
                        WeeklyPlan(date(2026, 3, 2), ()), items, destination,
                        "Λίστα αγορών", "Κατηγορία", "Υλικό", "Ποσότητα", "Μονάδα",
                        lambda value: value,
                    )

                pdf = destination.read_bytes()
                self.assertEqual(len(re.findall(rb"/Type\s*/Page\b", pdf)), 1)
                document = documents[0]
                self.assertIn("Λίστα αγορών", document.toPlainText())
                self.assertIn("02/03/2026", document.toPlainText())
                for item in items:
                    self.assertIn(item.name, document.toPlainText())
                scale_x, scale_y = scales[0]
                self.assertLessEqual(document.size().width() * scale_x, page_sizes[0].width() + 0.01)
                self.assertLessEqual(document.size().height() * scale_y, page_sizes[0].height() + 0.01)
                if count == 100:
                    self.assertLess(scale_y, 1)

    def test_unwritable_destination_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(OSError):
                export_shopping_list_pdf(
                    WeeklyPlan(date(2026, 3, 2), ()), [], Path(directory) / "missing" / "list.pdf",
                    "Λίστα", "Κατηγορία", "Υλικό", "Ποσότητα", "Μονάδα",
                    lambda value: value,
                )

    def test_special_quantities_in_dialog_clipboard_and_pdf(self):
        items = [
            ShoppingItem("πατάτες", "κιλό", Decimal("1"), more_than=True),
            ShoppingItem("δυόσμος", "", None),
        ]
        dialog = ShoppingDialog(items, "el")
        self.assertEqual(dialog.list_text.toPlainText(), "πατάτες: >1 κιλό\nδυόσμος")
        self.assertEqual(dialog.table.item(0, 2).text(), ">1")
        self.assertEqual(dialog.table.item(1, 2).text(), "")
        self.assertEqual(dialog.table.item(1, 3).text(), "")
        dialog.copy_list()
        self.assertEqual(self.app.clipboard().text(), "πατάτες: >1 κιλό\nδυόσμος")

        documents = []

        class RecordingDocument(QTextDocument):
            def __init__(self):
                super().__init__()
                documents.append(self)

        with tempfile.TemporaryDirectory() as directory:
            with patch("utilities.weekly_export.QTextDocument", RecordingDocument):
                export_shopping_list_pdf(
                    WeeklyPlan(date(2026, 3, 2), ()), items, Path(directory) / "list.pdf",
                    "Λίστα", "Κατηγορία", "Υλικό", "Ποσότητα", "Μονάδα",
                    lambda value: value,
                )
            text = documents[0].toPlainText()
            self.assertIn(">1", text)
            self.assertIn("δυόσμος", text)
            self.assertEqual(text.count("πατάτες"), 1)
            self.assertEqual(text.count("δυόσμος"), 1)


if __name__ == "__main__":
    unittest.main()
