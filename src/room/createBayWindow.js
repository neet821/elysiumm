import * as THREE from 'three'
import { createOutlinedBox, createOutlinedMesh, disposeObjectGeometries } from '../scene/primitives.js'
import { DEFAULT_SCENERY, SCENERY_URLS, loadSceneryTexture, resolveSceneryUrl } from '../scene/textureLoader.js'

function addBox(group, registry, name, size, position, materialKey = 'frame', shadows = {}) {
  const box = createOutlinedBox(size, materialKey, registry, shadows)
  box.name = name
  box.position.copy(position)
  group.add(box)
  return box
}

export function createBayWindow({ materials, scenery = DEFAULT_SCENERY, textureLoader } = {}) {
  const group = new THREE.Group()
  group.name = 'bay-window'

  const sceneryMaterial = new THREE.MeshBasicMaterial({ color: '#b8d6dc', side: THREE.DoubleSide })
  const sceneryMesh = new THREE.Mesh(new THREE.PlaneGeometry(8.65, 4.65), sceneryMaterial)
  sceneryMesh.name = 'seamless-outside-scenery'
  sceneryMesh.position.set(0, 3.25, -4.52)
  group.add(sceneryMesh)

  const glass = createOutlinedMesh(new THREE.PlaneGeometry(8.35, 4.35), 'glass', materials)
  glass.name = 'bay-window-glass'
  glass.position.set(0, 3.25, -4.28)
  group.add(glass)

  const frameShadows = { castShadow: true }
  addBox(group, materials, 'window-top-frame', new THREE.Vector3(8.85, 0.22, 0.22), new THREE.Vector3(0, 5.52, -4.15), 'frame', frameShadows)
  addBox(group, materials, 'window-bottom-frame', new THREE.Vector3(8.85, 0.26, 0.48), new THREE.Vector3(0, 0.98, -3.98), 'frame', frameShadows)
  addBox(group, materials, 'window-left-frame', new THREE.Vector3(0.22, 4.72, 0.22), new THREE.Vector3(-4.32, 3.25, -4.15), 'frame', frameShadows)
  addBox(group, materials, 'window-right-frame', new THREE.Vector3(0.22, 4.72, 0.22), new THREE.Vector3(4.32, 3.25, -4.15), 'frame', frameShadows)
  addBox(group, materials, 'window-mullion-left', new THREE.Vector3(0.16, 4.5, 0.18), new THREE.Vector3(-1.46, 3.25, -4.04), 'frame', frameShadows)
  addBox(group, materials, 'window-mullion-right', new THREE.Vector3(0.16, 4.5, 0.18), new THREE.Vector3(1.46, 3.25, -4.04), 'frame', frameShadows)

  const leftReveal = addBox(group, materials, 'bay-left-reveal', new THREE.Vector3(0.24, 4.7, 0.85), new THREE.Vector3(-4.42, 3.25, -3.76), 'shell')
  leftReveal.rotation.y = -0.18
  const rightReveal = addBox(group, materials, 'bay-right-reveal', new THREE.Vector3(0.24, 4.7, 0.85), new THREE.Vector3(4.42, 3.25, -3.76), 'shell')
  rightReveal.rotation.y = 0.18

  const interactionProxy = new THREE.Mesh(
    new THREE.BoxGeometry(8.55, 4.55, 0.28),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
  )
  interactionProxy.name = 'window-interaction-proxy'
  interactionProxy.position.set(0, 3.25, -3.91)
  interactionProxy.userData.interactionId = 'window'
  group.add(interactionProxy)

  let loadVersion = 0
  async function setScenery(nextScenery) {
    const resolvedScenery = Object.hasOwn(SCENERY_URLS, nextScenery) ? nextScenery : DEFAULT_SCENERY
    const version = ++loadVersion
    const loadedScenery = await loadSceneryTexture(resolvedScenery, textureLoader)
    if (version !== loadVersion) {
      loadedScenery.texture.dispose()
      return false
    }

    sceneryMaterial.map?.dispose()
    sceneryMaterial.map = loadedScenery.texture
    sceneryMaterial.color.set('#ffffff')
    sceneryMaterial.needsUpdate = true
    group.userData.scenery = loadedScenery.scenery
    group.userData.sceneryUrl = resolveSceneryUrl(loadedScenery.scenery)
    return true
  }

  group.userData.scenery = scenery
  group.userData.sceneryUrl = resolveSceneryUrl(scenery)
  const ready = setScenery(scenery)

  return {
    group,
    sceneryMesh,
    interactionProxy,
    setScenery,
    ready,
    dispose() {
      loadVersion += 1
      disposeObjectGeometries(group)
      sceneryMaterial.map?.dispose()
      sceneryMaterial.dispose()
      interactionProxy.material.dispose()
    },
  }
}
