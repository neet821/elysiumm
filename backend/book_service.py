"""Compatibility facade for the curated book catalog services."""

from book_admin_service import (
    _book_values as _book_values,
    create_book as create_book,
    delete_book as delete_book,
    update_book as update_book,
)
from book_list_admin_service import (
    create_book_list as create_book_list,
    delete_book_list as delete_book_list,
    replace_book_list_items as replace_book_list_items,
    update_book_list as update_book_list,
)
from book_catalog_service import (
    BookDuplicate as BookDuplicate,
    BookListMembershipError as BookListMembershipError,
    BookNotFound as BookNotFound,
    BookRevisionConflict as BookRevisionConflict,
    _metadata_overrides as _metadata_overrides,
    _ordered_books as _ordered_books,
    _serialize_admin_list as _serialize_admin_list,
    _serialize_public_list as _serialize_public_list,
    _tags as _tags,
    admin_catalog as admin_catalog,
    public_catalog as public_catalog,
    serialize_admin_book as serialize_admin_book,
    serialize_public_book as serialize_public_book,
)
