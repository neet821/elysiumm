import * as THREE from 'three'
import { createOutlinedBox } from '../scene/primitives.js'

function addBox(group, registry, name, size, position, materialKey, shadows = {}) {
  const box = createOutlinedBox(size, materialKey, registry, shadows)
  box.name = name
  box.position.copy(position)
  group.add(box)
  return box
}

export function createShell({ materials }) {
  const group = new THREE.Group()
  group.name = 'room-shell'
  const receivingSurface = { receiveShadow: true }
  const castingTrim = { castShadow: true }

  addBox(group, materials, 'floor', new THREE.Vector3(13.2, 0.3, 8.4), new THREE.Vector3(0, -0.15, 0), 'floor', receivingSurface)

  // The back wall stays open around the bay window instead of hiding it behind a full slab.
  addBox(group, materials, 'back-wall-left', new THREE.Vector3(2.2, 6.6, 0.25), new THREE.Vector3(-5.5, 3.3, -4.05), 'shell', receivingSurface)
  addBox(group, materials, 'back-wall-right', new THREE.Vector3(2.2, 6.6, 0.25), new THREE.Vector3(5.5, 3.3, -4.05), 'shell', receivingSurface)
  addBox(group, materials, 'back-wall-header', new THREE.Vector3(8.9, 1.15, 0.25), new THREE.Vector3(0, 6.025, -4.05), 'shell', receivingSurface)
  addBox(group, materials, 'back-wall-apron', new THREE.Vector3(8.9, 0.7, 0.25), new THREE.Vector3(0, 0.35, -4.05), 'shell', receivingSurface)
  addBox(group, materials, 'right-return', new THREE.Vector3(0.25, 6.6, 8.15), new THREE.Vector3(6.475, 3.3, 0), 'shell', receivingSurface)

  addBox(group, materials, 'back-base-trim-left', new THREE.Vector3(2.25, 0.28, 0.18), new THREE.Vector3(-5.48, 0.2, -3.86), 'trim', castingTrim)
  addBox(group, materials, 'back-base-trim-right', new THREE.Vector3(2.25, 0.28, 0.18), new THREE.Vector3(5.48, 0.2, -3.86), 'trim', castingTrim)
  addBox(group, materials, 'right-base-trim', new THREE.Vector3(0.18, 0.28, 7.9), new THREE.Vector3(6.29, 0.2, 0.04), 'trim', castingTrim)
  addBox(group, materials, 'back-crown-left', new THREE.Vector3(2.25, 0.24, 0.2), new THREE.Vector3(-5.48, 6.43, -3.84), 'trim', castingTrim)
  addBox(group, materials, 'back-crown-right', new THREE.Vector3(2.25, 0.24, 0.2), new THREE.Vector3(5.48, 6.43, -3.84), 'trim', castingTrim)
  addBox(group, materials, 'right-crown', new THREE.Vector3(0.2, 0.24, 7.9), new THREE.Vector3(6.27, 6.43, 0.04), 'trim', castingTrim)

  return group
}
