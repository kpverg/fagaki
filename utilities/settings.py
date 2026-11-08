from dataclasses import dataclass


@dataclass(frozen=True)
class AppSettings:
    background: str
    font_color: str
    font_size: int
    language: str
