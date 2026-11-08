from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PlanEntry:
    weekday: int
    meal_id: int | None
    meal_name: str | None


@dataclass(frozen=True)
class WeeklyPlan:
    start: date
    entries: tuple[PlanEntry, ...]


class PlanningError(Exception):
    def __init__(self, reason: str, details: str = ""):
        super().__init__(reason, details)
        self.reason = reason
        self.details = details
