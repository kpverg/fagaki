import sqlite3
import unicodedata
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QPalette, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QApplication,
    QComboBox,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dbservices.database import DATABASE_PATH, WEEKDAYS
from screens.ingredient_editor import IngredientEditor
from screens.settingscreen import SettingsScreen
from screens.weekly_screen import WeeklyScreen
from services.meal_service import MealService
from services.settings_service import SettingsService
from services.weekly_service import WeeklyService
from style.styles import CARROT_PATH, apply_styles
from utilities.meal import MealData, Weekday
from utilities.translations import text, weekday_name


class BackgroundWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.carrot = QPixmap(str(CARROT_PATH))
        if self.carrot.isNull():
            raise RuntimeError(f"Δεν ήταν δυνατή η φόρτωση της εικόνας: {CARROT_PATH}")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QApplication.palette().color(QPalette.Window))
        painter.setOpacity(0.22)
        image = self.carrot.scaled(
            self.size() * 0.7, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        painter.drawPixmap((self.width() - image.width()) // 2,
                           (self.height() - image.height()) // 2, image)


class WeekdayTableItem(QTableWidgetItem):
    def __lt__(self, other):
        day = self.data(Qt.UserRole)
        other_day = other.data(Qt.UserRole)
        return (day.id if day else 8) < (other_day.id if other_day else 8)


def _search_key(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    )


class MealDialog(QDialog):
    def __init__(self, parent=None, meal=None, language="el", available_ingredients=None,
                 weekdays=None):
        super().__init__(parent)
        self.language = language
        self.setWindowTitle(text(language, "meal"))
        self.resize(700, 700)
        self.name_input = QLineEdit()
        self.ingredients_input = QPlainTextEdit()
        self.ingredients_input.setReadOnly(True)
        self.recipe_input = QPlainTextEdit()
        self.fasting_input = QCheckBox(text(language, "fasting"))
        self.weekday_input = QComboBox()
        if weekdays is None:
            weekdays = [Weekday(day_id, name) for day_id, name, _ in WEEKDAYS]
        self.weekday_input.addItem(text(language, "weekday_unassigned"), None)
        for day in weekdays:
            self.weekday_input.addItem(weekday_name(day, language), day.id)
        self.ingredient_editor = IngredientEditor(
            available_ingredients or [], meal.ingredient_items or () if meal else (), language
        )
        self.ingredients_input.setPlaceholderText(text(language, "ingredients_hint"))
        self.recipe_input.setPlaceholderText(text(language, "recipe_hint"))
        if meal is not None:
            self.name_input.setText(meal.name)
            self.ingredients_input.setPlainText(meal.ingredients)
            self.recipe_input.setPlainText(meal.recipe)
            self.fasting_input.setChecked(meal.is_fasting)
            index = self.weekday_input.findData(meal.weekday_id)
            if index >= 0:
                self.weekday_input.setCurrentIndex(index)

        form = QFormLayout()
        form.addRow(text(language, "name"), self.name_input)
        form.addRow(text(language, "weekday_field"), self.weekday_input)
        if meal is not None and meal.ingredients:
            form.addRow(text(language, "ingredients"), self.ingredients_input)
        form.addRow("", QLabel(text(language, "legacy_note")))
        form.addRow(text(language, "structured_ingredients"), self.ingredient_editor)
        form.addRow(text(language, "recipe"), self.recipe_input)
        form.addRow("", self.fasting_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(text(language, "save"))
        buttons.button(QDialogButtonBox.Cancel).setText(text(language, "cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(
                self, text(self.language, "missing_details"), text(self.language, "name_required")
            )
            self.name_input.setFocus()
            return
        if self.weekday_input.currentData() is None:
            QMessageBox.warning(
                self, text(self.language, "missing_details"), text(self.language, "weekday_required")
            )
            self.weekday_input.setFocus()
            return
        super().accept()

    def values(self):
        return MealData(
            name=self.name_input.text().strip(),
            ingredients=self.ingredients_input.toPlainText().strip(),
            is_fasting=self.fasting_input.isChecked(),
            recipe=self.recipe_input.toPlainText().strip(),
            ingredient_items=(tuple(self.ingredient_editor.items)
                              if self.ingredient_editor.changed else None),
            weekday_id=self.weekday_input.currentData(),
        )


class MainWindow(QMainWindow):
    def __init__(self, database_path: str | Path = DATABASE_PATH,
                 settings_service: SettingsService | None = None):
        super().__init__()
        self.database_path = database_path
        self.settings_service = settings_service or SettingsService()
        self.settings = self.settings_service.load(QApplication.font().pointSize())
        apply_styles(QApplication.instance(), self.settings)
        self.meal_service = MealService(database_path)
        self.resize(720, 480)

        self.table = QTableWidget(0, 3)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(self.edit_meal)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.AscendingOrder)
        self.table.horizontalHeader().sectionClicked.connect(self.apply_recipe_filters)

        self.weekdays = []
        self.search_label = QLabel("🔍")
        self.search_input = QLineEdit()
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.apply_recipe_filters)
        self.day_filter = QComboBox()
        self.day_filter.currentIndexChanged.connect(self.apply_recipe_filters)
        filters = QHBoxLayout()
        filters.addWidget(self.search_label)
        filters.addWidget(self.search_input, 1)
        filters.addWidget(self.day_filter)

        self.add_button = QPushButton()
        self.edit_button = QPushButton()
        self.delete_button = QPushButton()
        self.add_button.clicked.connect(self.add_meal)
        self.edit_button.clicked.connect(self.edit_meal)
        self.delete_button.clicked.connect(self.delete_meal)
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch()

        self.title_label = QLabel()
        self.settings_button = QPushButton("⚙")
        self.settings_button.setAccessibleName(text(self.settings.language, "settings"))
        self.settings_button.clicked.connect(self.open_settings)
        heading = QHBoxLayout()
        heading.addWidget(self.title_label)
        heading.addStretch()
        heading.addWidget(self.settings_button)
        recipes = BackgroundWidget()
        recipes.setObjectName("recipesPage")
        recipes_layout = QVBoxLayout(recipes)
        recipes_layout.addLayout(filters)
        recipes_layout.addWidget(self.table)
        recipes_layout.addLayout(buttons)
        self.weekly_screen = WeeklyScreen(WeeklyService(database_path), self.settings.language)
        weekly_page = BackgroundWidget()
        weekly_page.setObjectName("weeklyPage")
        weekly_layout = QVBoxLayout(weekly_page)
        weekly_layout.setContentsMargins(0, 0, 0, 0)
        weekly_layout.addWidget(self.weekly_screen)
        self.tabs = QTabWidget()
        self.tabs.addTab(recipes, "")
        self.tabs.addTab(weekly_page, "")
        layout = QVBoxLayout()
        layout.addLayout(heading)
        layout.addWidget(self.tabs)
        central = BackgroundWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self.retranslate_ui()
        self.refresh()

    def retranslate_ui(self):
        language = self.settings.language
        self.setWindowTitle(text(language, "window_title"))
        self.title_label.setText(text(language, "app_name"))
        self.tabs.setTabText(0, text(language, "recipes_tab"))
        self.tabs.setTabText(1, text(language, "weekly_tab"))
        self.weekly_screen.retranslate(language)
        self.search_input.setPlaceholderText(text(language, "search_recipes"))
        self.search_input.setAccessibleName(text(language, "search_recipes"))
        self.search_label.setAccessibleName(text(language, "search_recipes"))
        self.day_filter.setAccessibleName(text(language, "filter_weekday"))
        self._populate_day_filter()
        self.table.setHorizontalHeaderLabels([
            text(language, "meal"), text(language, "fasting"), text(language, "weekday")
        ])
        self.add_button.setText(text(language, "add"))
        self.edit_button.setText(text(language, "edit"))
        self.delete_button.setText(text(language, "delete"))
        self.settings_button.setToolTip(text(language, "settings"))
        self.settings_button.setAccessibleName(text(language, "settings"))
        self.table.setSortingEnabled(False)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            item.setText(text(language, "yes" if item.data(Qt.UserRole) else "no"))
            day_item = self.table.item(row, 2)
            day = day_item.data(Qt.UserRole)
            day_item.setText(weekday_name(day, language) if day else text(language, "weekday_unassigned"))
        self.table.setSortingEnabled(True)
        self.apply_recipe_filters()

    def _populate_day_filter(self):
        selected = self.day_filter.currentData()
        self.day_filter.blockSignals(True)
        try:
            self.day_filter.clear()
            self.day_filter.addItem(text(self.settings.language, "all_weekdays"), None)
            for day in self.weekdays:
                self.day_filter.addItem(weekday_name(day, self.settings.language), day.id)
            self.day_filter.addItem(text(self.settings.language, "weekday_unassigned"), 0)
            index = self.day_filter.findData(selected)
            self.day_filter.setCurrentIndex(max(index, 0))
        finally:
            self.day_filter.blockSignals(False)

    def apply_recipe_filters(self):
        query = _search_key(self.search_input.text().strip())
        selected_day = self.day_filter.currentData()
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0)
            day = self.table.item(row, 2).data(Qt.UserRole)
            day_id = day.id if day else 0
            visible = query in _search_key(name.text()) and (
                selected_day is None or day_id == selected_day
            )
            self.table.setRowHidden(row, not visible)
        current = self.table.currentRow()
        if current >= 0 and self.table.isRowHidden(current):
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)

    def open_settings(self):
        dialog = SettingsScreen(self.settings, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        settings = dialog.values()
        try:
            self.settings_service.save(settings)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, text(self.settings.language, "settings_error"), str(error))
            return
        self.settings = settings
        apply_styles(QApplication.instance(), settings)
        self.retranslate_ui()

    def refresh(self):
        try:
            meals = self.meal_service.list_meals()
            weekdays = self.meal_service.list_weekdays()
        except sqlite3.Error as error:
            self.show_database_error(error)
            return
        self.weekdays = weekdays
        self._populate_day_filter()
        days_by_id = {day.id: day for day in weekdays}
        self.table.setSortingEnabled(False)
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.table.setRowCount(len(meals))
        for row, meal in enumerate(meals):
            name = QTableWidgetItem(meal.name)
            name.setData(Qt.UserRole, meal.id)
            self.table.setItem(row, 0, name)
            fasting = QTableWidgetItem(text(self.settings.language, "yes" if meal.is_fasting else "no"))
            fasting.setData(Qt.UserRole, meal.is_fasting)
            self.table.setItem(row, 1, fasting)
            day = days_by_id.get(meal.weekday_id)
            day_item = WeekdayTableItem(
                weekday_name(day, self.settings.language) if day else text(self.settings.language, "weekday_unassigned")
            )
            day_item.setData(Qt.UserRole, day)
            self.table.setItem(row, 2, day_item)
        self.table.setSortingEnabled(True)
        self.apply_recipe_filters()
        self.weekly_screen.refresh()

    def selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, text(self.settings.language, "select_meal_title"),
                text(self.settings.language, "select_meal"),
            )
            return None
        return self.table.item(row, 0).data(Qt.UserRole)

    def add_meal(self):
        try:
            available = self.meal_service.list_ingredients()
            weekdays = self.meal_service.list_weekdays()
        except sqlite3.Error as error:
            self.show_database_error(error)
            return
        dialog = MealDialog(self, language=self.settings.language, available_ingredients=available,
                            weekdays=weekdays)
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            self.meal_service.add_meal(dialog.values())
        except (sqlite3.Error, ValueError) as error:
            self.show_database_error(error)
            return
        self.refresh()

    def edit_meal(self):
        meal_id = self.selected_id()
        if meal_id is None:
            return
        try:
            meal = self.meal_service.get_meal(meal_id)
        except sqlite3.Error as error:
            self.show_database_error(error)
            return
        if meal is None:
            QMessageBox.warning(
                self, text(self.settings.language, "meal"), text(self.settings.language, "meal_missing")
            )
            self.refresh()
            return
        try:
            available = self.meal_service.list_ingredients()
            weekdays = self.meal_service.list_weekdays()
        except sqlite3.Error as error:
            self.show_database_error(error)
            return
        dialog = MealDialog(self, meal, self.settings.language, available, weekdays)
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            if not self.meal_service.update_meal(meal_id, dialog.values()):
                QMessageBox.warning(
                    self, text(self.settings.language, "meal"), text(self.settings.language, "meal_missing")
                )
        except (sqlite3.Error, ValueError) as error:
            self.show_database_error(error)
            return
        self.refresh()

    def delete_meal(self):
        meal_id = self.selected_id()
        if meal_id is None:
            return
        language = self.settings.language
        confirmation = QMessageBox(
            QMessageBox.Question, text(language, "delete"), text(language, "delete_question"),
            QMessageBox.Yes | QMessageBox.No, self,
        )
        confirmation.setDefaultButton(QMessageBox.No)
        confirmation.button(QMessageBox.Yes).setText(text(language, "yes"))
        confirmation.button(QMessageBox.No).setText(text(language, "no"))
        answer = confirmation.exec_()
        if answer != QMessageBox.Yes:
            return
        try:
            if not self.meal_service.delete_meal(meal_id):
                QMessageBox.warning(
                    self, text(self.settings.language, "meal"), text(self.settings.language, "meal_missing")
                )
        except sqlite3.Error as error:
            self.show_database_error(error)
            return
        self.refresh()

    def show_database_error(self, error):
        QMessageBox.critical(self, text(self.settings.language, "database_error"), str(error))
