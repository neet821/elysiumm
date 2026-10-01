from sqlalchemy.orm import Session

import models


def get_or_create_tag(db: Session, user_id: int, name: str) -> models.BookmarkTag:
    normalized = name.strip()
    tag = db.query(models.BookmarkTag).filter(
        models.BookmarkTag.user_id == user_id,
        models.BookmarkTag.name == normalized,
    ).first()
    if tag:
        return tag

    tag = models.BookmarkTag(user_id=user_id, name=normalized)
    db.add(tag)
    db.flush()
    return tag


def replace_bookmark_tags(
    db: Session,
    user_id: int,
    bookmark: models.Bookmark,
    tag_names: list[str],
) -> None:
    db.query(models.BookmarkTagRelation).filter(
        models.BookmarkTagRelation.bookmark_id == bookmark.id,
    ).delete(synchronize_session=False)

    seen: set[str] = set()
    for tag_name in tag_names:
        normalized = tag_name.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tag = get_or_create_tag(db, user_id, normalized)
        db.add(models.BookmarkTagRelation(bookmark_id=bookmark.id, tag_id=tag.id))


def tags_for_bookmark(bookmark: models.Bookmark) -> list[str]:
    return [relation.tag.name for relation in bookmark.tag_relations if relation.tag]
