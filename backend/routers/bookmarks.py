"""Compatibility router assembling the bookmark HTTP domains."""

from fastapi import APIRouter

from bookmark_service import bookmark_backup_output_dir as bookmark_backup_output_dir
from routers.bookmark_folders import (
    create_bookmark_folder as create_bookmark_folder,
    delete_bookmark_folder as delete_bookmark_folder,
    list_bookmark_folders as list_bookmark_folders,
    update_bookmark_folder as update_bookmark_folder,
)
from routers.bookmark_items import (
    bulk_update_bookmarks as bulk_update_bookmarks,
    create_bookmark as create_bookmark,
    delete_bookmark as delete_bookmark,
    list_bookmarks as list_bookmarks,
    update_bookmark as update_bookmark,
    visit_bookmark as visit_bookmark,
)
from routers.bookmark_route_helpers import (
    model_updates as model_updates,
    serialize_bookmark as serialize_bookmark,
)
from routers.bookmark_search_engines import (
    create_search_engine as create_search_engine,
    delete_search_engine as delete_search_engine,
    list_search_engines as list_search_engines,
    update_search_engine as update_search_engine,
)
from routers.bookmarks_public import get_public_collection as get_public_collection
from routers.bookmarks_transfer import (
    create_bookmark_backup as create_bookmark_backup,
    export_bookmarks_html as export_bookmarks_html,
    export_bookmarks_json as export_bookmarks_json,
    import_bookmarks_html as import_bookmarks_html,
    import_bookmarks_json as import_bookmarks_json,
    list_bookmark_backups as list_bookmark_backups,
    restore_bookmark_backup as restore_bookmark_backup,
)
from routers import bookmark_items, bookmark_search_engines, bookmark_folders
from routers import bookmarks_public, bookmarks_transfer

router = APIRouter(tags=["bookmarks"])

# Keep the historical registration sequence while each route group owns its handlers.
router.include_router(bookmarks_public.router)
router.include_router(bookmark_folders.router)
router.include_router(bookmark_items.list_create_router)
router.include_router(bookmarks_transfer.router)
router.include_router(bookmark_items.activity_router)
router.include_router(bookmark_search_engines.router)
router.include_router(bookmark_items.update_delete_router)
