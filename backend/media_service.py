"""Compatibility facade for curated media queries, writes, and views."""

from media_mutation_service import (
    MediaDuplicate as MediaDuplicate,
    MediaNotFound as MediaNotFound,
    MediaRevisionConflict as MediaRevisionConflict,
    _BOOK_MODEL_FIELDS as _BOOK_MODEL_FIELDS,
    _MANUAL_METADATA_FIELDS as _MANUAL_METADATA_FIELDS,
    _MEDIA_MODEL_FIELDS as _MEDIA_MODEL_FIELDS,
    _load_row as _load_row,
    _source_duplicate as _source_duplicate,
    _unique_slug as _unique_slug,
    create_media as create_media,
    update_media as update_media,
)
from media_public_service import (
    public_recent as public_recent,
    selected_public as selected_public,
)
from media_serialization import (
    _book_external_url as _book_external_url,
    _book_status_to_media as _book_status_to_media,
    _dump_json as _dump_json,
    _json_list as _json_list,
    _json_object as _json_object,
    _media_status_to_book as _media_status_to_book,
    _safe_external_url as _safe_external_url,
    _tags as _tags,
    serialize_book_admin as serialize_book_admin,
    serialize_book_view as serialize_book_view,
    serialize_media_admin as serialize_media_admin,
    serialize_media_view as serialize_media_view,
)
