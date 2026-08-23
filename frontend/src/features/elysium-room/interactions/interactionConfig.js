import { FOCUS_POSES, ROUTE_BY_ID } from '../routes/routeConfig.js'

export function createInteractionConfig({ environment }) {
  if (!environment) throw new TypeError('createInteractionConfig requires an environment controller')

  return {
    getRouteFor(id) {
      return ROUTE_BY_ID[id] ?? null
    },
    focusPoseFor(id) {
      return FOCUS_POSES[id] ?? null
    },
    activateInRoom(id) {
      switch (id) {
        case 'lamp':
          environment.toggleLamp()
          return true
        case 'recordPlayer':
          environment.toggleRecord()
          return true
        case 'recordRack':
          environment.cycleAlbum()
          return true
        case 'window':
          environment.cycleScenery()
          return true
        default:
          return false
      }
    },
  }
}
