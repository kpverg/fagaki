import sqlite3
from contextlib import closing
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().with_name("fagaki.db")

WEEKDAYS = (
    (1, "Δευτέρα", 0),
    (2, "Τρίτη", 0),
    (3, "Τετάρτη", 1),
    (4, "Πέμπτη", 0),
    (5, "Παρασκευή", 1),
    (6, "Σάββατο", 0),
    (7, "Κυριακή", 0),
)


def initialize_database(database_path: str | Path = DATABASE_PATH) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS meres (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    isnisteia INTEGER NOT NULL CHECK (isnisteia IN (0, 1))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS nisteies (
                    id INTEGER PRIMARY KEY,
                    dtstart TEXT NOT NULL,
                    dtend TEXT NOT NULL,
                    paratiriseis TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS fagaki (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    selectedday TEXT,
                    ulika TEXT NOT NULL,
                    isnistisimo INTEGER NOT NULL CHECK (isnistisimo IN (0, 1)),
                    syntagi TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = {
                row[1]: row
                for row in connection.execute("PRAGMA table_info(fagaki)")
            }
            if columns["selectedday"][3]:
                connection.execute(
                    """
                    CREATE TABLE fagaki_new (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        selectedday TEXT,
                        ulika TEXT NOT NULL,
                        isnistisimo INTEGER NOT NULL CHECK (isnistisimo IN (0, 1)),
                        syntagi TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
                recipe = "syntagi" if "syntagi" in columns else "''"
                connection.execute(
                    "INSERT INTO fagaki_new "
                    "(id, name, selectedday, ulika, isnistisimo, syntagi) "
                    f"SELECT id, name, selectedday, ulika, isnistisimo, {recipe} "
                    "FROM fagaki"
                )
                connection.execute("DROP TABLE fagaki")
                connection.execute("ALTER TABLE fagaki_new RENAME TO fagaki")
            elif "syntagi" not in columns:
                connection.execute(
                    "ALTER TABLE fagaki ADD COLUMN syntagi TEXT NOT NULL DEFAULT ''"
                )
            connection.executemany(
                "INSERT OR IGNORE INTO meres (id, name, isnisteia) VALUES (?, ?, ?)",
                WEEKDAYS,
            )


if __name__ == "__main__":
    from ui import run

    run()