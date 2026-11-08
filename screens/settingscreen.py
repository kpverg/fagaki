from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from style import styles
from utilities.settings import AppSettings
from utilities.translations import text


class SettingsScreen(QDialog):
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.language = settings.language
        self.background = settings.background
        self.font_color = settings.font_color
        self.setWindowTitle(text(self.language, "settings"))

        self.background_preview = QLabel()
        self.font_color_preview = QLabel()
        self.background_button = QPushButton(text(self.language, "choose_color"))
        self.font_color_button = QPushButton(text(self.language, "choose_color"))
        self.background_button.clicked.connect(self.choose_background)
        self.font_color_button.clicked.connect(self.choose_font_color)

        self.font_size_input = QSpinBox()
        self.font_size_input.setRange(styles.MIN_FONT_SIZE, styles.MAX_FONT_SIZE)
        self.font_size_input.setValue(settings.font_size)
        self.language_input = QComboBox()
        self.language_input.addItem("Ελληνικά", "el")
        self.language_input.addItem("English", "en")
        self.language_input.setCurrentIndex(self.language_input.findData(settings.language))

        form = QFormLayout()
        form.addRow(text(self.language, "background"),
                    self._color_row(self.background_button, self.background_preview))
        form.addRow(text(self.language, "font_color"),
                    self._color_row(self.font_color_button, self.font_color_preview))
        form.addRow(text(self.language, "font_size"), self.font_size_input)
        form.addRow(text(self.language, "language"), self.language_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(text(self.language, "save"))
        buttons.button(QDialogButtonBox.Cancel).setText(text(self.language, "cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._update_previews()

    @staticmethod
    def _color_row(button: QPushButton, preview: QLabel) -> QWidget:
        preview.setFixedSize(32, 24)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(button)
        layout.addWidget(preview)
        layout.addStretch()
        return row

    def _update_previews(self) -> None:
        self.background_preview.setStyleSheet(
            f"background-color: {self.background}; border: 1px solid #888888;"
        )
        self.font_color_preview.setStyleSheet(
            f"background-color: {self.font_color}; border: 1px solid #888888;"
        )

    def choose_background(self) -> None:
        color = styles.choose_color(
            self, self.background, text(self.language, "choose_background")
        )
        if color is not None:
            self.background = color
            self._update_previews()

    def choose_font_color(self) -> None:
        color = styles.choose_color(
            self, self.font_color, text(self.language, "choose_font_color")
        )
        if color is not None:
            self.font_color = color
            self._update_previews()

    def values(self) -> AppSettings:
        return AppSettings(
            self.background,
            self.font_color,
            self.font_size_input.value(),
            self.language_input.currentData(),
        )
