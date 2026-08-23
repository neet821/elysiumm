import * as THREE from 'three'
import { disposeObjectGeometries, materialRegistry } from '../scene/primitives.js'
import { createBayWindow } from './createBayWindow.js'
import { createDecor } from './createDecor.js'
import { createDeskZone } from './createDeskZone.js'
import { createRecordZone } from './createRecordZone.js'
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
  const deskZone = createDeskZone({ materials })
  const recordZone = createRecordZone({ materials })
  const decor = createDecor({ materials })
  group.add(shell, bayWindow.group, deskZone.group, recordZone.group, decor.group)
  context.scene?.add(group)

  const registry = {
    window: {
      group: bayWindow.group,
      visual: bayWindow.group,
      proxy: bayWindow.interactionProxy,
      label: 'Scenery',
      setScenery: bayWindow.setScenery,
    },
    ...deskZone.registry,
    ...recordZone.registry,
    ...decor.registry,
  }

  return {
    group,
    shell,
    bayWindow,
    deskZone,
    recordZone,
    decor,
    registry,
    ready: bayWindow.ready,
    dispose() {
      bayWindow.dispose()
      deskZone.dispose()
      recordZone.dispose()
      decor.dispose()
      disposeObjectGeometries(group)
      group.removeFromParent()
    },
  }
}
