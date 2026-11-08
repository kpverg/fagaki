from pathlib import Path

from dbservices.database import initialize_database
from dbservices.meal_repository import MealRepository
from utilities.meal import MealData, MealSummary, Weekday


class MealService:
    def __init__(self, database_path: str | Path):
        initialize_database(database_path)
        self.repository = MealRepository(database_path)
        self.repository.convert_legacy_ingredients()

    def list_meals(self) -> list[MealSummary]:
        return self.repository.list_meals()

    def list_weekdays(self) -> list[Weekday]:
        return self.repository.list_weekdays()

    def get_meal(self, meal_id: int) -> MealData | None:
        return self.repository.get_meal(meal_id)

    def add_meal(self, meal: MealData) -> None:
        self.repository.add_meal(meal)

    def update_meal(self, meal_id: int, meal: MealData) -> bool:
        return self.repository.update_meal(meal_id, meal)

    def delete_meal(self, meal_id: int) -> bool:
        return self.repository.delete_meal(meal_id)

    def list_ingredients(self):
        return self.repository.list_ingredients()
