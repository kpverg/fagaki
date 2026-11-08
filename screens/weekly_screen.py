import sqlite3
from datetime import timedelta
from pathlib import Path

from PyQt5.QtCore import QDate, QStandardPaths
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.weekly_service import WeeklyService
from utilities.translations import DAY_KEYS, text, weekday_name
from utilities.weekly_export import export_shopping_list_pdf, export_weekly_plan_pdf
from utilities.weekly_plan import PlanningError


class ShoppingDialog(QDialog):
    def __init__(self, items, language: str, saved_path=None, parent=None):
        super().__init__(parent)
        self.language = language
        self.setWindowTitle(text(language, "shopping_title"))
        self.resize(450, 400)
        self.list_text = QPlainTextEdit()
        self.list_text.setReadOnly(True)
        self.list_text.setPlainText("\n".join(
            f"{item.name}: {item.quantity_text()} {text(language, item.unit)}"
            if item.quantity is not None else item.name
            for item in items
        ))
        self.table = QTableWidget(len(items), 4)
        self.table.setHorizontalHeaderLabels([
            text(language, "category"),
            text(language, "ingredient"),
            text(language, "quantity"),
            text(language, "unit"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        for row, item in enumerate(items):
            values = (
                text(language, item.category),
                item.name,
                item.quantity_text(),
                text(language, item.unit) if item.unit else "",
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.copy_button = QPushButton(text(language, "copy_list"))
        self.copy_button.clicked.connect(self.copy_list)
        self.status_label = QLabel()
        if saved_path is not None:
            self.status_label.setText(
                f"{text(language, 'shopping_saved')}\n{saved_path}"
            )
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(text(language, "close"))
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(self.list_text)
        layout.addWidget(self.copy_button)
        layout.addWidget(self.status_label)
        layout.addWidget(buttons)

    def copy_list(self):
        QApplication.clipboard().setText(self.list_text.toPlainText())
        self.status_label.setText(text(self.language, "copied"))


class WeeklyScreen(QWidget):
    def __init__(self, service: WeeklyService, language: str, parent=None):
        super().__init__(parent)
        self.setObjectName("weeklyContent")
        self.service = service
        self.language = language
        self.weekdays = {}
        self.week_label = QLabel()
        self.week_input = QDateEdit(QDate.currentDate())
        self.week_input.setCalendarPopup(True)
        self.week_input.setDisplayFormat("dd/MM/yyyy")
        self.create_button = QPushButton()
        self.shopping_button = QPushButton()
        self.save_button = QPushButton()
        self.create_button.clicked.connect(self.create_plan)
        self.shopping_button.clicked.connect(self.show_shopping)
        self.save_button.clicked.connect(self.save_to_desktop)
        top = QHBoxLayout()
        top.addWidget(self.week_label)
        top.addWidget(self.week_input)
        top.addStretch()
        self.plan_label = QLabel()
        self.table = QTableWidget(0, 3)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(max(30, self.fontMetrics().height() + 14))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        buttons = QHBoxLayout()
        buttons.addWidget(self.create_button)
        buttons.addWidget(self.shopping_button)
        buttons.addWidget(self.save_button)
        buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.plan_label)
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        self.retranslate(language)

    def retranslate(self, language: str):
        self.language = language
        self.week_label.setText(text(language, "week_date"))
        self.create_button.setText(text(language, "create_plan"))
        self.shopping_button.setText(text(language, "shopping"))
        self.save_button.setText(text(language, "save_desktop"))
        self.table.setHorizontalHeaderLabels([
            text(language, "weekday"), text(language, "date"), text(language, "meal")
        ])
        self.table.verticalHeader().setDefaultSectionSize(max(30, self.fontMetrics().height() + 14))
        self.refresh()

    def refresh(self):
        try:
            self.weekdays = {day.id: day for day in self.service.list_weekdays()}
            plan = self.service.load()
            if plan is None:
                self.table.setRowCount(0)
                self.plan_label.setText(text(self.language, "no_plan"))
                return
            choices = [self.service.eligible(plan.start, day) for day in range(1, 8)]
        except (sqlite3.Error, ValueError) as error:
            self._error(error)
            return
        self.week_input.setDate(QDate(plan.start.year, plan.start.month, plan.start.day))
        end = plan.start + timedelta(days=6)
        self.plan_label.setText(f"{plan.start:%d/%m/%Y} – {end:%d/%m/%Y}")
        self.table.setRowCount(7)
        for row, entry in enumerate(plan.entries):
            self.table.setItem(
                row, 0, QTableWidgetItem(weekday_name(self.weekdays[entry.weekday], self.language))
            )
            day = plan.start + timedelta(days=row)
            self.table.setItem(row, 1, QTableWidgetItem(day.strftime("%d/%m/%Y")))
            combo = QComboBox()
            for meal in choices[row]:
                combo.addItem(meal.name, meal.id)
            selected = combo.findData(entry.meal_id)
            if selected < 0:
                unavailable = (
                    f"{entry.meal_name} — {text(self.language, 'invalid_assignment')}"
                    if entry.meal_name else text(self.language, "plan_incomplete")
                )
                combo.insertItem(0, unavailable, None)
                selected = 0
            combo.setCurrentIndex(selected)
            combo.currentIndexChanged.connect(
                lambda index, widget=combo, weekday=entry.weekday: self.change_meal(
                    weekday, widget.itemData(index)
                )
            )
            self.table.setCellWidget(row, 2, combo)

    def create_plan(self):
        try:
            existing = self.service.load()
            if existing is not None:
                confirmation = QMessageBox(
                    QMessageBox.Question, text(self.language, "weekly_tab"),
                    text(self.language, "replace_plan"), QMessageBox.Yes | QMessageBox.No, self
                )
                confirmation.setDefaultButton(QMessageBox.No)
                confirmation.button(QMessageBox.Yes).setText(text(self.language, "yes"))
                confirmation.button(QMessageBox.No).setText(text(self.language, "no"))
                if confirmation.exec_() != QMessageBox.Yes:
                    return
            self.service.create(self.week_input.date().toPyDate())
        except (sqlite3.Error, ValueError, PlanningError) as error:
            self._error(error)
            return
        self.refresh()

    def change_meal(self, weekday: int, meal_id):
        if meal_id is None:
            return
        try:
            self.service.change_meal(weekday, meal_id)
        except (sqlite3.Error, ValueError, PlanningError) as error:
            self._error(error)
            self.refresh()

    def show_shopping(self):
        try:
            items = self.service.shopping_list()
            plan = self.service.load()
            if plan is None:
                raise PlanningError("plan_missing")
            desktop = Path(QStandardPaths.writableLocation(QStandardPaths.DesktopLocation))
            if not desktop:
                raise OSError("Δεν βρέθηκε η Επιφάνεια Εργασίας.")
            destination = desktop / f"lista_agoron_{plan.start.isoformat()}.pdf"
            export_shopping_list_pdf(
                plan,
                items,
                destination,
                text(self.language, "shopping_title"),
                text(self.language, "category"),
                text(self.language, "ingredient"),
                text(self.language, "quantity"),
                text(self.language, "unit"),
                lambda key: text(self.language, key),
            )
        except (sqlite3.Error, ValueError, PlanningError) as error:
            self._error(error)
            return
        except OSError as error:
            self._error(error)
            return
        ShoppingDialog(items, self.language, destination, self).exec_()

    def save_to_desktop(self):
        try:
            plan = self.service.load()
            if plan is None:
                raise PlanningError("plan_missing")
            desktop = Path(QStandardPaths.writableLocation(QStandardPaths.DesktopLocation))
            if not desktop:
                raise OSError("Δεν βρέθηκε η Επιφάνεια Εργασίας.")
            destination = desktop / f"fagaki_{plan.start.isoformat()}.pdf"
            export_weekly_plan_pdf(
                plan,
                self.weekdays,
                destination,
                text(self.language, "weekly_tab"),
                text(self.language, "weekday"),
                text(self.language, "date"),
                text(self.language, "meal"),
            )
        except (OSError, sqlite3.Error, ValueError, PlanningError) as error:
            self._error(error)
            return
        QMessageBox.information(
            self,
            text(self.language, "weekly_tab"),
            f"{text(self.language, 'saved_desktop')}\n{destination}",
        )

    def _error(self, error):
        if isinstance(error, PlanningError):
            message = text(self.language, error.reason)
            if error.reason == "no_eligible_meals" and error.details:
                day = self.weekdays.get(int(error.details))
                message += " " + (weekday_name(day, self.language) if day else
                                   text(self.language, DAY_KEYS[int(error.details) - 1]))
            elif error.details:
                message += " " + error.details
            QMessageBox.warning(self, text(self.language, "weekly_tab"), message)
        else:
            QMessageBox.critical(self, text(self.language, "database_error"), str(error))
