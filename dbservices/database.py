import sqlite3
from contextlib import closing
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent.parent / "fagaki.db"

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
                        CHECK (monada_metrisis IN
                            ('τεμάχιο', 'συσκευασία', 'κιλό', 'λίτρο', 'ml', 'κ.σ.', 'κ.γ.')),
                    katigoria TEXT NOT NULL DEFAULT 'άλλα',
                    exoapothema INTEGER NOT NULL DEFAULT 0 CHECK (exoapothema IN (0, 1))
                )
                """
            )
            ingredient_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(ulika)")
            }
            if "katigoria" not in ingredient_columns:
                connection.execute(
                    "ALTER TABLE ulika ADD COLUMN katigoria TEXT NOT NULL DEFAULT 'άλλα'"
                )
            table_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'ulika'"
            ).fetchone()[0]
            link_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'fagaki_ulika'"
            ).fetchone() is not None
            link_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(fagaki_ulika)")
            } if link_exists else set()
            link_targets = {
                row[2] for row in connection.execute("PRAGMA foreign_key_list(fagaki_ulika)")
            } if link_exists else set()
            rebuild_links = (
                link_exists and
                ("posotita" not in link_columns or link_targets != {"fagaki", "ulika"})
            )
            if "'λίτρο'" not in table_sql or rebuild_links:
                if link_exists:
                    backup_quantity = (
                        "posotita" if "posotita" in link_columns else "NULL AS posotita"
                    )
                    backup_unit = (
                        "monada_metrisis" if "monada_metrisis" in link_columns
                        else "COALESCE((SELECT u.monada_metrisis FROM ulika u "
                             "WHERE u.id = fagaki_ulika.ulika_id), '') AS monada_metrisis"
                    )
                    connection.execute(
                        "CREATE TEMP TABLE fagaki_ulika_backup AS "
                        f"SELECT fagaki_id, ulika_id, {backup_quantity}, {backup_unit} "
                        "FROM fagaki_ulika"
                    )
                    connection.execute("DROP TABLE fagaki_ulika")
                if "'λίτρο'" not in table_sql:
                    connection.execute("ALTER TABLE ulika RENAME TO ulika_old")
                    connection.execute(
                        """
                        CREATE TABLE ulika (
                            id INTEGER PRIMARY KEY,
                            name TEXT NOT NULL,
                            monada_metrisis TEXT NOT NULL
                                CHECK (monada_metrisis IN
                                    ('τεμάχιο', 'συσκευασία', 'κιλό', 'λίτρο',
                                     'ml', 'κ.σ.', 'κ.γ.')),
                            katigoria TEXT NOT NULL DEFAULT 'άλλα',
                            exoapothema INTEGER NOT NULL DEFAULT 0
                                CHECK (exoapothema IN (0, 1))
                        )
                        """
                    )
                    connection.execute(
                        "INSERT INTO ulika "
                        "(id, name, monada_metrisis, katigoria, exoapothema) "
                        "SELECT id, name, monada_metrisis, katigoria, exoapothema "
                        "FROM ulika_old"
                    )
                    connection.execute("DROP TABLE ulika_old")
                if link_exists:
                    connection.execute(
                        """
                        CREATE TABLE fagaki_ulika (
                            fagaki_id INTEGER NOT NULL REFERENCES fagaki(id) ON DELETE CASCADE,
                            ulika_id INTEGER NOT NULL REFERENCES ulika(id) ON DELETE CASCADE,
                            posotita REAL CHECK (
                                posotita IS NULL OR
                                (typeof(posotita) IN ('integer', 'real') AND posotita > 0)
                            ),
                            monada_metrisis TEXT NOT NULL DEFAULT '' CHECK (
                                monada_metrisis IN
                                ('', 'τεμάχιο', 'συσκευασία', 'κιλό', 'λίτρο', 'ml', 'κ.σ.', 'κ.γ.')
                            ),
                            PRIMARY KEY (fagaki_id, ulika_id, monada_metrisis)
                        )
                        """
                    )
                    connection.execute(
                        "INSERT INTO fagaki_ulika (fagaki_id, ulika_id, posotita, monada_metrisis) "
                        "SELECT fagaki_id, ulika_id, posotita, monada_metrisis "
                        "FROM fagaki_ulika_backup"
                    )
                    connection.execute("DROP TABLE fagaki_ulika_backup")
                    connection.execute(
                        "CREATE INDEX IF NOT EXISTS fagaki_ulika_ulika_id "
                        "ON fagaki_ulika (ulika_id)"
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
                    monada_metrisis TEXT NOT NULL DEFAULT '' CHECK (
                        monada_metrisis IN
                        ('', 'τεμάχιο', 'συσκευασία', 'κιλό', 'λίτρο', 'ml', 'κ.σ.', 'κ.γ.')
                    ),
                    PRIMARY KEY (fagaki_id, ulika_id, monada_metrisis)
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
            if "monada_metrisis" not in ingredient_columns:
                extra_columns = ingredient_columns - {"fagaki_id", "ulika_id", "posotita"}
                extra_objects = connection.execute(
                    "SELECT name FROM sqlite_master WHERE tbl_name = 'fagaki_ulika' "
                    "AND type IN ('index', 'trigger') AND sql IS NOT NULL "
                    "AND name <> 'fagaki_ulika_ulika_id'"
                ).fetchall()
                if extra_columns or extra_objects:
                    raise sqlite3.DatabaseError(
                        "Δεν είναι δυνατή η αναβάθμιση του πίνακα fagaki_ulika: "
                        "υπάρχουν επιπλέον στήλες, ευρετήρια ή triggers."
                    )
                connection.execute("ALTER TABLE fagaki_ulika RENAME TO fagaki_ulika_old")
                connection.execute(
                    """
                    CREATE TABLE fagaki_ulika (
                        fagaki_id INTEGER NOT NULL REFERENCES fagaki(id) ON DELETE CASCADE,
                        ulika_id INTEGER NOT NULL REFERENCES ulika(id) ON DELETE CASCADE,
                        posotita REAL CHECK (
                            posotita IS NULL OR
                            (typeof(posotita) IN ('integer', 'real') AND posotita > 0)
                        ),
                        monada_metrisis TEXT NOT NULL DEFAULT '' CHECK (
                            monada_metrisis IN
                            ('', 'τεμάχιο', 'συσκευασία', 'κιλό', 'λίτρο', 'ml', 'κ.σ.', 'κ.γ.')
                        ),
                        PRIMARY KEY (fagaki_id, ulika_id, monada_metrisis)
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO fagaki_ulika (fagaki_id, ulika_id, posotita, monada_metrisis) "
                    "SELECT f.fagaki_id, f.ulika_id, f.posotita, "
                    "COALESCE(u.monada_metrisis, '') "
                    "FROM fagaki_ulika_old f LEFT JOIN ulika u ON u.id = f.ulika_id"
                )
                connection.execute("DROP TABLE fagaki_ulika_old")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS fagaki_ulika_ulika_id ON fagaki_ulika (ulika_id)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS weekly_plan (
                    weekday_id INTEGER PRIMARY KEY CHECK (weekday_id BETWEEN 1 AND 7),
                    week_start TEXT NOT NULL,
                    meal_id INTEGER REFERENCES fagaki(id) ON DELETE SET NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingredient_processing (
                    meal_id INTEGER PRIMARY KEY REFERENCES fagaki(id) ON DELETE CASCADE
                )
                """
            )
            connection.executemany(
                "INSERT OR IGNORE INTO meres (id, name, isnisteia) VALUES (?, ?, ?)",
                WEEKDAYS,
            )