import sqlite3
import math
from contextlib import closing
from pathlib import Path

from utilities.ingredients import (
    CATEGORIES, Ingredient, UNITS, parse_legacy_ingredients, parse_recipe_ingredients,
)
from utilities.meal import MealData, MealSummary, Weekday


class MealRepository:
    def __init__(self, database_path: str | Path):
        self.database_path = database_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection

    def list_meals(self) -> list[MealSummary]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT id, name, isnistisimo, imera_id FROM fagaki ORDER BY name, id"
            ).fetchall()
        return [MealSummary(row["id"], row["name"], bool(row["isnistisimo"]), row["imera_id"])
                for row in rows]

    def list_weekdays(self) -> list[Weekday]:
        with closing(self.connect()) as connection:
            rows = connection.execute("SELECT id, name FROM meres ORDER BY id").fetchall()
        return [Weekday(row["id"], row["name"]) for row in rows]

    def get_meal(self, meal_id: int) -> MealData | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT name, ulika, isnistisimo, syntagi, imera_id FROM fagaki WHERE id = ?",
                (meal_id,),
            ).fetchone()
            ingredient_rows = connection.execute(
                "SELECT u.id, u.name, COALESCE(NULLIF(f.monada_metrisis, ''), u.monada_metrisis), "
                "f.posotita, u.katigoria "
                "FROM fagaki_ulika f JOIN ulika u ON u.id = f.ulika_id "
                "WHERE f.fagaki_id = ? ORDER BY u.name, u.id",
                (meal_id,),
            ).fetchall()
        if row is None:
            return None
        ingredients = tuple(Ingredient(*item) for item in ingredient_rows) or None
        return MealData(row["name"], row["ulika"], bool(row["isnistisimo"]),
                        row["syntagi"], ingredients, row["imera_id"])

    def add_meal(self, meal: MealData) -> None:
        self._validate_weekday(meal.weekday_id)
        with closing(self.connect()) as connection, connection:
            result = connection.execute(
                "INSERT INTO fagaki (name, ulika, isnistisimo, syntagi, imera_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (meal.name, meal.ingredients, int(meal.is_fasting), meal.recipe, meal.weekday_id),
            )
            if meal.ingredient_items is not None:
                self._save_ingredients(connection, result.lastrowid, meal.ingredient_items)
            else:
                self._convert_legacy_ingredients(connection, result.lastrowid)

    def update_meal(self, meal_id: int, meal: MealData) -> bool:
        self._validate_weekday(meal.weekday_id)
        with closing(self.connect()) as connection, connection:
            result = connection.execute(
                "UPDATE fagaki SET name = ?, ulika = ?, isnistisimo = ?, syntagi = ?, imera_id = ? "
                "WHERE id = ?",
                (meal.name, meal.ingredients, int(meal.is_fasting), meal.recipe,
                 meal.weekday_id, meal_id),
            )
            if result.rowcount and meal.ingredient_items is not None:
                self._save_ingredients(connection, meal_id, meal.ingredient_items)
            elif result.rowcount:
                self._convert_legacy_ingredients(connection, meal_id)
            return result.rowcount != 0

    @staticmethod
    def _validate_weekday(weekday_id: int | None) -> None:
        if weekday_id is None or weekday_id not in range(1, 8):
            raise ValueError("A valid weekday is required")

    def delete_meal(self, meal_id: int) -> bool:
        with closing(self.connect()) as connection, connection:
            result = connection.execute("DELETE FROM fagaki WHERE id = ?", (meal_id,))
            return result.rowcount != 0

    def list_ingredients(self) -> list[Ingredient]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT id, name, monada_metrisis, NULL, katigoria "
                "FROM ulika ORDER BY name, id"
            ).fetchall()
        return [Ingredient(*row) for row in rows]

    @staticmethod
    def _save_ingredients(connection, meal_id: int, ingredients: tuple[Ingredient, ...]) -> None:
        connection.execute("DELETE FROM fagaki_ulika WHERE fagaki_id = ?", (meal_id,))
        connection.execute("INSERT OR IGNORE INTO ingredient_processing (meal_id) VALUES (?)", (meal_id,))
        all_ingredients = connection.execute(
            "SELECT id, name, monada_metrisis, katigoria FROM ulika"
        ).fetchall()
        used = set()
        for item in ingredients:
            if not item.name.strip() or item.unit not in UNITS:
                raise ValueError("Invalid ingredient name or unit")
            if item.category not in CATEGORIES:
                raise ValueError(f"Invalid ingredient category: {item.name}")
            if item.quantity is not None and (
                not math.isfinite(item.quantity) or item.quantity <= 0
            ):
                raise ValueError(f"Invalid ingredient quantity: {item.name}")
            if item.id is None:
                matches = [row for row in all_ingredients if row["name"].casefold() == item.name.casefold()]
                if matches:
                    if len(matches) != 1:
                        raise ValueError(f"Ambiguous ingredient: {item.name}")
                    ingredient_id = matches[0]["id"]
                else:
                    result = connection.execute(
                        "INSERT INTO ulika (name, monada_metrisis, katigoria) VALUES (?, ?, ?)",
                        (item.name, item.unit, item.category),
                    )
                    ingredient_id = result.lastrowid
                    all_ingredients = connection.execute(
                        "SELECT id, name, monada_metrisis, katigoria FROM ulika"
                    ).fetchall()
            else:
                ingredient_id = item.id
                if not any(row["id"] == item.id for row in all_ingredients):
                    raise ValueError(f"Ingredient no longer exists: {item.name}")
                if item.category not in CATEGORIES:
                    raise ValueError(f"Invalid ingredient category: {item.name}")
            key = (ingredient_id, item.unit)
            if key in used:
                raise ValueError(f"Duplicate ingredient: {item.name}")
            used.add(key)
            connection.execute(
                "UPDATE ulika SET katigoria = ? WHERE id = ?",
                (item.category, ingredient_id),
            )
            connection.execute(
                "INSERT INTO fagaki_ulika (fagaki_id, ulika_id, posotita, monada_metrisis) "
                "VALUES (?, ?, ?, ?)",
                (meal_id, ingredient_id, item.quantity, item.unit),
            )

    def convert_legacy_ingredients(self) -> None:
        with closing(self.connect()) as connection, connection:
            self._convert_legacy_ingredients(connection)

    @classmethod
    def _convert_legacy_ingredients(cls, connection, meal_id: int | None = None) -> None:
        rows = connection.execute(
            "SELECT id, ulika FROM fagaki WHERE trim(ulika) <> '' "
            "AND (? IS NULL OR id = ?) "
            "AND NOT EXISTS (SELECT 1 FROM fagaki_ulika WHERE fagaki_id = fagaki.id) "
            "AND NOT EXISTS (SELECT 1 FROM ingredient_processing WHERE meal_id = fagaki.id)",
            (meal_id, meal_id),
        ).fetchall()
        existing = connection.execute(
            "SELECT id, name, monada_metrisis, katigoria FROM ulika"
        ).fetchall()
        for row in rows:
            items = parse_legacy_ingredients(row["ulika"])
            if items is None:
                items = parse_recipe_ingredients(row["ulika"])
            if items is None:
                continue
            ambiguous = False
            for item in items:
                matches = [entry for entry in existing
                           if entry["name"].casefold() == item.name.casefold()]
                if len(matches) > 1:
                    ambiguous = True
                    break
            if ambiguous:
                continue
            cls._save_ingredients(connection, row["id"], items)
            existing = connection.execute(
                "SELECT id, name, monada_metrisis, katigoria FROM ulika"
            ).fetchall()
