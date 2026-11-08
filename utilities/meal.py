from dataclasses import dataclass

from utilities.ingredients import Ingredient


@dataclass(frozen=True)
class MealData:
    name: str
    ingredients: str
    is_fasting: bool
    recipe: str
    ingredient_items: tuple[Ingredient, ...] | None = None
    weekday_id: int | None = None


@dataclass(frozen=True)
class MealSummary:
    id: int
    name: str
    is_fasting: bool
    weekday_id: int | None = None


@dataclass(frozen=True)
class Weekday:
    id: int
    name: str
