import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from main import DATABASE_PATH, initialize_database


class MealDialog(QDialog):
    def __init__(self, parent=None, meal=None):
        super().__init__(parent)
        self.setWindowTitle("Φαγητό")
        self.resize(480, 500)
        self.name_input = QLineEdit()
        self.ingredients_input = QPlainTextEdit()
        self.recipe_input = QPlainTextEdit()
        self.fasting_input = QCheckBox("Νηστίσιμο")
        self.ingredients_input.setPlaceholderText("Υλικά και ποσότητες")
        self.recipe_input.setPlaceholderText("Οδηγίες παρασκευής")
        if meal is not None:
            self.name_input.setText(meal["name"])
            self.ingredients_input.setPlainText(meal["ulika"])
            self.recipe_input.setPlainText(meal["syntagi"])
            self.fasting_input.setChecked(bool(meal["isnistisimo"]))

        form = QFormLayout()
        form.addRow("Όνομα:", self.name_input)
        form.addRow("Υλικά:", self.ingredients_input)
        form.addRow("Συνταγή:", self.recipe_input)
        form.addRow("", self.fasting_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Αποθήκευση")
        buttons.button(QDialogButtonBox.Cancel).setText("Ακύρωση")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Ελλιπή στοιχεία", "Συμπλήρωσε το όνομα του φαγητού.")
            self.name_input.setFocus()
            return
        super().accept()

    def values(self):
        return (
            self.name_input.text().strip(),
            self.ingredients_input.toPlainText().strip(),
            int(self.fasting_input.isChecked()),
            self.recipe_input.toPlainText().strip(),
        )


class MainWindow(QMainWindow):
    def __init__(self, database_path: str | Path = DATABASE_PATH):
        super().__init__()
        self.database_path = database_path
        initialize_database(database_path)
        self.setWindowTitle("Φαγάκι - Ρυθμίσεις")
        self.resize(720, 480)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Φαγητό", "Νηστίσιμο"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(self.edit_meal)

        add_button = QPushButton("Προσθήκη")
        edit_button = QPushButton("Επεξεργασία")
        delete_button = QPushButton("Διαγραφή")
        add_button.clicked.connect(self.add_meal)
        edit_button.clicked.connect(self.edit_meal)
        delete_button.clicked.connect(self.delete_meal)
        buttons = QHBoxLayout()
        buttons.addWidget(add_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(delete_button)
        buttons.addStretch()

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Φαγητά και συνταγές"))
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self.refresh()

    def connect_database(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def refresh(self):
        try:
            with closing(self.connect_database()) as connection:
                meals = connection.execute(
                    "SELECT id, name, isnistisimo FROM fagaki ORDER BY name, id"
                ).fetchall()
        except sqlite3.Error as error:
            self.show_database_error(error)
            return
        self.table.setRowCount(len(meals))
        for row, meal in enumerate(meals):
            name = QTableWidgetItem(meal["name"])
            name.setData(Qt.UserRole, meal["id"])
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem("Ναι" if meal["isnistisimo"] else "Όχι"))

    def selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Επιλογή φαγητού", "Επίλεξε ένα φαγητό.")
            return None
        return self.table.item(row, 0).data(Qt.UserRole)

    def add_meal(self):
        dialog = MealDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            with closing(self.connect_database()) as connection, connection:
                connection.execute(
                    "INSERT INTO fagaki (name, ulika, isnistisimo, syntagi) VALUES (?, ?, ?, ?)",
                    dialog.values(),
                )
        except sqlite3.Error as error:
            self.show_database_error(error)
            return
        self.refresh()

    def edit_meal(self):
        meal_id = self.selected_id()
        if meal_id is None:
            return
        try:
            with closing(self.connect_database()) as connection:
                meal = connection.execute(
                    "SELECT name, ulika, isnistisimo, syntagi FROM fagaki WHERE id = ?",
                    (meal_id,),
                ).fetchone()
        except sqlite3.Error as error:
            self.show_database_error(error)
            return
        if meal is None:
            QMessageBox.warning(self, "Φαγητό", "Το φαγητό δεν υπάρχει πλέον.")
            self.refresh()
            return
        dialog = MealDialog(self, meal)
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            with closing(self.connect_database()) as connection, connection:
                result = connection.execute(
                    "UPDATE fagaki SET name = ?, ulika = ?, isnistisimo = ?, syntagi = ? "
                    "WHERE id = ?",
                    (*dialog.values(), meal_id),
                )
                if result.rowcount == 0:
                    QMessageBox.warning(self, "Φαγητό", "Το φαγητό δεν υπάρχει πλέον.")
        except sqlite3.Error as error:
            self.show_database_error(error)
            return
        self.refresh()

    def delete_meal(self):
        meal_id = self.selected_id()
        if meal_id is None:
            return
        answer = QMessageBox.question(
            self, "Διαγραφή", "Να διαγραφεί το επιλεγμένο φαγητό και η συνταγή του;",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            with closing(self.connect_database()) as connection, connection:
                result = connection.execute("DELETE FROM fagaki WHERE id = ?", (meal_id,))
                if result.rowcount == 0:
                    QMessageBox.warning(self, "Φαγητό", "Το φαγητό δεν υπάρχει πλέον.")
        except sqlite3.Error as error:
            self.show_database_error(error)
            return
        self.refresh()

    def show_database_error(self, error):
        QMessageBox.critical(self, "Σφάλμα βάσης δεδομένων", str(error))


def run():
    app = QApplication(sys.argv)
    try:
        window = MainWindow()
    except sqlite3.Error as error:
        QMessageBox.critical(None, "Σφάλμα βάσης δεδομένων", str(error))
        return
    window.show()
    sys.exit(app.exec_())
