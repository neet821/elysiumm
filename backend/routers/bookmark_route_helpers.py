import bookmark_service
import models


def model_updates(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=True)
    return model.dict(exclude_unset=True)


def serialize_bookmark(bookmark: models.Bookmark) -> dict:
    return {
        "id": bookmark.id,
        "user_id": bookmark.user_id,
        "folder_id": bookmark.folder_id,
        "title": bookmark.title,
        "url": bookmark.url,
        "description": bookmark.description,
        "favicon": bookmark.favicon,
        "preview_url": bookmark.preview_url,
        "sort_order": bookmark.sort_order,
        "is_archived": bookmark.is_archived,
        "is_public": bookmark.is_public,
        "is_pinned": bookmark.is_pinned,
        "visit_count": bookmark.visit_count,
        "show_description": bookmark.show_description,
        "show_preview": bookmark.show_preview,
        "show_visit_count": bookmark.show_visit_count,
        "allow_indexing": bookmark.allow_indexing,
        "tags": bookmark_service.tags_for_bookmark(bookmark),
        "created_at": bookmark.created_at,
        "updated_at": bookmark.updated_at,
        "last_visited_at": bookmark.last_visited_at,
    }
