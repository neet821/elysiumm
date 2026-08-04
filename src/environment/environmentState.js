const AUTO_MODE = 'auto'
const MODES = new Set(['dawn', 'day', 'dusk', 'night'])

export function classifyLocalHour(hour) {
  if (!Number.isInteger(hour) || hour < 0 || hour > 23) {
    throw new RangeError('hour must be an integer from 0 through 23')
  }

  if (hour < 6 || hour >= 20) return 'night'
  if (hour < 9) return 'dawn'
  if (hour < 17) return 'day'
  return 'dusk'
}

export function createEnvironmentState(nowProvider = () => new Date()) {
  if (typeof nowProvider !== 'function') {
    throw new TypeError('nowProvider must be a function')
  }

  let manualMode = null

  return {
    getState() {
      return {
        mode: manualMode ?? classifyLocalHour(nowProvider().getHours()),
        isAuto: manualMode === null,
      }
    },

    setMode(mode) {
      if (mode === AUTO_MODE) {
        manualMode = null
        return
      }

      if (!MODES.has(mode)) {
        throw new RangeError(`unknown environment mode: ${mode}`)
      }

      manualMode = mode
    },
  }
}
