from fastapi import APIRouter

from routers import live_admin_access, live_admin_audience, live_admin_recordings, live_admin_settings
from routers.live_admin_access import (
    _active_invite_query as _active_invite_query,
    _allowed_payload as _allowed_payload,
    _invite_payload as _invite_payload,
    create_invite as create_invite,
    list_allowed_users as list_allowed_users,
    list_invites as list_invites,
    replace_allowed_users as replace_allowed_users,
    revoke_invite as revoke_invite,
    rotate_stream_key as rotate_stream_key,
)
from routers.live_admin_audience import (
    _session_payload as _session_payload,
    _viewer_payload as _viewer_payload,
    delete_audience_history as delete_audience_history,
    kick_publisher as kick_publisher,
    list_audience as list_audience,
    list_audience_history as list_audience_history,
    list_sessions as list_sessions,
    live_status as live_status,
)
from routers.live_admin_common import (
    MUTATION_LIMIT as MUTATION_LIMIT,
    MUTATION_WINDOW_SECONDS as MUTATION_WINDOW_SECONDS,
    _rate_limit as _rate_limit,
    active_administrator as active_administrator,
)
from routers.live_admin_recordings import (
    _get_recording as _get_recording,
    _recording_payload as _recording_payload,
    download_recording as download_recording,
    list_recordings as list_recordings,
    remove_recording as remove_recording,
    update_recording as update_recording,
)
from routers.live_admin_settings import (
    _setting_payload as _setting_payload,
    get_settings as get_settings,
    update_settings as update_settings,
)


router = APIRouter(prefix="/api/admin/live", tags=["live-admin"])
router.include_router(live_admin_settings.router)
router.include_router(live_admin_access.router)
router.include_router(live_admin_audience.router)
router.include_router(live_admin_recordings.router)
