from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


class GameRemovalTest(unittest.TestCase):
  def test_game_api_and_runtime_are_removed(self):
    main_source = read("main.py")
    websocket_source = read("websocket_server.py")
    cleanup_source = read("room_cleanup_task.py")
    admin_source = read("admin_dashboard_service.py")

    self.assertIn("routers import", main_source)
    self.assertNotIn("games", main_source)
    self.assertNotIn("game_service", cleanup_source)
    self.assertNotIn("game_room", websocket_source)
    self.assertNotIn("game_service", websocket_source)
    self.assertNotIn("GameRoom", admin_source)


  def test_game_models_and_router_are_deleted(self):
    self.assertFalse((ROOT / "routers/games.py").exists())
    models_source = read("models.py")
    schemas_source = read("schemas.py")
    self.assertNotIn("class Game(", models_source)
    self.assertNotIn("class GameRoom", models_source)
    self.assertNotIn("class GameRoom", schemas_source)
    self.assertNotIn("class GameActionRequest", schemas_source)


  def test_latest_migration_drops_all_game_tables(self):
    migrations = sorted((ROOT / "alembic/versions").glob("*.py"))
    removal = next(
        (path.read_text(encoding="utf-8") for path in migrations if "remove_game" in path.name),
        "",
    )
    self.assertTrue(removal)
    for table in (
        "game_replay_frames",
        "game_events",
        "game_invites",
        "game_results",
        "game_states",
        "game_room_members",
        "game_rooms",
        "games",
    ):
        self.assertIn(f'"{table}"', removal)


if __name__ == "__main__":
    unittest.main()
