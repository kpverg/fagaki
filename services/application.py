import sqlite3
import sys
from pathlib import Path

import PyQt5
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtWidgets import QApplication, QMessageBox

from screens.maininterface import MainWindow


def configure_qt_plugins():
    # Qt's bundled plugin path may be corrupted when it contains non-ASCII characters.
    plugin_path = Path(PyQt5.__file__).resolve().parent / "Qt5" / "plugins"
    if plugin_path.is_dir():
        QCoreApplication.addLibraryPath(str(plugin_path))


def run():
    configure_qt_plugins()
    app = QApplication(sys.argv)
    try:
        window = MainWindow()
    except sqlite3.Error as error:
        QMessageBox.critical(None, "Σφάλμα βάσης δεδομένων", str(error))
        sys.exit(1)
    except (OSError, ValueError) as error:
        QMessageBox.critical(None, "Σφάλμα ρυθμίσεων", str(error))
        sys.exit(1)
    window.show()
    sys.exit(app.exec_())
