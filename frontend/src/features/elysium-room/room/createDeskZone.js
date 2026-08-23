import * as THREE from 'three'
import { createOutlinedBox, createOutlinedMesh } from '../scene/primitives.js'
import { DESK } from './layout.js'

function addBox(parent, materials, name, size, position, materialKey, shadows = {}) {
  const object = createOutlinedBox(size, materialKey, materials, shadows)
  object.name = name
  object.position.copy(position)
  parent.add(object)
  return object
}

function addCylinder(parent, materials, name, radiusTop, radiusBottom, height, position, materialKey, shadows = {}) {
  const object = createOutlinedMesh(new THREE.CylinderGeometry(radiusTop, radiusBottom, height, 18), materialKey, materials, shadows)
  object.name = name
  object.position.copy(position)
  parent.add(object)
  return object
}

function createProxy(parent, id, size, position) {
  const material = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false })
  const proxy = new THREE.Mesh(new THREE.BoxGeometry(size.x, size.y, size.z), material)
  proxy.name = `${id}-interaction-proxy`
  proxy.position.copy(position)
  proxy.userData.interactionId = id
  parent.add(proxy)
  return proxy
}

export function createDeskZone({ materials }) {
  const group = new THREE.Group()
  group.name = 'desk-zone'
  const majorShadow = { castShadow: true, receiveShadow: true }

  addBox(group, materials, 'desk-top', new THREE.Vector3(DESK.width, DESK.topThickness, DESK.depth), new THREE.Vector3(DESK.x, DESK.topY, DESK.z), 'wood', majorShadow)
  addBox(group, materials, 'desk-front-edge', new THREE.Vector3(DESK.width - 0.18, 0.14, 0.12), new THREE.Vector3(DESK.x, DESK.topY - 0.13, DESK.z + DESK.depth / 2 - 0.03), 'wood', { receiveShadow: true })
  addBox(group, materials, 'desk-leg-left', new THREE.Vector3(0.34, DESK.topY - 0.2, DESK.depth - 0.14), new THREE.Vector3(DESK.x - DESK.width / 2 + 0.42, (DESK.topY - 0.2) / 2, DESK.z), 'dark', majorShadow)
  addBox(group, materials, 'desk-leg-right', new THREE.Vector3(0.34, DESK.topY - 0.2, DESK.depth - 0.14), new THREE.Vector3(DESK.x + DESK.width / 2 - 0.42, (DESK.topY - 0.2) / 2, DESK.z), 'dark', majorShadow)

  for (const x of [-0.72, 0.72]) {
    addBox(group, materials, `desk-drawer-seam-${x}`, new THREE.Vector3(0.04, 0.11, 0.018), new THREE.Vector3(DESK.x + x, DESK.topY - 0.04, DESK.z + DESK.depth / 2 + 0.012), 'dark')
  }

  const monitor = new THREE.Group()
  monitor.name = 'monitor'
  monitor.position.set(DESK.x - 0.25, DESK.topY + 0.18, DESK.z - 0.04)
  addBox(monitor, materials, 'monitor-screen', new THREE.Vector3(1.72, 1.08, 0.12), new THREE.Vector3(0, 0.66, 0), 'screen', { castShadow: true })
  addBox(monitor, materials, 'monitor-chin', new THREE.Vector3(1.72, 0.18, 0.14), new THREE.Vector3(0, 0.12, 0.006), 'metal')
  addBox(monitor, materials, 'monitor-neck', new THREE.Vector3(0.16, 0.38, 0.14), new THREE.Vector3(0, -0.16, 0), 'metal')
  addBox(monitor, materials, 'monitor-foot', new THREE.Vector3(0.65, 0.07, 0.38), new THREE.Vector3(0, -0.35, 0.08), 'metal')
  group.add(monitor)

  const keyboard = addBox(group, materials, 'keyboard', new THREE.Vector3(1.25, 0.055, 0.34), new THREE.Vector3(DESK.x - 0.25, DESK.topY + 0.18, DESK.z + 0.4), 'paper')
  keyboard.rotation.x = -0.05

  const lamp = new THREE.Group()
  lamp.name = 'desk-lamp'
  lamp.position.set(DESK.x + 1.45, DESK.topY + 0.18, DESK.z - 0.02)
  addCylinder(lamp, materials, 'desk-lamp-base', 0.3, 0.34, 0.1, new THREE.Vector3(0, 0.02, 0), 'dark', { castShadow: true })
  addCylinder(lamp, materials, 'desk-lamp-stem', 0.04, 0.04, 0.54, new THREE.Vector3(0, 0.33, 0), 'dark')
  const bulb = createOutlinedMesh(new THREE.SphereGeometry(0.11, 14, 8), 'paper', materials)
  bulb.name = 'desk-lamp-bulb'
  bulb.position.set(0, 0.59, 0)
  lamp.add(bulb)
  const shade = createOutlinedMesh(new THREE.SphereGeometry(0.34, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2), 'dark', materials, { castShadow: true })
  shade.name = 'desk-lamp-shade'
  shade.position.set(0, 0.61, 0)
  lamp.add(shade)
  addCylinder(lamp, materials, 'desk-lamp-rim', 0.36, 0.36, 0.055, new THREE.Vector3(0, 0.6, 0), 'dark')
  group.add(lamp)

  const monitorProxy = createProxy(group, 'monitor', new THREE.Vector3(1.92, 1.55, 0.44), new THREE.Vector3(DESK.x - 0.25, DESK.topY + 0.73, DESK.z + 0.08))
  const lampProxy = createProxy(group, 'lamp', new THREE.Vector3(0.95, 1.18, 0.78), new THREE.Vector3(DESK.x + 1.45, DESK.topY + 0.54, DESK.z + 0.02))

  return {
    group,
    registry: {
      monitor: { visual: monitor, proxy: monitorProxy, label: 'Projects' },
      lamp: { visual: lamp, proxy: lampProxy, label: 'Lamp', shade, bulb },
    },
    dispose() {
      monitorProxy.material.dispose()
      lampProxy.material.dispose()
    },
  }
}
