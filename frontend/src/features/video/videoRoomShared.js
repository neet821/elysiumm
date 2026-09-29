export function formatVideoRoomError(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return error?.message || fallback
}

export function sameVideoRoomUserId(left, right) {
  return left != null && right != null && String(left) === String(right)
}
