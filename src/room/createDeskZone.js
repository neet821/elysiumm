import * as THREE from 'three'
import { createOutlinedBox, createOutlinedMesh } from '../scene/primitives.js'

function addBox(parent, materials, name, size, position, materialKey, shadows = {}) {
  const object = createOutlinedBox(size, materialKey, materials, shadows)
  object.name = name
  object.position.copy(position)
  parent.add(object)
  return object
}

function addCylinder(parent, materials, name, radiusTop, radiusBottom, height, position, materialKey) {
  const object = createOutlinedMesh(
    new THREE.CylinderGeometry(radiusTop, radiusBottom, height, 16),
    materialKey,
    materials,
    { castShadow: true },
  )
  object.name = name
  object.position.copy(position)
  parent.add(object)
  return object
}

function addSphere(parent, materials, name, radius, position, scale, materialKey) {
  const object = createOutlinedMesh(
    new THREE.SphereGeometry(radius, 16, 10),
    materialKey,
    materials,
    { castShadow: true },
  )
  object.name = name
  object.position.copy(position)
  object.scale.copy(scale)
  parent.add(object)
  return object
}

function createProxy(parent, id, size, position) {
  const material = new THREE.MeshBasicMaterial({
    transparent: true,
    opacity: 0,
    depthWrite: false,
  })
  const proxy = new THREE.Mesh(new THREE.BoxGeometry(size.x, size.y, size.z), material)
  proxy.name = `${id}-interaction-proxy`
  proxy.position.copy(position)
  proxy.userData.interactionId = id
  parent.add(proxy)
  return proxy
}

function addCable(parent, materials) {
  const geometry = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(-1.2, 2.3, -2.76),
    new THREE.Vector3(-1.15, 1.76, -2.8),
    new THREE.Vector3(-0.5, 1.1, -2.9),
    new THREE.Vector3(-0.1, 0.18, -3.18),
  ])
  const cable = new THREE.Line(geometry, materials.get('dark').edge)
  cable.name = 'monitor-cable'
  parent.add(cable)
}

export function createDeskZone({ materials }) {
  const group = new THREE.Group()
  group.name = 'desk-zone'

  const shadowed = { castShadow: true, receiveShadow: true }
  addBox(group, materials, 'desk-top', new THREE.Vector3(6.1, 0.3, 1.3), new THREE.Vector3(-1.2, 1.83, -2.65), 'wood', shadowed)
  addBox(group, materials, 'desk-apron', new THREE.Vector3(5.7, 0.22, 0.16), new THREE.Vector3(-1.2, 1.57, -2.12), 'wood', shadowed)
  addBox(group, materials, 'desk-leg-left', new THREE.Vector3(0.32, 1.68, 1.08), new THREE.Vector3(-4.0, 0.84, -2.65), 'dark', shadowed)
  addBox(group, materials, 'desk-leg-right', new THREE.Vector3(0.32, 1.68, 1.08), new THREE.Vector3(1.6, 0.84, -2.65), 'dark', shadowed)

  const monitor = new THREE.Group()
  monitor.name = 'monitor'
  monitor.position.set(-1.25, 2.75, -2.68)
  addBox(monitor, materials, 'monitor-screen', new THREE.Vector3(1.85, 1.15, 0.14), new THREE.Vector3(0, 0.25, 0), 'screen', { castShadow: true })
  addBox(monitor, materials, 'monitor-chin', new THREE.Vector3(1.85, 0.19, 0.16), new THREE.Vector3(0, -0.32, 0.005), 'metal', { castShadow: true })
  addBox(monitor, materials, 'monitor-neck', new THREE.Vector3(0.17, 0.42, 0.14), new THREE.Vector3(0, -0.68, 0), 'metal', { castShadow: true })
  addBox(monitor, materials, 'monitor-foot', new THREE.Vector3(0.72, 0.08, 0.42), new THREE.Vector3(0, -0.88, 0.06), 'metal', { castShadow: true })
  group.add(monitor)

  const keyboard = addBox(group, materials, 'keyboard', new THREE.Vector3(1.55, 0.09, 0.43), new THREE.Vector3(-1.25, 2.04, -2.12), 'paper', { castShadow: true })
  keyboard.rotation.x = -0.08
  addBox(group, materials, 'desk-notebook', new THREE.Vector3(0.65, 0.08, 0.78), new THREE.Vector3(-2.65, 2.04, -2.52), 'paper', { castShadow: true })
  addCylinder(group, materials, 'desk-pencil-cup', 0.16, 0.13, 0.32, new THREE.Vector3(-3.35, 2.12, -2.76), 'metal')

  const lamp = new THREE.Group()
  lamp.name = 'desk-lamp'
  lamp.position.set(0.85, 2.02, -2.66)
  addCylinder(lamp, materials, 'desk-lamp-base', 0.34, 0.38, 0.11, new THREE.Vector3(0, 0.03, 0), 'dark')
  addCylinder(lamp, materials, 'desk-lamp-stem', 0.055, 0.055, 0.62, new THREE.Vector3(0, 0.38, 0), 'dark')
  const bulb = addSphere(lamp, materials, 'desk-lamp-bulb', 0.13, new THREE.Vector3(0, 0.7, 0), new THREE.Vector3(1, 0.9, 1), 'paper')
  const shade = addSphere(lamp, materials, 'desk-lamp-shade', 0.42, new THREE.Vector3(0, 0.77, 0), new THREE.Vector3(1, 0.55, 1), 'dark')
  shade.rotation.x = Math.PI
  group.add(lamp)

  const chair = new THREE.Group()
  chair.name = 'desk-chair'
  chair.position.set(-1.15, 0, -0.86)
  addBox(chair, materials, 'chair-seat', new THREE.Vector3(1.1, 0.18, 1.0), new THREE.Vector3(0, 1.05, 0), 'dark', { castShadow: true })
  const chairBack = addBox(chair, materials, 'chair-back', new THREE.Vector3(1.08, 1.22, 0.18), new THREE.Vector3(0, 1.72, 0.42), 'dark', { castShadow: true })
  chairBack.rotation.x = -0.08
  addCylinder(chair, materials, 'chair-column', 0.09, 0.12, 0.82, new THREE.Vector3(0, 0.56, 0), 'metal')
  for (let index = 0; index < 5; index += 1) {
    const spoke = addBox(chair, materials, `chair-spoke-${index}`, new THREE.Vector3(0.75, 0.07, 0.08), new THREE.Vector3(0, 0.16, 0), 'metal')
    spoke.rotation.y = (index / 5) * Math.PI * 2
  }
  group.add(chair)

  const plant = new THREE.Group()
  plant.name = 'desk-plant'
  plant.position.set(-3.35, 2.02, -2.32)
  addCylinder(plant, materials, 'desk-plant-pot', 0.21, 0.15, 0.34, new THREE.Vector3(0, 0.16, 0), 'paper')
  addSphere(plant, materials, 'desk-plant-leaves', 0.28, new THREE.Vector3(0, 0.48, 0), new THREE.Vector3(0.8, 1.25, 0.8), 'plant')
  group.add(plant)
  addCable(group, materials)

  const monitorProxy = createProxy(group, 'monitor', new THREE.Vector3(2.1, 1.8, 0.5), new THREE.Vector3(-1.25, 2.85, -2.56))
  const lampProxy = createProxy(group, 'lamp', new THREE.Vector3(1.0, 1.35, 0.85), new THREE.Vector3(0.85, 2.48, -2.62))

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
