import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from services.meal_service import MealService
from utilities.meal import MealData, MealSummary


class MealServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "fagaki.db"
        self.service = MealService(self.path)

    def test_meal_data_round_trip_and_missing_meals(self):
        meal = MealData("Φακές", "φακές, νερό", True, "Βράζουμε", weekday_id=1)
        self.service.add_meal(meal)
        summaries = self.service.list_meals()
        self.assertEqual(len(summaries), 1)
        meal_id = summaries[0].id
        self.assertEqual(summaries, [MealSummary(meal_id, "Φακές", True, 1)])
        self.assertEqual(self.service.get_meal(meal_id), meal)

        updated = MealData("Σούπα", "φακές", False, "Σιγοβράζουμε", weekday_id=2)
        self.assertTrue(self.service.update_meal(meal_id, updated))
        self.assertEqual(self.service.get_meal(meal_id), updated)
        self.assertTrue(self.service.delete_meal(meal_id))
        self.assertIsNone(self.service.get_meal(meal_id))
        self.assertFalse(self.service.update_meal(meal_id, updated))
        self.assertFalse(self.service.delete_meal(meal_id))

    def test_database_errors_are_propagated(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE fagaki")
        with self.assertRaises(sqlite3.OperationalError):
            self.service.list_meals()

    def test_weekday_is_required_and_invalid_ids_are_rejected(self):
        for day in (None, 0, 8):
            with self.subTest(day=day):
                with self.assertRaises(ValueError):
                    self.service.add_meal(MealData("Φακές", "", True, "", weekday_id=day))
        self.assertEqual(self.service.list_meals(), [])


if __name__ == "__main__":
    unittest.main()
