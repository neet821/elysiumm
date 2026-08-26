export function buildRoomShareUrl(location = window.location) {
  return `${location.origin}${location.pathname}${location.search || ''}${location.hash || ''}`
}

export function normalizeSearchQuery(value) {
  return String(value ?? '').trim()
}

export async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value)
    return
  }
  const input = document.createElement('textarea')
  input.value = value
  input.style.position = 'fixed'
  input.style.opacity = '0'
  document.body.appendChild(input)
  input.select()
  document.execCommand('copy')
  input.remove()
}
