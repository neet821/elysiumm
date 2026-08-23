import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import media_matching  # noqa: E402


class MediaMatchingTest(unittest.TestCase):
    def test_album_creator_hint_ranks_the_right_same_title_result(self):
        ranked, recommendation = media_matching.rank_candidates(
            "album",
            "OK Computer",
            [
                {"title": "OK Computer", "creator": "Lemaitre", "source_id": "wrong"},
                {"title": "OK Computer", "creator": "Radiohead", "source_id": "right"},
            ],
        )

        self.assertEqual([item["source_id"] for item in ranked], ["right", "wrong"])
        self.assertEqual(recommendation["source_id"], "right")

    def test_chinese_book_alias_is_available_to_the_server(self):
        self.assertIn("The Wind-Up Bird Chronicle", media_matching.search_queries("book", "奇鸟行状录"))

    def test_games_remove_non_product_entries_and_recommend_base_game(self):
        ranked, recommendation = media_matching.rank_candidates(
            "game",
            "女神异闻录5",
            [
                {"title": "Persona 5 Tactica", "source_id": "tactica"},
                {"title": "Persona 5 Royal", "source_id": "royal"},
                {"title": "Persona 5", "source_id": "base"},
                {"title": "Persona 5 Soundtrack", "source_id": "ost"},
            ],
        )

        self.assertEqual([item["source_id"] for item in ranked], ["base", "royal", "tactica"])
        self.assertEqual(recommendation["source_id"], "base")

    def test_unseen_book_alias_prefers_norwegian_wood(self):
        ranked, recommendation = media_matching.rank_candidates(
            "book",
            "挪威的森林",
            [
                {"title": "Norwegian Wood", "creator": "Haruki Murakami"},
                {"title": "Norwegian Wood: A Novel", "creator": "Haruki Murakami"},
                {"title": "Norwegian Woodworking", "creator": "Other Author"},
            ],
        )
        self.assertEqual(ranked[0]["title"], "Norwegian Wood")
        self.assertEqual(recommendation["title"], "Norwegian Wood")

    def test_unseen_album_alias_prefers_elliott_smith(self):
        ranked, recommendation = media_matching.rank_candidates(
            "album",
            "Either—Or",
            [
                {"title": "Either/Or", "creator": "Elliott Smith"},
                {"title": "Either-Or", "creator": "Various Artists"},
            ],
        )
        self.assertEqual(ranked[0]["creator"], "Elliott Smith")
        self.assertEqual(recommendation["creator"], "Elliott Smith")

    def test_unseen_movie_alias_prefers_last_emperor(self):
        ranked, recommendation = media_matching.rank_candidates(
            "movie",
            "末代皇帝",
            [
                {"title": "The Last Emperor", "year": 1987},
                {"title": "The Emperor's Last Stand", "year": 2000},
            ],
        )
        self.assertEqual(ranked[0]["title"], "The Last Emperor")
        self.assertEqual(recommendation["title"], "The Last Emperor")

    def test_unseen_game_alias_removes_soundtrack_and_recommends_fata_morgana(self):
        ranked, recommendation = media_matching.rank_candidates(
            "game",
            "海市蜃楼之馆",
            [
                {"title": "The House in Fata Morgana Original Soundtrack"},
                {"title": "The House in Fata Morgana"},
                {"title": "The House in Fata Morgana - Dream of the Revenants Edition"},
            ],
        )
        self.assertEqual(ranked[0]["title"], "The House in Fata Morgana")
        self.assertEqual(recommendation["title"], "The House in Fata Morgana")


if __name__ == "__main__":
    unittest.main()
