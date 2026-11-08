from pathlib import Path

from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtWidgets import QApplication, QColorDialog

from utilities.settings import AppSettings


CARROT_PATH = Path(__file__).resolve().parent.parent / "assets" / "carrot.png"
DEFAULT_BACKGROUND = "#efefef"
DEFAULT_FONT_COLOR = "#202020"
MIN_FONT_SIZE = 6
MAX_FONT_SIZE = 48

BUTTON_STYLE = """
QPushButton {
    background-color: #f28c28;
    border: 2px solid #55bde8;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton:hover {
    background-color: #ffa43e;
}
QPushButton:pressed {
    background-color: #dc7515;
}
QPushButton:disabled {
    background-color: #f2b478;
}
QTableWidget, QTableWidget QTableCornerButton::section {
    background: transparent;
}
QTabWidget::pane {
    background: transparent;
}
QWidget#recipesPage, QWidget#weeklyPage, QWidget#weeklyContent, QTabWidget QStackedWidget {
    background: transparent;
}
QTabBar::tab {
    padding: 6px 12px;
}
QTabBar::tab:selected {
    border-bottom: 3px solid #55bde8;
}
"""


def choose_color(parent, current: str, title: str) -> str | None:
    color = QColorDialog.getColor(QColor(current), parent, title)
    return color.name() if color.isValid() else None


def apply_styles(app: QApplication, settings: AppSettings) -> None:
    palette = QPalette(app.style().standardPalette())
    for role in (QPalette.Window, QPalette.Base, QPalette.AlternateBase):
        palette.setColor(role, QColor(settings.background))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText,
                 QPalette.ToolTipText):
        palette.setColor(role, QColor(settings.font_color))
    app.setPalette(palette)
    font = QFont(app.font())
    font.setPointSize(settings.font_size)
    app.setFont(font)
    app.setStyleSheet(
        BUTTON_STYLE
        + f"\n* {{ font-size: {settings.font_size}pt; }}"
        + f"\nQPushButton {{ color: {settings.font_color}; }}"
        + "\nQHeaderView::section, QTabBar::tab, QComboBox, QComboBox QAbstractItemView, "
          "QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit "
          f"{{ background-color: {settings.background}; color: {settings.font_color}; }}"
    )
