"""Compatibility facade for public sync domains.

Routes and existing integrations keep importing this module while device,
dashboard, single-file, and resumable-upload behavior lives in focused owners.
"""

from public_sync_chunk_service import (
    _abort_upload as _abort_upload,
    _restore_or_remove_upload_record as _restore_or_remove_upload_record,
    cleanup_expired_uploads as cleanup_expired_uploads,
    save_chunk as save_chunk,
)
from public_sync_dashboard_service import (
    MAX_DASHBOARD_DEVICES as MAX_DASHBOARD_DEVICES,
    MAX_DASHBOARD_EVENTS as MAX_DASHBOARD_EVENTS,
    MAX_DASHBOARD_FILES as MAX_DASHBOARD_FILES,
    dashboard_payload as dashboard_payload,
    serialize_device as serialize_device,
    serialize_event as serialize_event,
    serialize_file as serialize_file,
)
from public_sync_device_service import (
    DEFAULT_DEVICE_TOKEN_DAYS as DEFAULT_DEVICE_TOKEN_DAYS,
    INVALID_DEVICE_CREDENTIAL as INVALID_DEVICE_CREDENTIAL,
    MAX_DEVICE_TOKEN_DAYS as MAX_DEVICE_TOKEN_DAYS,
    MAX_DEVICE_TOKEN_LENGTH as MAX_DEVICE_TOKEN_LENGTH,
    _new_device_token as _new_device_token,
    _validate_expiry_days as _validate_expiry_days,
    authenticate_device as authenticate_device,
    create_device as create_device,
    hash_device_token as hash_device_token,
    revoke_device as revoke_device,
    rotate_device_credential as rotate_device_credential,
)
from public_sync_file_service import (
    MAX_SYNC_CHUNK_SIZE as MAX_SYNC_CHUNK_SIZE,
    MAX_SYNC_DEVICE_BYTES as MAX_SYNC_DEVICE_BYTES,
    MAX_SYNC_FILE_SIZE as MAX_SYNC_FILE_SIZE,
    MAX_TOTAL_CHUNKS as MAX_TOTAL_CHUNKS,
    STREAM_BLOCK_SIZE as STREAM_BLOCK_SIZE,
    SYNC_STORAGE_ROOT as SYNC_STORAGE_ROOT,
    UPLOAD_TTL_SECONDS as UPLOAD_TTL_SECONDS,
    _active_uploads as _active_uploads,
    _atomic_replace as _atomic_replace,
    _check_device_quota as _check_device_quota,
    _destination_path as _destination_path,
    _file_record as _file_record,
    _normalize_sha256 as _normalize_sha256,
    _publish_record as _publish_record,
    _remove_empty_parents as _remove_empty_parents,
    _rollback_replace as _rollback_replace,
    _storage_root as _storage_root,
    _stream_to_path as _stream_to_path,
    _validate_expected_size as _validate_expected_size,
    delete_file as delete_file,
    safe_relative_path as safe_relative_path,
    save_upload as save_upload,
)
