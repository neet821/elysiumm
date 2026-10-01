"""Compat router combining the admin and share-link transfer endpoints."""

from fastapi import APIRouter

from routers import admin_transfers, public_transfers
from transfer_download_service import (
    create_transfer_download_response as create_transfer_download_response,
    iter_file as iter_file,
)
from transfer_session_service import (
    get_or_create_current_session as get_or_create_current_session,
    serialize_datetime as serialize_datetime,
    serialize_session as serialize_session,
    session_for_token as session_for_token,
)

# Keep the historical module-level router import and endpoint names available.
router = APIRouter()
router.include_router(admin_transfers.router)
router.include_router(public_transfers.router)

AdminTransferNotePayload = admin_transfers.AdminTransferNotePayload
admin_user = admin_transfers.admin_user
create_transfer = admin_transfers.create_transfer
current_transfer_link = admin_transfers.current_transfer_link
list_transfers = admin_transfers.list_transfers
list_transfer_files = admin_transfers.list_transfer_files
get_admin_transfer_note = admin_transfers.get_admin_transfer_note
read_admin_transfer_note = admin_transfers.read_admin_transfer_note
write_admin_transfer_note = admin_transfers.write_admin_transfer_note
download_admin_transfer = admin_transfers.download_admin_transfer
delete_admin_transfer_file = admin_transfers.delete_admin_transfer_file
delete_transfer = admin_transfers.delete_transfer
inspect_transfer = public_transfers.inspect_transfer
upload_transfer = public_transfers.upload_transfer
download_transfer = public_transfers.download_transfer
