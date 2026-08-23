export function cubicEaseInOut(value) {
  const progress = Number.isFinite(value) ? value : 0
  if (progress <= 0) return 0
  if (progress >= 1) return 1
  if (progress < 0.5) return 4 * progress * progress * progress

  const remaining = -2 * progress + 2
  return 1 - (remaining * remaining * remaining) / 2
}
