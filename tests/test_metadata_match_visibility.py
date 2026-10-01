import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from articles.store import (  # noqa: E402
    ArticleStore,
    _parse_note,
    _strip_obsidian_metadata_match_panel,
)


def test_public_record_drops_metadata_match_panel() -> None:
    source = (
        "---\ntype: album\nmetadata_match:\n  status: pending\n---\n\n"
        "<!-- elysium-metadata-match:start -->\n"
        "secret candidate\n"
        "<!-- elysium-metadata-match:end -->\n\n正文"
    )

    data, body, *_ = _parse_note(source, "测试")

    assert data["metadata_match"]["status"] == "pending"
    assert "secret candidate" not in _strip_obsidian_metadata_match_panel(body)


def test_public_record_item_does_not_expose_machine_field(tmp_path: Path) -> None:
    note = tmp_path / "专辑" / "测试.md"
    note.parent.mkdir()
    note.write_text(
        "---\ntype: album\ncreator: 作者\nmetadata_match:\n  status: pending\n---\n正文",
        encoding="utf-8",
    )

    item = ArticleStore(tmp_path, include_root_files=True)._read_record(note)

    assert item is not None
    assert "metadata_match" not in item


def test_public_detail_removes_the_panel_before_markdown_render(tmp_path: Path) -> None:
    note = tmp_path / "专辑" / "测试.md"
    note.parent.mkdir()
    note.write_text(
        "---\ntype: album\nmetadata_match:\n  status: pending\n---\n\n"
        "<!-- elysium-metadata-match:start -->\n"
        "secret candidate\n"
        "<!-- elysium-metadata-match:end -->\n\n正文",
        encoding="utf-8",
    )

    article = ArticleStore(tmp_path).get_article("专辑/测试")

    assert "secret candidate" not in article["markdown"]
    assert "正文" in article["markdown"]
