const fromEnv = (key) => import.meta.env[key] || ''

// API / WS 基础地址优先来自环境变量；未提供时使用当前页面 origin。
const fallbackOrigin = window?.location?.origin || ''
const API_BASE_URL = fromEnv('VITE_API_BASE_URL') || fallbackOrigin
const WS_BASE_URL = fromEnv('VITE_WS_BASE_URL') || API_BASE_URL

export const API_ENDPOINTS = {
  // 认证
  LOGIN: `${API_BASE_URL}/api/auth/login`,
  REFRESH: `${API_BASE_URL}/api/auth/refresh`,
  LOGOUT: `${API_BASE_URL}/api/auth/logout`,
  REGISTER: `${API_BASE_URL}/api/users/register`,
  USER_INFO: `${API_BASE_URL}/api/auth/me`,
  UPDATE_PASSWORD: `${API_BASE_URL}/api/users/me/password`,

  // 直播
  LIVE_STATUS: `${API_BASE_URL}/api/live/status`,
  LIVE_SESSION: `${API_BASE_URL}/api/live/session`,
  LIVE_HEARTBEAT: `${API_BASE_URL}/api/live/session/heartbeat`,
  LIVE_SESSION_END: `${API_BASE_URL}/api/live/session/end`,
  LIVE_MESSAGES: `${API_BASE_URL}/api/live/messages`,

  // 管理与文件同步
  ADMIN_USERS: `${API_BASE_URL}/api/admin/users`,
  ADMIN_USER_DETAIL: (id) => `${API_BASE_URL}/api/admin/users/${id}`,
  ADMIN_FILE_SYNC_STATUS: `${API_BASE_URL}/api/admin/file-sync/status`,
  ADMIN_FILE_SYNC_BROWSE: `${API_BASE_URL}/api/admin/file-sync/browse`,
  ADMIN_FILE_SYNC_DOWNLOAD: `${API_BASE_URL}/api/admin/file-sync/download`,
  ADMIN_TRANSFERS: `${API_BASE_URL}/api/admin/transfers`,
  ADMIN_TRANSFER: (id) => `${API_BASE_URL}/api/admin/transfers/${id}`,
  ADMIN_ROOMS: `${API_BASE_URL}/api/admin/sync-rooms`,
  ADMIN_ROOM_LOCK: (id) => `${API_BASE_URL}/api/admin/sync-rooms/${id}/lock`,
  AGENT_CONSOLE_STATUS: `${API_BASE_URL}/api/admin/agent-console/status`,
  ADMIN_LIVE_SETTINGS: `${API_BASE_URL}/api/admin/live/settings`,
  ADMIN_LIVE_ALLOWED_USERS: `${API_BASE_URL}/api/admin/live/allowed-users`,
  ADMIN_LIVE_STREAM_KEY_ROTATE: `${API_BASE_URL}/api/admin/live/stream-key/rotate`,
  ADMIN_LIVE_INVITES: `${API_BASE_URL}/api/admin/live/invites`,
  ADMIN_LIVE_INVITE_REVOKE: (id) => `${API_BASE_URL}/api/admin/live/invites/${id}/revoke`,
  ADMIN_LIVE_STATUS: `${API_BASE_URL}/api/admin/live/status`,
  ADMIN_LIVE_KICK: `${API_BASE_URL}/api/admin/live/kick-publisher`,
  ADMIN_LIVE_AUDIENCE: `${API_BASE_URL}/api/admin/live/audience`,
  ADMIN_LIVE_AUDIENCE_HISTORY: `${API_BASE_URL}/api/admin/live/audience/history`,
  ADMIN_LIVE_SESSIONS: `${API_BASE_URL}/api/admin/live/sessions`,
  ADMIN_LIVE_RECORDINGS: `${API_BASE_URL}/api/admin/live/recordings`,
  ADMIN_LIVE_RECORDING: (id) => `${API_BASE_URL}/api/admin/live/recordings/${id}`,

  // 观影房
  SYNC_ROOMS: `${API_BASE_URL}/api/sync-rooms`,
  SYNC_ROOM_DETAIL: (id) => `${API_BASE_URL}/api/sync-rooms/${id}`,
  SYNC_ROOM_JOIN: (id) => `${API_BASE_URL}/api/sync-rooms/${id}/join`,
  SYNC_ROOM_LEAVE: (id) => `${API_BASE_URL}/api/sync-rooms/${id}/leave`,
  SYNC_ROOM_MESSAGES: (id) => `${API_BASE_URL}/api/sync-rooms/${id}/messages`,

  // 视频房间
  VIDEO_ROOM: (roomId) => `${API_BASE_URL}/api/video/rooms/${roomId}`,
  VIDEO_URL_ITEM: (roomId) => `${API_BASE_URL}/api/video/rooms/${roomId}/items/url`,
  VIDEO_UPLOAD: (roomId) => `${API_BASE_URL}/api/video/rooms/${roomId}/items/upload`,
  VIDEO_LOCAL_ITEM: (roomId) => `${API_BASE_URL}/api/video/rooms/${roomId}/items/local`,
  VIDEO_PLAYLIST: (roomId) => `${API_BASE_URL}/api/video/rooms/${roomId}/playlist`,
  VIDEO_ADVANCE: (roomId) => `${API_BASE_URL}/api/video/rooms/${roomId}/advance`,
  VIDEO_SELECT: (roomId, itemId) => `${API_BASE_URL}/api/video/rooms/${roomId}/items/${itemId}/select`,
  VIDEO_ITEM: (roomId, itemId) => `${API_BASE_URL}/api/video/rooms/${roomId}/items/${itemId}`,
  VIDEO_METADATA: (roomId, itemId) => `${API_BASE_URL}/api/video/rooms/${roomId}/items/${itemId}/metadata`,
  VIDEO_SUBTITLES: (roomId, itemId) => `${API_BASE_URL}/api/video/rooms/${roomId}/items/${itemId}/subtitles`,
  VIDEO_SUBTITLE_SELECT: (roomId, subtitleId) => `${API_BASE_URL}/api/video/rooms/${roomId}/subtitles/${subtitleId}/select`,
  VIDEO_SUBTITLE: (roomId, subtitleId) => `${API_BASE_URL}/api/video/rooms/${roomId}/subtitles/${subtitleId}`,

  // 音乐房
  MUSIC_AUDIO: (trackId) => `${API_BASE_URL}/api/music/tracks/${trackId}/audio`,
  MUSIC_HISTORY: (roomId) => `${API_BASE_URL}/api/music/rooms/${roomId}/history`,
  MUSIC_HISTORY_REQUEUE: (roomId, eventId) => `${API_BASE_URL}/api/music/rooms/${roomId}/history/${eventId}/queue`,
  MUSIC_QUEUE: (roomId) => `${API_BASE_URL}/api/music/rooms/${roomId}/queue`,
  MUSIC_ROOM_SETTINGS: (roomId) => `${API_BASE_URL}/api/music/rooms/${roomId}/settings`,
  MUSIC_SNAPSHOT: (roomId) => `${API_BASE_URL}/api/music/rooms/${roomId}/snapshot`,
  MUSIC_PROPOSAL_VOTE: (roomId, itemId) => `${API_BASE_URL}/api/music/rooms/${roomId}/proposals/${itemId}/vote`,
  MUSIC_QUEUE_LIKE: (roomId, itemId) => `${API_BASE_URL}/api/music/rooms/${roomId}/queue/${itemId}/like`,
  MUSIC_NEXT: (roomId) => `${API_BASE_URL}/api/music/rooms/${roomId}/next`,
  MUSIC_VOTE_SKIP: (roomId) => `${API_BASE_URL}/api/music/rooms/${roomId}/vote-skip`,
  MUSIC_PROVIDER_STATUS: `${API_BASE_URL}/api/music/providers/status`,
  MUSIC_PROVIDER_LOGIN_START: (provider) => `${API_BASE_URL}/api/music/providers/${provider}/login/start`,
  MUSIC_PROVIDER_LOGIN_STATUS: (provider, sessionId) => `${API_BASE_URL}/api/music/providers/${provider}/login/${sessionId}`,
  MUSIC_PROVIDER_LOGIN_IMAGE: (provider, sessionId) => `${API_BASE_URL}/api/music/providers/${provider}/login/${sessionId}/image`,
  MUSIC_PROVIDER_CREDENTIAL: (provider) => `${API_BASE_URL}/api/music/providers/${provider}/credential`,

  // 书签导入备份（与旧页面解耦但属于受保护的数据恢复边界）
  BOOKMARK_BACKUPS: `${API_BASE_URL}/api/bookmarks/backups`,
  BOOKMARK_BACKUP_RESTORE: (id) => `${API_BASE_URL}/api/bookmarks/backups/${id}/restore`,

  // 首页与管理首页
  ADMIN_HOMEPAGE: `${API_BASE_URL}/api/admin/homepage`,
}

export { API_BASE_URL, WS_BASE_URL }
