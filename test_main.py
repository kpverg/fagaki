import sqlite3
import tempfile
import unittest
from pathlib import Path

from main import WEEKDAYS, initialize_database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database_path = Path(self.directory.name) / "fagaki.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.addCleanup(self.connection.close)

    def test_weekdays_are_seeded_and_initialization_is_repeatable(self):
        initialize_database(self.database_path)
        rows = self.connection.execute(
            "SELECT id, name, isnisteia FROM meres ORDER BY id"
        ).fetchall()
        self.assertEqual(rows, list(WEEKDAYS))

    def test_existing_weekday_changes_are_preserved(self):
        self.connection.execute("UPDATE meres SET isnisteia = 1 WHERE id = 1")
        self.connection.commit()
        initialize_database(self.database_path)
        row = self.connection.execute(
            "SELECT isnisteia FROM meres WHERE id = 1"
        ).fetchone()
        self.assertEqual(row, (1,))

    def test_fasting_periods_and_meals_can_be_saved(self):
        self.connection.execute(
            "INSERT INTO nisteies (dtstart, dtend, paratiriseis) VALUES (?, ?, ?)",
            ("2026-03-01", "2026-03-10", "Χωρίς κρέας"),
        )
        self.connection.execute(
            "INSERT INTO fagaki (name, selectedday, ulika, isnistisimo) "
            "VALUES (?, ?, ?, ?)",
            ("Φακές", "2026-03-04", "φακές, κρεμμύδι", 1),
        )
        self.connection.commit()
        self.assertEqual(
            self.connection.execute(
                "SELECT dtstart, dtend, paratiriseis FROM nisteies"
            ).fetchone(),
            ("2026-03-01", "2026-03-10", "Χωρίς κρέας"),
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT name, selectedday, ulika, isnistisimo FROM fagaki"
            ).fetchone(),
            ("Φακές", "2026-03-04", "φακές, κρεμμύδι", 1),
        )

    def test_boolean_fields_reject_other_values(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("UPDATE meres SET isnisteia = 2 WHERE id = 1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO fagaki (name, selectedday, ulika, isnistisimo) "
                "VALUES (?, ?, ?, ?)",
                ("Φακές", "2026-03-04", "φακές", 2),
            )


if __name__ == "__main__":
    unittest.main()
