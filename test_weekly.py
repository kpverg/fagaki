import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from services.meal_service import MealService
from services.weekly_service import WeeklyService
from utilities.ingredients import (
    Ingredient, ShoppingItem, parse_legacy_ingredients, parse_recipe_ingredients,
)
from utilities.meal import MealData
from utilities.weekly_plan import PlanningError


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "fagaki.db"
        self.meals = MealService(self.path)
        self.week = WeeklyService(self.path)

    def add_meal(self, name, fasting, items, weekday=1):
        self.meals.add_meal(MealData(name, "", fasting, "", tuple(items), weekday))
        return next(meal.id for meal in self.meals.list_meals() if meal.name == name)

    def add_for_all_days(self, name, fasting, items):
        return {day: self.add_meal(f"{name} {day}", fasting, items, day)
                for day in range(1, 8)}

    def test_create_respects_weekdays_fasting_and_extra_periods(self):
        fasting_ids = self.add_for_all_days("Νηστίσιμο", True, [Ingredient(None, "Φακές", "κιλό", 0.5)])
        self.add_for_all_days("Κρέας", False, [Ingredient(None, "Κρέας", "κιλό", 1)])
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO nisteies (dtstart, dtend) VALUES (?, ?)",
                ("2026-03-02", "2026-03-03"),
            )
        with patch("services.weekly_service.random.choice", side_effect=lambda values: values[0]):
            plan = self.week.create(date(2026, 3, 4))
        self.assertEqual(plan.start, date(2026, 3, 2))
        self.assertEqual(len(plan.entries), 7)
        meals = {meal.id: meal for meal in self.meals.list_meals()}
        for entry in plan.entries:
            self.assertEqual(meals[entry.meal_id].weekday_id, entry.weekday)
        for day in (1, 2, 3, 5):
            self.assertEqual(plan.entries[day - 1].meal_id, fasting_ids[day])
        self.assertEqual(self.week.load(), plan)

    def test_only_assigned_day_is_eligible_for_automatic_and_manual_selection(self):
        ids = self.add_for_all_days("Συνταγή", True, [Ingredient(None, "Ρύζι", "κιλό", 1)])
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO fagaki (name, ulika, isnistisimo, imera_id) VALUES (?, '', 1, NULL)",
                ("Χωρίς ημέρα",),
            )
        self.assertEqual([meal.id for meal in self.week.eligible(date(2026, 3, 2), 1)], [ids[1]])
        plan = self.week.create(date(2026, 3, 2))
        self.assertEqual([entry.meal_id for entry in plan.entries], [ids[day] for day in range(1, 8)])
        with self.assertRaises(PlanningError) as error:
            self.week.change_meal(1, ids[2])
        self.assertEqual(error.exception.reason, "invalid_meal")
        self.assertEqual(self.week.load(), plan)

    def test_day_change_invalidates_existing_plan_without_overwriting_it(self):
        ids = self.add_for_all_days("Συνταγή", True, [Ingredient(None, "Ρύζι", "κιλό", 1)])
        plan = self.week.create(date(2026, 3, 2))
        meal = self.meals.get_meal(ids[1])
        self.meals.update_meal(ids[1], MealData(
            meal.name, meal.ingredients, meal.is_fasting, meal.recipe, weekday_id=2
        ))
        self.assertEqual(self.week.load(), plan)
        with self.assertRaises(PlanningError) as error:
            self.week.shopping_list()
        self.assertEqual(error.exception.reason, "invalid_meal")
        with self.assertRaises(PlanningError) as error:
            self.week.create(date(2026, 3, 9))
        self.assertEqual(error.exception.reason, "no_eligible_meals")
        self.assertEqual(error.exception.details, "1")
        self.assertEqual(self.week.load(), plan)

    def test_aggregate_quantities_and_manual_changes(self):
        first = self.add_for_all_days("Α", True, [Ingredient(None, "Φακές", "κιλό", 0.1)])
        second = self.add_for_all_days("Β", True, [
            Ingredient(None, "Φακές", "κιλό", 0.2),
            Ingredient(None, "Κρεμμύδι", "τεμάχιο", 2),
        ])
        self.week.create(date(2026, 3, 2))
        for day in range(1, 8):
            self.week.change_meal(day, first[day] if day <= 3 else second[day])
        self.assertEqual(self.week.shopping_list(), [
            ShoppingItem("Κρεμμύδι", "τεμάχιο", Decimal("8.0")),
            ShoppingItem("Φακές", "κιλό", Decimal("1.1")),
        ])
        self.assertEqual(WeeklyService(self.path).load().entries[0].meal_id, first[1])

    def test_missing_meals_and_ingredients_are_reported(self):
        for day in range(1, 8):
            self.meals.add_meal(MealData(f"Α {day}", "φακές", True, "", weekday_id=day))
        with self.assertRaises(PlanningError) as error:
            self.week.shopping_list()
        self.assertEqual(error.exception.reason, "plan_missing")
        self.week.create(date(2026, 3, 2))
        with self.assertRaises(PlanningError) as error:
            self.week.shopping_list()
        self.assertEqual(error.exception.reason, "missing_ingredients")
        self.meals.delete_meal(self.meals.list_meals()[0].id)
        with self.assertRaises(PlanningError) as error:
            self.week.shopping_list()
        self.assertEqual(error.exception.reason, "plan_incomplete")

    def test_pantry_staples_are_excluded_only_from_shopping(self):
        names = [
            "ΝΕΡΟ", "Ρίγανη", "αποξηραμένη ρίγανη", "Αλάτι", "Πιπέρι",
            "Ελαιόλαδο", "ζάχαρη", "πρέζα κρυσταλλική ζάχαρη",
        ]
        ingredients = [Ingredient(None, name, "τεμάχιο", None) for name in names]
        ingredients.extend([
            Ingredient(None, "πιπεριά", "τεμάχιο", 2),
            Ingredient(None, "πιπεριά Φλωρίνης σε βαζάκι", "τεμάχιο", 1),
            Ingredient(None, "ρύζι", "κιλό", 0.5),
        ])
        ids = self.add_for_all_days("Συνταγή", True, ingredients)
        original = self.meals.get_meal(ids[1]).ingredient_items
        self.week.create(date(2026, 3, 2))
        shopping = self.week.shopping_list()
        self.assertEqual({item.name for item in shopping}, {
            "πιπεριά", "πιπεριά Φλωρίνης σε βαζάκι", "ρύζι",
        })
        self.assertEqual(next(item.quantity for item in shopping if item.name == "ρύζι"),
                         Decimal("3.5"))
        self.assertEqual(self.meals.get_meal(ids[1]).ingredient_items, original)

    def test_recipe_with_only_excluded_ingredients_is_complete(self):
        self.add_for_all_days("Νερό", True, [Ingredient(None, "νερό", "λίτρο", None)])
        self.week.create(date(2026, 3, 2))
        self.assertEqual(self.week.shopping_list(), [])

    def test_missing_quantity_for_shopping_ingredient_is_still_reported(self):
        self.add_for_all_days("Συνταγή", True, [
            Ingredient(None, "αλάτι", "τεμάχιο", None),
            Ingredient(None, "φακές", "κιλό", None),
        ])
        self.week.create(date(2026, 3, 2))
        with self.assertRaises(PlanningError) as error:
            self.week.shopping_list()
        self.assertEqual(error.exception.reason, "missing_ingredients")

    def test_failed_creation_does_not_replace_plan_and_manual_fasting_is_checked(self):
        fasting_ids = self.add_for_all_days("Α", True, [Ingredient(None, "Ρύζι", "κιλό", 1)])
        normal_ids = self.add_for_all_days("Β", False, [Ingredient(None, "Τυρί", "κιλό", 1)])
        original = self.week.create(date(2026, 3, 2))
        with self.assertRaises(PlanningError) as error:
            self.week.change_meal(3, normal_ids[3])
        self.assertEqual(error.exception.reason, "invalid_meal")
        self.assertEqual(self.week.load(), original)
        self.meals.update_meal(fasting_ids[3], MealData("Α 3", "", False, "", weekday_id=3))
        with self.assertRaises(PlanningError) as error:
            self.week.create(date(2026, 3, 9))
        self.assertEqual(error.exception.reason, "no_eligible_meals")
        self.assertEqual(self.week.load(), original)
        with self.assertRaises(PlanningError) as error:
            self.week.shopping_list()
        self.assertEqual(error.exception.reason, "invalid_meal")

    def test_legacy_conversion_is_safe_and_does_not_repeat_after_manual_removal(self):
        self.meals.add_meal(MealData("A", "kremidi ,1, temaxia    fakes,1 kila,", True, "", weekday_id=1))
        self.meals.add_meal(MealData("B", "φακές, νερό", True, "", weekday_id=2))
        a = next(meal.id for meal in self.meals.list_meals() if meal.name == "A")
        b = next(meal.id for meal in self.meals.list_meals() if meal.name == "B")
        self.assertEqual(len(self.meals.get_meal(a).ingredient_items), 2)
        self.assertIsNone(self.meals.get_meal(b).ingredient_items)
        self.meals.update_meal(a, MealData("A", "kremidi ,1, temaxia    fakes,1 kila,", True, "", (), 1))
        reloaded = MealService(self.path)
        self.assertIsNone(reloaded.get_meal(a).ingredient_items)
        self.assertEqual(reloaded.get_meal(b).ingredients, "φακές, νερό")

    def test_existing_legacy_recipe_converts_at_startup_without_changing_original_text(self):
        legacy = "kremidi ,1, temaxia    fakes,1 kila,"
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO fagaki (name, ulika, isnistisimo) VALUES (?, ?, ?)",
                ("Old", legacy, 1),
            )
        reloaded = MealService(self.path)
        meal_id = reloaded.list_meals()[0].id
        meal = reloaded.get_meal(meal_id)
        self.assertEqual(meal.ingredients, legacy)
        self.assertEqual(len(meal.ingredient_items), 2)
        reloaded = MealService(self.path)
        self.assertEqual(reloaded.get_meal(meal_id), meal)
        self.assertEqual(len(reloaded.list_ingredients()), 2)

    def test_parser_refuses_unknown_and_nonpositive_values(self):
        self.assertIsNotNone(parse_legacy_ingredients("φακές, 0,5 κιλά, κρεμμύδι, 2 τεμάχια"))
        for value in ("φακές, νερό", "φακές, 0 κιλά",
                      "φακές, 1 κιλό, φακές, 2 κιλά"):
            self.assertIsNone(parse_legacy_ingredients(value))

    def test_parser_does_not_consume_part_of_a_unit_or_ingredient(self):
        parsed = parse_recipe_ingredients(
            "1 κιλό πατάτες\n1 λίτρο νερό\n2 αυγά\n1 φύλλο δάφνης\n"
            "1/2 κιλό κολοκυθάκια\n1/4 κ.γ. κανέλα"
        )
        self.assertEqual([(item.name, item.unit, item.quantity) for item in parsed], [
            ("πατάτες", "κιλό", 1),
            ("νερό", "λίτρο", 1),
            ("αυγά", "τεμάχιο", 2),
            ("φύλλο δάφνης", "τεμάχιο", 1),
            ("κολοκυθάκια", "κιλό", 0.5),
            ("κανέλα", "κ.γ.", 0.25),
        ])

    def test_recipe_section_headings_are_not_ingredients(self):
        parsed = parse_recipe_ingredients(
            "ΥΛΙΚΑ ΓΙΑ ΤΑ ΜΠΙΦΤΕΚΙΑ\n500 γρ. κιμάς\n"
            "ΓΙΑ ΤΗ ΣΑΛΤΣΑ\n1 ντομάτα\n"
            "Για τον πουρέ:\n2 πατάτες\n"
            "ΓΙΑ ΤΟ ΡΥΖΙ\n1 κιλό ρύζι\n"
            "1 γιαούρτι\nΦέτα για το σερβίρισμα"
        )
        self.assertEqual([item.name for item in parsed], [
            "κιμάς", "ντομάτα", "πατάτες", "ρύζι", "γιαούρτι",
            "Φέτα για το σερβίρισμα",
        ])
        self.assertIsNone(parse_recipe_ingredients("ΓΙΑ ΤΟ ΡΥΖΙ\nΓΙΑ ΤΗ ΣΑΛΤΣΑ"))

    def test_invalid_ingredient_update_rolls_back_recipe_and_links(self):
        meal_id = self.add_meal("Α", True, [Ingredient(None, "Ρύζι", "κιλό", 1)])
        before = self.meals.get_meal(meal_id)
        with self.assertRaises(ValueError):
            self.meals.update_meal(meal_id, MealData("Changed", "", True, "", (
                Ingredient(None, "Ρύζι", "κιλό", 1),
                Ingredient(None, "Ρύζι", "κιλό", 2),
            ), 1))
        self.assertEqual(self.meals.get_meal(meal_id), before)

    def test_same_ingredient_with_different_units_uses_one_ingredient(self):
        self.add_meal("Existing", True, [Ingredient(None, "Ρύζι", "κιλό", 1)])
        self.meals.add_meal(MealData("Legacy", "Ρύζι, 2, τεμάχια", True, "", weekday_id=1))
        legacy_id = next(meal.id for meal in self.meals.list_meals() if meal.name == "Legacy")
        self.assertEqual(self.meals.get_meal(legacy_id).ingredient_items[0].unit, "τεμάχιο")
        self.assertEqual(len(self.meals.list_ingredients()), 1)

    def test_same_ingredient_can_have_multiple_units_in_one_recipe(self):
        ids = self.add_for_all_days("Α", True, [
            Ingredient(None, "Αλεύρι", "κιλό", 0.5),
            Ingredient(None, "Αλεύρι", "κ.σ.", 2),
        ])
        self.assertEqual(len(self.meals.list_ingredients()), 1)
        items = self.meals.get_meal(ids[1]).ingredient_items
        self.assertEqual({(item.unit, item.quantity) for item in items},
                         {("κιλό", 0.5), ("κ.σ.", 2)})
        self.assertEqual(len({item.id for item in items}), 1)
        self.week.create(date(2026, 3, 2))
        self.assertEqual(self.week.shopping_list(), [
            ShoppingItem("Αλεύρι", "κιλό", Decimal("3.5"), more_than=True),
        ])
        self.meals.update_meal(ids[1], MealData("Α 1", "", True, "", items, 1))
        self.assertEqual(self.meals.get_meal(ids[1]).ingredient_items, items)

    def test_selected_ingredients_appear_once_without_changing_recipes(self):
        ids = self.add_for_all_days("Α", True, [
            Ingredient(None, "Πατάτες", "κιλό", 1, "λαχανικά"),
            Ingredient(None, "Πατάτες", "τεμάχιο", 2, "λαχανικά"),
            Ingredient(None, "Δυόσμος", "κιλό", 0.1),
            Ingredient(None, "Δυόσμος", "τεμάχιο", None),
            Ingredient(None, "Αλεύρι", "τεμάχιο", 1),
            Ingredient(None, "Αλεύρι", "κ.σ.", 2),
            Ingredient(None, "γλυκοπατάτες", "κιλό", 1, "λαχανικά"),
        ])
        original = self.meals.get_meal(ids[1]).ingredient_items
        self.week.create(date(2026, 3, 2))
        items = {item.name: item for item in self.week.shopping_list()}
        self.assertEqual(items["Πατάτες"], ShoppingItem(
            "Πατάτες", "κιλό", Decimal("7"), "λαχανικά", more_than=True,
        ))
        self.assertEqual(items["Αλεύρι"], ShoppingItem("Αλεύρι", "", None))
        self.assertEqual(items["Δυόσμος"], ShoppingItem("Δυόσμος", "", None))
        self.assertEqual(items["γλυκοπατάτες"].quantity, Decimal("7"))
        self.assertEqual(self.meals.get_meal(ids[1]).ingredient_items, original)

    def test_single_unit_preserved_for_potatoes(self):
        self.add_for_all_days("Α", True, [Ingredient(None, "πατάτες", "τεμάχιο", 2)])
        self.week.create(date(2026, 3, 2))
        self.assertEqual(self.week.shopping_list(),
                         [ShoppingItem("πατάτες", "τεμάχιο", Decimal("14"))])

    def test_equal_ingredients_are_combined_but_units_are_separate(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executemany(
                "INSERT INTO ulika (id, name, monada_metrisis) VALUES (?, ?, ?)",
                [(1, "Ρύζι", "κιλό"), (2, "ΡΎΖΙ", "κιλό"), (3, "Ρύζι", "τεμάχιο")],
            )
        self.add_for_all_days("Α", True, [
            Ingredient(1, "Ρύζι", "κιλό", 0.1),
            Ingredient(2, "ΡΎΖΙ", "κιλό", 0.2),
            Ingredient(3, "Ρύζι", "τεμάχιο", 1),
        ])
        self.week.create(date(2026, 3, 2))
        items = self.week.shopping_list()
        self.assertEqual({(item.unit, item.quantity) for item in items},
                         {("κιλό", Decimal("2.1")), ("τεμάχιο", Decimal("7"))})


if __name__ == "__main__":
    unittest.main()
