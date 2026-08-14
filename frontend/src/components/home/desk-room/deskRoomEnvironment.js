export function getInitialTimePreset(hour = new Date().getHours()) {
  if (hour >= 5 && hour < 9) return 'morning'
  if (hour >= 9 && hour < 17) return 'afternoon'
  if (hour >= 17 && hour < 20) return 'sunset'
  return 'night'
}
