import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = ROOT_DIR / "backend" / "alembic.ini"
LIVE_TABLES = {
    "live_settings",
    "live_allowed_users",
    "live_invites",
    "live_sessions",
    "live_recordings",
    "live_viewer_sessions",
    "live_credentials",
}


class LiveMigrationTest(unittest.TestCase):
    def run_alembic(self, database_url: str, *arguments: str) -> None:
        env = os.environ.copy()
        env["DATABASE_URL"] = database_url
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(ALEMBIC_CONFIG),
                *arguments,
            ],
            cwd=ROOT_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_live_migration_round_trip_creates_seven_tables_and_preserves_users(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "live-migration.sqlite"
            database_url = f"sqlite:///{database_path}"
            self.run_alembic(database_url, "upgrade", "0012_sync_room_time_float")

            engine = create_engine(database_url)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users "
                        "(id, username, email, hashed_password, role, is_active) "
                        "VALUES (1, 'admin', 'admin@example.com', 'hash', 'admin', 1)"
                    )
                )
            engine.dispose()

            self.run_alembic(database_url, "upgrade", "0022_sync_room_lock")
            engine = create_engine(database_url)
            self.assertTrue(
                LIVE_TABLES.issubset(set(inspect(engine).get_table_names()))
            )
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(text("SELECT count(*) FROM users")).scalar_one(),
                    1,
                )
            engine.dispose()

            self.run_alembic(
                database_url,
                "downgrade",
                "0012_sync_room_time_float",
            )
            engine = create_engine(database_url)
            self.assertTrue(
                LIVE_TABLES.isdisjoint(set(inspect(engine).get_table_names()))
            )
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(text("SELECT count(*) FROM users")).scalar_one(),
                    1,
                )
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
