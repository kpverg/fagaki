import random
import unicodedata
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from dbservices.weekly_repository import WeeklyRepository
from utilities.ingredients import CATEGORY_ORDER, ShoppingItem
from utilities.meal import MealSummary, Weekday
from utilities.weekly_plan import PlanningError, WeeklyPlan


_SHOPPING_EXCLUSIONS = frozenset({
    "νερο", "ριγανη", "αποξηραμενη ριγανη", "αλατι", "πιπερι",
    "ελαιολαδο", "ζαχαρη", "κρυσταλλικη ζαχαρη", "πρεζα κρυσταλλικη ζαχαρη",
})


def _normalized_name(name: str) -> str:
    normalized = unicodedata.normalize("NFD", name.strip().casefold())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


_SINGLE_ROW_NAMES = {
    "πατατα": "πατατες",
    "πατατεσ": "πατατες",
    "αλευρι": "αλευρι",
    "δυοσμοσ": "δυοσμος",
}


class WeeklyService:
    def __init__(self, database_path: str | Path):
        self.repository = WeeklyRepository(database_path)

    def load(self) -> WeeklyPlan | None:
        return self.repository.load_plan()

    def list_weekdays(self) -> list[Weekday]:
        weekdays = self.repository.list_weekdays()
        if [day.id for day in weekdays] != list(range(1, 8)):
            raise ValueError("Invalid weekdays in database")
        return weekdays

    @staticmethod
    def _eligible(meal: MealSummary, weekday: int, fasting: set[int]) -> bool:
        return meal.weekday_id == weekday and (weekday not in fasting or meal.is_fasting)

    def eligible(self, start: date, weekday: int) -> list[MealSummary]:
        meals = self.repository.list_meals()
        fasting = self.repository.fasting_dates(start)
        return [meal for meal in meals if self._eligible(meal, weekday, fasting)]

    def create(self, selected_date: date) -> WeeklyPlan:
        start = selected_date - timedelta(days=selected_date.weekday())
        self.list_weekdays()
        meals = self.repository.list_meals()
        fasting = self.repository.fasting_dates(start)
        selected = []
        for weekday in range(1, 8):
            eligible = [meal for meal in meals if self._eligible(meal, weekday, fasting)]
            if not eligible:
                raise PlanningError("no_eligible_meals", str(weekday))
            selected.append(random.choice(eligible).id)
        self.repository.replace_plan(start, selected)
        plan = self.repository.load_plan()
        if plan is None:
            raise PlanningError("plan_missing")
        return plan

    def change_meal(self, weekday: int, meal_id: int) -> None:
        plan = self.repository.load_plan()
        if plan is None:
            raise PlanningError("plan_missing")
        if not any(meal.id == meal_id for meal in self.eligible(plan.start, weekday)):
            raise PlanningError("invalid_meal")
        if not self.repository.set_meal(weekday, meal_id):
            raise PlanningError("plan_missing")

    def shopping_list(self) -> list[ShoppingItem]:
        plan = self.repository.load_plan()
        if plan is None:
            raise PlanningError("plan_missing")
        fasting = self.repository.fasting_dates(plan.start)
        meals = {meal.id: meal for meal in self.repository.list_meals()}
        totals = {}
        single_rows = {}
        incomplete = []
        for entry in plan.entries:
            meal = meals.get(entry.meal_id)
            if meal is None:
                raise PlanningError("plan_incomplete")
            if not self._eligible(meal, entry.weekday, fasting):
                raise PlanningError("invalid_meal", meal.name)
            rows = self.repository.ingredient_rows(meal.id)
            shopping_rows = [row for row in rows if _normalized_name(row["name"]) not in _SHOPPING_EXCLUSIONS]
            if not rows or any(
                row["posotita"] is None and _SINGLE_ROW_NAMES.get(_normalized_name(row["name"])) != "δυοσμος"
                for row in shopping_rows
            ):
                incomplete.append(meal.name)
                continue
            for row in shopping_rows:
                special_name = _SINGLE_ROW_NAMES.get(_normalized_name(row["name"]))
                if special_name:
                    if special_name not in single_rows:
                        single_rows[special_name] = [row["katigoria"], row["name"], {}]
                    units = single_rows[special_name][2]
                    if row["posotita"] is not None:
                        unit = row["monada_metrisis"]
                        units[unit] = units.get(unit, Decimal("0")) + Decimal(str(row["posotita"]))
                    continue
                key = (
                    row["katigoria"],
                    row["name"].strip().casefold(),
                    row["monada_metrisis"],
                )
                if key not in totals:
                    totals[key] = [
                        row["katigoria"], row["name"], row["monada_metrisis"], Decimal("0")
                    ]
                totals[key][3] += Decimal(str(row["posotita"]))
        if incomplete:
            raise PlanningError("missing_ingredients", ", ".join(dict.fromkeys(incomplete)))
        items = [
            ShoppingItem(name, unit, quantity, category)
            for category, name, unit, quantity in totals.values()
        ]
        for key, (category, name, units) in single_rows.items():
            if key == "δυοσμος" or not units:
                items.append(ShoppingItem(name, "", None, category))
            elif len(units) == 1:
                unit, quantity = next(iter(units.items()))
                items.append(ShoppingItem(name, unit, quantity, category))
            elif "κιλό" in units:
                items.append(ShoppingItem(name, "κιλό", units["κιλό"], category, more_than=True))
            else:
                items.append(ShoppingItem(name, "", None, category))
        return sorted(items, key=lambda item: (CATEGORY_ORDER[item.category], item.name.casefold()))
