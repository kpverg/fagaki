import tempfile
import unittest
from pathlib import Path

from PyQt5.QtCore import QSettings

from services.settings_service import SettingsService
from utilities.settings import AppSettings
from utilities.translations import TEXT


class SettingsServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = str(Path(self.directory.name) / "settings.ini")
        self.store = QSettings(path, QSettings.IniFormat)
        self.service = SettingsService(self.store)

    def test_invalid_stored_font_size_is_reported(self):
        self.store.setValue("font_size", "invalid")
        self.store.sync()
        with self.assertRaisesRegex(ValueError, "font size"):
            self.service.load(10)

    def test_invalid_values_cannot_be_saved(self):
        for settings in (
            AppSettings("not-a-color", "#000000", 10, "el"),
            AppSettings("#ffffff", "not-a-color", 10, "el"),
            AppSettings("#ffffff", "#000000", 49, "el"),
            AppSettings("#ffffff", "#000000", 10, "unknown"),
        ):
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    self.service.save(settings)
        self.assertEqual(self.store.allKeys(), [])

    def test_both_languages_cover_the_same_text(self):
        self.assertEqual(TEXT["el"].keys(), TEXT["en"].keys())


if __name__ == "__main__":
    unittest.main()
