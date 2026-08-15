export const EMPTY_ROOM_TIMEOUT_MS = 10 * 60 * 1000

export function getOnlineMemberCount(room) {
  const count = Number(room?.member_count)
  return Number.isFinite(count) && count >= 0 ? Math.floor(count) : 0
}

export function formatEmptyRoomCountdown(lastActivityAt, nowMs = Date.now()) {
  const parsedActivityAt = Date.parse(lastActivityAt || '')
  const activityAt = Number.isFinite(parsedActivityAt) ? parsedActivityAt : nowMs
  const remainingMs = activityAt + EMPTY_ROOM_TIMEOUT_MS - nowMs
  const remainingSeconds = Math.max(0, Math.ceil(remainingMs / 1000))
  const minutes = Math.floor(remainingSeconds / 60)
  const seconds = remainingSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')} 后关闭`
}
