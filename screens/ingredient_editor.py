from PyQt5.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from utilities.ingredients import CATEGORIES, Ingredient, UNITS
from utilities.translations import text


class IngredientEditor(QWidget):
    def __init__(self, available: list[Ingredient], items: tuple[Ingredient, ...], language: str):
        super().__init__()
        self.language = language
        self.available = available
        self.items = list(items)
        self.changed = False
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            text(language, "ingredient"), text(language, "quantity"),
            text(language, "unit"), text(language, "category"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(100)

        self.name_input = QComboBox()
        self.name_input.setEditable(True)
        self.name_input.setInsertPolicy(QComboBox.NoInsert)
        for ingredient in available:
            self.name_input.addItem(ingredient.name, ingredient.id)
        self.name_input.setCurrentIndex(-1)
        self.name_input.lineEdit().setPlaceholderText(text(language, "ingredient_hint"))
        self.unit_input = QComboBox()
        self.unit_input.addItem(text(language, "unit_required"), None)
        for unit in UNITS:
            self.unit_input.addItem(text(language, unit), unit)
        self.category_input = QComboBox()
        for category in CATEGORIES:
            self.category_input.addItem(text(language, category), category)
        self.name_input.currentIndexChanged.connect(self._select_unit)
        self.name_input.editTextChanged.connect(self._clear_unit_for_new_name)
        self.quantity_input = QDoubleSpinBox()
        self.quantity_input.setDecimals(3)
        self.quantity_input.setRange(0, 1000000)
        self.quantity_input.setSpecialValueText(text(language, "quantity_required"))
        self.add_button = QPushButton(text(language, "add_ingredient"))
        self.remove_button = QPushButton(text(language, "remove_ingredient"))
        self.add_button.clicked.connect(self.add_ingredient)
        self.remove_button.clicked.connect(self.remove_ingredient)
        row = QHBoxLayout()
        row.addWidget(self.name_input, 2)
        row.addWidget(QLabel(text(language, "quantity")))
        row.addWidget(self.quantity_input)
        row.addWidget(QLabel(text(language, "unit")))
        row.addWidget(self.unit_input)
        row.addWidget(QLabel(text(language, "category")))
        row.addWidget(self.category_input)
        row.addWidget(self.add_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.table)
        layout.addWidget(self.remove_button)
        self._refresh()

    def _select_unit(self, index: int) -> None:
        if index >= 0:
            self.unit_input.setCurrentIndex(self.unit_input.findData(self.available[index].unit))
            self.category_input.setCurrentIndex(
                self.category_input.findData(self.available[index].category)
            )
        else:
            self.unit_input.setCurrentIndex(0)
            self.category_input.setCurrentIndex(self.category_input.findData("άλλα"))

    def _clear_unit_for_new_name(self, name: str) -> None:
        index = self.name_input.currentIndex()
        if index < 0 or self.available[index].name != name:
            self.unit_input.setCurrentIndex(0)
            self.category_input.setCurrentIndex(self.category_input.findData("άλλα"))

    def _refresh(self) -> None:
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            quantity = "" if item.quantity is None else f"{item.quantity:g}"
            for col, value in enumerate((
                item.name, quantity, text(self.language, item.unit),
                text(self.language, item.category),
            )):
                self.table.setItem(row, col, QTableWidgetItem(value))

    def add_ingredient(self) -> None:
        name = self.name_input.currentText().strip()
        if not name:
            QMessageBox.warning(self, text(self.language, "ingredient"), text(self.language, "ingredient_required"))
            return
        if self.quantity_input.value() <= 0:
            QMessageBox.warning(self, text(self.language, "ingredient"), text(self.language, "quantity_required"))
            return
        matches = [item for item in self.available if item.name.casefold() == name.casefold()]
        selected_id = self.name_input.currentData()
        selected = next((item for item in matches if item.id == selected_id), None)
        if selected is None and len(matches) == 1:
            selected = matches[0]
        if len(matches) > 1 and selected is None:
            QMessageBox.warning(self, text(self.language, "ingredient"), text(self.language, "ingredient_ambiguous"))
            return
        unit = self.unit_input.currentData()
        if unit is None:
            QMessageBox.warning(self, text(self.language, "ingredient"), text(self.language, "unit_required"))
            return
        if any(item.name.casefold() == name.casefold() and item.unit == unit for item in self.items):
            QMessageBox.warning(self, text(self.language, "ingredient"), text(self.language, "ingredient_duplicate"))
            return
        self.items.append(Ingredient(
            selected.id if selected else None,
            name,
            unit,
            self.quantity_input.value(),
            self.category_input.currentData(),
        ))
        self.changed = True
        self._refresh()
        self.name_input.setCurrentIndex(-1)
        self.unit_input.setCurrentIndex(0)
        self.category_input.setCurrentIndex(self.category_input.findData("άλλα"))
        self.quantity_input.setValue(0)

    def remove_ingredient(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, text(self.language, "ingredient"), text(self.language, "select_ingredient"))
            return
        self.items.pop(row)
        self.changed = True
        self._refresh()
