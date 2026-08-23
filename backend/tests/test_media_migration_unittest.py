import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect


ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = ROOT_DIR / "backend" / "alembic.ini"


class MediaMigrationTest(unittest.TestCase):
    def run_alembic(self, database_url: str, *arguments: str) -> None:
        env = os.environ.copy()
        env["DATABASE_URL"] = database_url
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_CONFIG), *arguments],
            cwd=ROOT_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_upgrade_adds_media_without_replacing_the_existing_book_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'media-migration.sqlite'}"
            self.run_alembic(database_url, "upgrade", "head")
            engine = create_engine(database_url)
            inspector = inspect(engine)

            self.assertIn("media_entries", inspector.get_table_names())
            media_columns = {column["name"] for column in inspector.get_columns("media_entries")}
            self.assertTrue(
                {
                    "kind",
                    "title",
                    "creator",
                    "cover_url",
                    "release_year",
                    "summary",
                    "tags_json",
                    "status",
                    "activity_at",
                    "personal_rating",
                    "personal_notes",
                    "is_public",
                    "is_featured",
                    "source",
                    "source_id",
                    "external_url",
                    "metadata_json",
                    "raw_metadata_json",
                    "metadata_overrides_json",
                    "revision",
                    "created_at",
                    "updated_at",
                }.issubset(media_columns)
            )
            book_columns = {column["name"] for column in inspector.get_columns("books")}
            self.assertTrue(
                {
                    "source",
                    "source_id",
                    "isbn",
                    "publication_year",
                    "personal_rating",
                    "personal_notes",
                    "metadata_overrides_json",
                }.issubset(book_columns)
            )
            engine.dispose()

            self.run_alembic(database_url, "downgrade", "0016_music_room_switching")
            engine = create_engine(database_url)
            inspector = inspect(engine)
            self.assertNotIn("media_entries", inspector.get_table_names())
            book_columns = {column["name"] for column in inspector.get_columns("books")}
            self.assertNotIn("source_id", book_columns)
            self.assertIn("title", book_columns)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
