from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from dbservices.meal_repository import MealRepository
from utilities.weekly_plan import PlanEntry, WeeklyPlan


class WeeklyRepository(MealRepository):
    def __init__(self, database_path: str | Path):
        super().__init__(database_path)

    def load_plan(self) -> WeeklyPlan | None:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT p.weekday_id, p.week_start, p.meal_id, f.name "
                "FROM weekly_plan p LEFT JOIN fagaki f ON f.id = p.meal_id "
                "ORDER BY p.weekday_id"
            ).fetchall()
        if not rows:
            return None
        if len(rows) != 7 or len({row["week_start"] for row in rows}) != 1:
            raise ValueError("Invalid weekly plan data")
        start = date.fromisoformat(rows[0]["week_start"])
        if start.weekday() != 0:
            raise ValueError("Invalid weekly plan start date")
        return WeeklyPlan(start, tuple(
            PlanEntry(row["weekday_id"], row["meal_id"], row["name"]) for row in rows
        ))

    def replace_plan(self, start: date, meal_ids: list[int]) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute("DELETE FROM weekly_plan")
            connection.executemany(
                "INSERT INTO weekly_plan (weekday_id, week_start, meal_id) VALUES (?, ?, ?)",
                [(day, start.isoformat(), meal_id) for day, meal_id in enumerate(meal_ids, 1)],
            )

    def set_meal(self, weekday: int, meal_id: int) -> bool:
        with closing(self.connect()) as connection, connection:
            result = connection.execute(
                "UPDATE weekly_plan SET meal_id = ? WHERE weekday_id = ?",
                (meal_id, weekday),
            )
            return result.rowcount == 1

    def fasting_dates(self, start: date) -> set[int]:
        with closing(self.connect()) as connection:
            weekdays = {row["id"] for row in connection.execute(
                "SELECT id FROM meres WHERE isnisteia = 1"
            )}
            rows = connection.execute("SELECT dtstart, dtend FROM nisteies").fetchall()
        periods = [(date.fromisoformat(row["dtstart"]), date.fromisoformat(row["dtend"]))
                   for row in rows]
        if any(start_date > end_date for start_date, end_date in periods):
            raise ValueError("Invalid fasting period")
        for day in range(1, 8):
            current = start + timedelta(days=day - 1)
            if any(start_date <= current <= end_date for start_date, end_date in periods):
                weekdays.add(day)
        return weekdays

    def ingredient_rows(self, meal_id: int):
        with closing(self.connect()) as connection:
            return connection.execute(
                "SELECT u.id, u.name, "
                "COALESCE(NULLIF(f.monada_metrisis, ''), u.monada_metrisis) AS monada_metrisis, "
                "f.posotita, u.katigoria "
                "FROM fagaki_ulika f JOIN ulika u ON u.id = f.ulika_id "
                "WHERE f.fagaki_id = ? ORDER BY u.name, u.id", (meal_id,)
            ).fetchall()
