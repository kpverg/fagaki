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
            connection.execute("BEGIN")
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
                    syntagi TEXT NOT NULL DEFAULT '',
                    imera_id INTEGER REFERENCES meres(id)
                )
                """
            )
            columns = {
                row[1]: row
                for row in connection.execute("PRAGMA table_info(fagaki)")
            }
            if columns["selectedday"][3]:
                expected_columns = {
                    "id", "name", "selectedday", "ulika", "isnistisimo", "syntagi", "imera_id"
                }
                extra_columns = columns.keys() - expected_columns
                extra_objects = connection.execute(
                    "SELECT name FROM sqlite_master WHERE tbl_name = 'fagaki' "
                    "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
                ).fetchall()
                if extra_columns or extra_objects:
                    raise sqlite3.DatabaseError(
                        "Δεν είναι δυνατή η αναβάθμιση του πίνακα fagaki: "
                        "υπάρχουν επιπλέον στήλες, ευρετήρια ή triggers."
                    )
                connection.execute(
                    """
                    CREATE TABLE fagaki_new (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        selectedday TEXT,
                        ulika TEXT NOT NULL,
                        isnistisimo INTEGER NOT NULL CHECK (isnistisimo IN (0, 1)),
                        syntagi TEXT NOT NULL DEFAULT '',
                        imera_id INTEGER REFERENCES meres(id)
                    )
                    """
                )
                recipe = "syntagi" if "syntagi" in columns else "''"
                weekday = "imera_id" if "imera_id" in columns else "NULL"
                connection.execute(
                    "INSERT INTO fagaki_new "
                    "(id, name, selectedday, ulika, isnistisimo, syntagi, imera_id) "
                    f"SELECT id, name, selectedday, ulika, isnistisimo, {recipe}, {weekday} "
                    "FROM fagaki"
                )
                connection.execute("DROP TABLE fagaki")
                connection.execute("ALTER TABLE fagaki_new RENAME TO fagaki")
            elif "syntagi" not in columns:
                connection.execute(
                    "ALTER TABLE fagaki ADD COLUMN syntagi TEXT NOT NULL DEFAULT ''"
                )
            if not columns["selectedday"][3] and "imera_id" not in columns:
                connection.execute(
                    "ALTER TABLE fagaki ADD COLUMN imera_id INTEGER REFERENCES meres(id)"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ulika (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    monada_metrisis TEXT NOT NULL
                        CHECK (monada_metrisis IN ('τεμάχιο', 'συσκευασία', 'κιλό')),
                    exoapothema INTEGER NOT NULL DEFAULT 0 CHECK (exoapothema IN (0, 1))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS fagaki_ulika (
                    fagaki_id INTEGER NOT NULL REFERENCES fagaki(id) ON DELETE CASCADE,
                    ulika_id INTEGER NOT NULL REFERENCES ulika(id) ON DELETE CASCADE,
                    posotita REAL CHECK (
                        posotita IS NULL OR
                        (typeof(posotita) IN ('integer', 'real') AND posotita > 0)
                    ),
                    PRIMARY KEY (fagaki_id, ulika_id)
                )
                """
            )
            ingredient_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(fagaki_ulika)")
            }
            if "posotita" not in ingredient_columns:
                connection.execute(
                    "ALTER TABLE fagaki_ulika ADD COLUMN posotita REAL CHECK "
                    "(posotita IS NULL OR "
                    "(typeof(posotita) IN ('integer', 'real') AND posotita > 0))"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS fagaki_ulika_ulika_id ON fagaki_ulika (ulika_id)"
            )
            connection.executemany(
                "INSERT OR IGNORE INTO meres (id, name, isnisteia) VALUES (?, ?, ?)",
                WEEKDAYS,
            )


if __name__ == "__main__":
    from ui import run

    run()