import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PyQt5.QtCore import QSettings

from services.settings_service import SettingsService
from utilities.settings import AppSettings


class ApplicationTests(unittest.TestCase):
    def check_entry_point_initializes_qt(self, platform):
        project_path = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "fagaki.db")
            settings_path = str(Path(directory) / "settings.ini")
            SettingsService(QSettings(settings_path, QSettings.IniFormat)).save(
                AppSettings("#dceffa", "#352060", 16, "en")
            )
            code = """
import runpy
import sys
from PyQt5.QtCore import QSettings, QTimer
from PyQt5.QtWidgets import QApplication
import services.application as application
from services.settings_service import SettingsService

original_window = application.MainWindow
def test_window():
    store = QSettings(sys.argv[2], QSettings.IniFormat)
    window = original_window(sys.argv[1], SettingsService(store))
    assert window.settings.background == '#dceffa'
    assert window.settings.font_color == '#352060'
    assert window.table.font().pointSize() == 16
    assert window.add_button.text() == 'Add'
    QTimer.singleShot(100, QApplication.instance().quit)
    return window
application.MainWindow = test_window
runpy.run_path('main.py', run_name='__main__')
"""
            environment = os.environ.copy()
            environment["QT_QPA_PLATFORM"] = platform
            result = subprocess.run(
                [sys.executable, "-c", code, database_path, settings_path],
                cwd=project_path,
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_entry_point_initializes_offscreen_qt(self):
        self.check_entry_point_initializes_qt("offscreen")

    @unittest.skipUnless(sys.platform == "win32", "Windows platform plugin required")
    def test_entry_point_initializes_windows_qt(self):
        self.check_entry_point_initializes_qt("windows")


if __name__ == "__main__":
    unittest.main()
