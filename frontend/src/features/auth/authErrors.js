export function getAuthErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(', ')
  if (typeof detail === 'object') {
    return detail.msg || JSON.stringify(detail)
  }
  return fallback
}
