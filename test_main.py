import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from main import WEEKDAYS, initialize_database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database_path = Path(self.directory.name) / "fagaki.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.execute("PRAGMA foreign_keys = ON")
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

    def test_ingredients_and_meals_have_many_to_many_relationship(self):
        self.connection.executemany(
            "INSERT INTO fagaki (id, name, ulika, isnistisimo) VALUES (?, ?, '', 1)",
            [(1, "Φακές"), (2, "Σούπα")],
        )
        self.connection.executemany(
            "INSERT INTO ulika (id, name, monada_metrisis, exoapothema) VALUES (?, ?, ?, ?)",
            [(1, "Κρεμμύδι", "τεμάχιο", 1), (2, "Φακές", "κιλό", 0)],
        )
        self.connection.executemany(
            "INSERT INTO fagaki_ulika (fagaki_id, ulika_id, posotita) VALUES (?, ?, ?)",
            [(1, 1, 2), (1, 2, 0.5), (2, 1, 1)],
        )
        self.connection.commit()
        initialize_database(self.database_path)
        self.assertEqual(
            self.connection.execute(
                "SELECT fagaki_id, ulika_id, posotita FROM fagaki_ulika "
                "ORDER BY fagaki_id, ulika_id"
            ).fetchall(),
            [(1, 1, 2), (1, 2, 0.5), (2, 1, 1)],
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO fagaki_ulika (fagaki_id, ulika_id) VALUES (1, 1)"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO fagaki_ulika (fagaki_id, ulika_id) VALUES (1, 999)"
            )
        for invalid in (0, -1, "πολύ"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.connection.execute(
                    "UPDATE fagaki_ulika SET posotita = ? WHERE fagaki_id = 1 AND ulika_id = 1",
                    (invalid,),
                )
        self.connection.execute("DELETE FROM fagaki WHERE id = 1")
        self.assertEqual(
            self.connection.execute("SELECT fagaki_id, ulika_id FROM fagaki_ulika").fetchall(),
            [(2, 1)],
        )
        self.connection.execute("DELETE FROM ulika WHERE id = 1")
        self.assertEqual(self.connection.execute("SELECT * FROM fagaki_ulika").fetchall(), [])

    def test_existing_ingredient_links_are_migrated_without_losing_data(self):
        old_path = Path(self.directory.name) / "old_ingredients.db"
        with closing(sqlite3.connect(old_path)) as connection, connection:
            connection.execute(
                "CREATE TABLE fagaki (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "selectedday TEXT, ulika TEXT NOT NULL, isnistisimo INTEGER NOT NULL, "
                "syntagi TEXT NOT NULL DEFAULT '', imera_id INTEGER)"
            )
            connection.execute(
                "CREATE TABLE ulika (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "monada_metrisis TEXT NOT NULL, exoapothema INTEGER NOT NULL DEFAULT 0)"
            )
            connection.execute(
                "CREATE TABLE fagaki_ulika (fagaki_id INTEGER NOT NULL REFERENCES fagaki(id), "
                "ulika_id INTEGER NOT NULL REFERENCES ulika(id), "
                "PRIMARY KEY (fagaki_id, ulika_id))"
            )
            connection.execute("INSERT INTO fagaki (id, name, ulika, isnistisimo) "
                               "VALUES (1, 'Φακές', '', 1)")
            connection.execute("INSERT INTO ulika (id, name, monada_metrisis) "
                               "VALUES (1, 'Φακές', 'κιλό')")
            connection.execute("INSERT INTO fagaki_ulika VALUES (1, 1)")
        initialize_database(old_path)
        initialize_database(old_path)
        with closing(sqlite3.connect(old_path)) as connection, connection:
            self.assertEqual(
                connection.execute("SELECT fagaki_id, ulika_id, posotita FROM fagaki_ulika")
                .fetchall(),
                [(1, 1, None)],
            )
            connection.execute("UPDATE fagaki_ulika SET posotita = 0.5")
        initialize_database(old_path)
        with closing(sqlite3.connect(old_path)) as connection:
            self.assertEqual(connection.execute("SELECT posotita FROM fagaki_ulika").fetchone(),
                             (0.5,))

    def test_ingredient_units_and_stock_are_constrained(self):
        for unit in ("τεμάχιο", "συσκευασία", "κιλό"):
            self.connection.execute(
                "INSERT INTO ulika (name, monada_metrisis) VALUES (?, ?)",
                ("Υλικό", unit),
            )
        self.assertEqual(
            self.connection.execute("SELECT exoapothema FROM ulika").fetchall(),
            [(0,), (0,), (0,)],
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO ulika (name, monada_metrisis) VALUES ('Υλικό', 'λίτρο')"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO ulika (name, monada_metrisis, exoapothema) "
                "VALUES ('Υλικό', 'κιλό', 2)"
            )

    def test_existing_database_is_migrated_without_losing_meals(self):
        old_path = Path(self.directory.name) / "old.db"
        with closing(sqlite3.connect(old_path)) as connection, connection:
            connection.execute(
                "CREATE TABLE fagaki (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "selectedday TEXT NOT NULL, ulika TEXT NOT NULL, "
                "isnistisimo INTEGER NOT NULL CHECK (isnistisimo IN (0, 1)))"
            )
            connection.execute(
                "INSERT INTO fagaki VALUES (1, 'Φακές', '2026-03-04', 'φακές', 1)"
            )
        initialize_database(old_path)
        initialize_database(old_path)
        with closing(sqlite3.connect(old_path)) as connection, connection:
            self.assertEqual(
                connection.execute(
                    "SELECT id, name, selectedday, ulika, isnistisimo, syntagi FROM fagaki"
                ).fetchone(),
                (1, "Φακές", "2026-03-04", "φακές", 1, ""),
            )
            connection.execute(
                "INSERT INTO fagaki (name, ulika, isnistisimo, syntagi) "
                "VALUES ('Ρύζι', 'ρύζι', 1, 'Βράσιμο')"
            )
            self.assertIsNone(connection.execute(
                "SELECT selectedday FROM fagaki WHERE name = 'Ρύζι'"
            ).fetchone()[0])

    def test_existing_nullable_database_gains_weekday_and_preserves_meals(self):
        old_path = Path(self.directory.name) / "nullable.db"
        with closing(sqlite3.connect(old_path)) as connection, connection:
            connection.execute(
                "CREATE TABLE fagaki (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "selectedday TEXT, ulika TEXT NOT NULL, isnistisimo INTEGER NOT NULL, "
                "syntagi TEXT NOT NULL DEFAULT '')"
            )
            connection.execute(
                "INSERT INTO fagaki (name, ulika, isnistisimo) VALUES ('Φακές', '', 1)"
            )
        initialize_database(old_path)
        initialize_database(old_path)
        with closing(sqlite3.connect(old_path)) as connection, connection:
            connection.execute("UPDATE fagaki SET imera_id = 3 WHERE name = 'Φακές'")
            self.assertEqual(
                connection.execute(
                    "SELECT name, selectedday, imera_id FROM fagaki"
                ).fetchone(),
                ("Φακές", None, 3),
            )

    def test_migration_refuses_to_drop_custom_indexes(self):
        old_path = Path(self.directory.name) / "custom.db"
        with closing(sqlite3.connect(old_path)) as connection, connection:
            connection.execute(
                "CREATE TABLE fagaki (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "selectedday TEXT NOT NULL, ulika TEXT NOT NULL, isnistisimo INTEGER NOT NULL)"
            )
            connection.execute("CREATE INDEX custom_index ON fagaki(name)")
        with self.assertRaises(sqlite3.DatabaseError):
            initialize_database(old_path)
        with closing(sqlite3.connect(old_path)) as connection, connection:
            self.assertIsNotNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'custom_index'"
            ).fetchone())
            self.assertIsNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'fagaki_new'"
            ).fetchone())


if __name__ == "__main__":
    unittest.main()
