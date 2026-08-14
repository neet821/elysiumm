import * as THREE from 'three'
import { createOutlinedBox, createOutlinedMesh, disposeObjectGeometries } from '../scene/primitives.js'
import { DEFAULT_SCENERY, SCENERY_URLS, loadSceneryTexture, resolveSceneryUrl } from '../scene/textureLoader.js'
import { BAY_WINDOW } from './layout.js'

function addBox(group, registry, name, size, position, materialKey = 'frame', shadows = {}) {
  const box = createOutlinedBox(size, materialKey, registry, shadows)
  box.name = name
  box.position.copy(position)
  group.add(box)
  return box
}

function addGlass(group, materials, name, width, height, position) {
  const glass = createOutlinedMesh(new THREE.PlaneGeometry(width, height), 'glass', materials)
  glass.name = name
  glass.position.copy(position)
  group.add(glass)
  return glass
}

function createSceneryPlane(name, width, height, material, uMin = 0, uMax = 1) {
  const geometry = new THREE.PlaneGeometry(width, height)
  const uv = geometry.getAttribute('uv')
  for (let index = 0; index < uv.count; index += 1) {
    uv.setX(index, THREE.MathUtils.lerp(uMin, uMax, uv.getX(index)))
  }
  uv.needsUpdate = true
  const mesh = new THREE.Mesh(geometry, material)
  mesh.name = name
  return mesh
}

function createFrontWindows(group, materials) {
  const unitWidth = BAY_WINDOW.frontWidth / BAY_WINDOW.unitCount
  const openingHeight = BAY_WINDOW.topY - BAY_WINDOW.sillY
  const upperHeight = BAY_WINDOW.topY - BAY_WINDOW.splitY
  const lowerHeight = BAY_WINDOW.splitY - BAY_WINDOW.sillY
  const frameShadow = { castShadow: true }

  addBox(group, materials, 'bay-front-top-frame', new THREE.Vector3(BAY_WINDOW.frontWidth + BAY_WINDOW.frame, 0.2, BAY_WINDOW.depth), new THREE.Vector3(0, BAY_WINDOW.topY, BAY_WINDOW.frontZ), 'frame', frameShadow)
  addBox(group, materials, 'bay-front-sill', new THREE.Vector3(BAY_WINDOW.frontWidth + 0.22, 0.22, 0.52), new THREE.Vector3(0, BAY_WINDOW.sillY, BAY_WINDOW.frontZ + 0.12), 'frame', frameShadow)

  for (let boundary = 0; boundary <= BAY_WINDOW.unitCount; boundary += 1) {
    const x = -BAY_WINDOW.frontWidth / 2 + boundary * unitWidth
    addBox(group, materials, `bay-front-vertical-${boundary + 1}`, new THREE.Vector3(BAY_WINDOW.frame, openingHeight, BAY_WINDOW.depth), new THREE.Vector3(x, (BAY_WINDOW.sillY + BAY_WINDOW.topY) / 2, BAY_WINDOW.frontZ), 'frame', frameShadow)
  }

  for (let index = 0; index < BAY_WINDOW.unitCount; index += 1) {
    const x = -BAY_WINDOW.frontWidth / 2 + unitWidth * (index + 0.5)
    addBox(group, materials, `bay-front-crossbar-${index + 1}`, new THREE.Vector3(unitWidth - BAY_WINDOW.frame * 0.45, BAY_WINDOW.frame, BAY_WINDOW.depth + 0.015), new THREE.Vector3(x, BAY_WINDOW.splitY, BAY_WINDOW.frontZ + 0.015), 'frame', frameShadow)
    addGlass(group, materials, `bay-front-upper-glass-${index + 1}`, unitWidth - BAY_WINDOW.frame * 1.35, upperHeight - BAY_WINDOW.frame * 1.3, new THREE.Vector3(x, BAY_WINDOW.splitY + upperHeight / 2, BAY_WINDOW.frontZ + 0.025))
    addGlass(group, materials, `bay-front-lower-glass-${index + 1}`, unitWidth - BAY_WINDOW.frame * 1.35, lowerHeight - BAY_WINDOW.frame * 1.3, new THREE.Vector3(x, BAY_WINDOW.sillY + lowerHeight / 2, BAY_WINDOW.frontZ + 0.025))
  }
}

function createSideWindow(group, materials, side) {
  const inner = new THREE.Vector3(side * BAY_WINDOW.frontWidth / 2, 0, BAY_WINDOW.frontZ)
  const outer = new THREE.Vector3(side * BAY_WINDOW.sideOuterX, 0, BAY_WINDOW.sideOuterZ)
  const center = inner.clone().add(outer).multiplyScalar(0.5)
  const width = inner.distanceTo(outer)
  const angle = side * Math.PI / 2
  const openingHeight = BAY_WINDOW.topY - BAY_WINDOW.sillY
  const upperHeight = BAY_WINDOW.topY - BAY_WINDOW.splitY
  const lowerHeight = BAY_WINDOW.splitY - BAY_WINDOW.sillY
  const panel = new THREE.Group()
  panel.name = `bay-${side < 0 ? 'left' : 'right'}-side-window`
  panel.position.set(center.x, 0, center.z)
  panel.rotation.y = angle
  group.add(panel)

  const shadow = { castShadow: true }
  addBox(panel, materials, `${panel.name}-top-frame`, new THREE.Vector3(width, 0.2, BAY_WINDOW.depth), new THREE.Vector3(0, BAY_WINDOW.topY, 0), 'frame', shadow)
  addBox(panel, materials, `${panel.name}-sill`, new THREE.Vector3(width + 0.12, 0.22, 0.48), new THREE.Vector3(0, BAY_WINDOW.sillY, 0.1), 'frame', shadow)
  const innerX = side < 0 ? -width / 2 : width / 2
  const outerX = -innerX
  addBox(panel, materials, `${panel.name}-inner-frame`, new THREE.Vector3(BAY_WINDOW.frame, openingHeight, BAY_WINDOW.depth), new THREE.Vector3(innerX, (BAY_WINDOW.sillY + BAY_WINDOW.topY) / 2, 0), 'frame', shadow)
  addBox(panel, materials, `${panel.name}-outer-frame`, new THREE.Vector3(BAY_WINDOW.frame, openingHeight, BAY_WINDOW.depth), new THREE.Vector3(outerX, (BAY_WINDOW.sillY + BAY_WINDOW.topY) / 2, 0), 'frame', shadow)
  addBox(panel, materials, `${panel.name}-crossbar`, new THREE.Vector3(width - BAY_WINDOW.frame * 0.45, BAY_WINDOW.frame, BAY_WINDOW.depth + 0.015), new THREE.Vector3(0, BAY_WINDOW.splitY, 0.015), 'frame', shadow)
  addGlass(panel, materials, `${panel.name}-upper-glass`, width - BAY_WINDOW.frame * 1.35, upperHeight - BAY_WINDOW.frame * 1.3, new THREE.Vector3(0, BAY_WINDOW.splitY + upperHeight / 2, 0.025))
  addGlass(panel, materials, `${panel.name}-lower-glass`, width - BAY_WINDOW.frame * 1.35, lowerHeight - BAY_WINDOW.frame * 1.3, new THREE.Vector3(0, BAY_WINDOW.sillY + lowerHeight / 2, 0.025))
}

export function createBayWindow({ materials, scenery = DEFAULT_SCENERY, textureLoader } = {}) {
  const group = new THREE.Group()
  group.name = 'bay-window'

  const sceneryMaterial = new THREE.MeshBasicMaterial({ color: '#eee9df', side: THREE.DoubleSide })
  const sceneryMesh = createSceneryPlane('seamless-outside-scenery', BAY_WINDOW.frontWidth + 0.5, 6.35, sceneryMaterial)
  sceneryMesh.position.set(0, 4.05, -5.42)
  group.add(sceneryMesh)

  const sideSceneryWidth = BAY_WINDOW.sideOuterZ - BAY_WINDOW.frontZ + 0.18
  const sideSceneryZ = (BAY_WINDOW.frontZ + BAY_WINDOW.sideOuterZ) / 2
  const leftScenery = createSceneryPlane('left-side-outside-scenery', sideSceneryWidth, 6.35, sceneryMaterial, 0, 0.2)
  leftScenery.position.set(-BAY_WINDOW.frontWidth / 2 - 0.32, 4.05, sideSceneryZ)
  leftScenery.rotation.y = -Math.PI / 2
  const rightScenery = createSceneryPlane('right-side-outside-scenery', sideSceneryWidth, 6.35, sceneryMaterial, 0.8, 1)
  rightScenery.position.set(BAY_WINDOW.frontWidth / 2 + 0.32, 4.05, sideSceneryZ)
  rightScenery.rotation.y = Math.PI / 2
  group.add(leftScenery, rightScenery)

  createFrontWindows(group, materials)
  createSideWindow(group, materials, -1)
  createSideWindow(group, materials, 1)

  const interactionProxy = new THREE.Mesh(
    new THREE.BoxGeometry(BAY_WINDOW.frontWidth - 0.2, BAY_WINDOW.topY - BAY_WINDOW.sillY - 0.2, 0.3),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
  )
  interactionProxy.name = 'window-interaction-proxy'
  interactionProxy.position.set(0, (BAY_WINDOW.sillY + BAY_WINDOW.topY) / 2, BAY_WINDOW.frontZ + 0.24)
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
