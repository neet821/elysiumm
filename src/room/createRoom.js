import * as THREE from 'three'
import { materialRegistry } from '../scene/primitives.js'
import { createBayWindow } from './createBayWindow.js'
import { createShell } from './createShell.js'

export function createRoom(context = {}) {
  const materials = context.materials ?? materialRegistry
  if (context.palette) materials.applyPalette(context.palette)

  const group = new THREE.Group()
  group.name = 'elysium-room'

  const shell = createShell({ materials })
  const bayWindow = createBayWindow({
    materials,
    scenery: context.scenery,
    textureLoader: context.textureLoader,
  })
  group.add(shell, bayWindow.group)
  context.scene?.add(group)

  const registry = {
    window: {
      group: bayWindow.group,
      proxy: bayWindow.interactionProxy,
      setScenery: bayWindow.setScenery,
    },
  }

  return {
    group,
    shell,
    bayWindow,
    registry,
    ready: bayWindow.ready,
    dispose() {
      bayWindow.dispose()
      group.traverse((object) => {
        if (object.isMesh && object !== bayWindow.sceneryMesh && object !== bayWindow.interactionProxy) {
          object.geometry?.dispose()
        }
      })
      group.removeFromParent()
    },
  }
}
