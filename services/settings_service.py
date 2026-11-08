from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QColor

from style.styles import DEFAULT_BACKGROUND, DEFAULT_FONT_COLOR, MAX_FONT_SIZE, MIN_FONT_SIZE
from utilities.settings import AppSettings


class SettingsService:
    def __init__(self, store: QSettings | None = None):
        self.store = store if store is not None else QSettings("Fagaki", "Fagaki")

    def load(self, default_font_size: int) -> AppSettings:
        self.store.sync()
        self._check_status()
        background = self.store.value("background", DEFAULT_BACKGROUND, type=str)
        font_color = self.store.value("font_color", DEFAULT_FONT_COLOR, type=str)
        default_font_size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, default_font_size))
        try:
            font_size = self.store.value("font_size", default_font_size, type=int)
        except TypeError as error:
            raise ValueError("Invalid settings font size") from error
        language = self.store.value("language", "el", type=str)
        settings = AppSettings(background, font_color, font_size, language)
        self._validate(settings)
        return settings

    def save(self, settings: AppSettings) -> None:
        self._validate(settings)
        self.store.setValue("background", settings.background)
        self.store.setValue("font_color", settings.font_color)
        self.store.setValue("font_size", settings.font_size)
        self.store.setValue("language", settings.language)
        self.store.sync()
        self._check_status()

    def _check_status(self) -> None:
        if self.store.status() != QSettings.NoError:
            raise OSError(f"Settings storage error: {self.store.status()}")

    @staticmethod
    def _validate(settings: AppSettings) -> None:
        if not QColor(settings.background).isValid() or not QColor(settings.font_color).isValid():
            raise ValueError("Invalid settings color")
        if not MIN_FONT_SIZE <= settings.font_size <= MAX_FONT_SIZE:
            raise ValueError("Invalid settings font size")
        if settings.language not in ("el", "en"):
            raise ValueError("Invalid settings language")
