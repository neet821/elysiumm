import * as THREE from 'three'
import { createOutlinedBox } from '../scene/primitives.js'
import { BAY_WINDOW, ROOM } from './layout.js'

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
  const receive = { receiveShadow: true }

  addBox(
    group,
    materials,
    'floor',
    new THREE.Vector3(ROOM.width, 0.24, ROOM.depth),
    new THREE.Vector3(0, -0.12, ROOM.centerZ),
    'floor',
    receive,
  )
  addBox(
    group,
    materials,
    'ceiling',
    new THREE.Vector3(ROOM.width, 0.18, ROOM.depth),
    new THREE.Vector3(0, ROOM.height + 0.09, ROOM.centerZ),
    'trim',
    receive,
  )

  addBox(group, materials, 'left-wall', new THREE.Vector3(0.22, ROOM.height, ROOM.depth), new THREE.Vector3(ROOM.leftX, ROOM.height / 2, ROOM.centerZ), 'shell', receive)
  addBox(group, materials, 'right-wall', new THREE.Vector3(0.22, ROOM.height, ROOM.depth), new THREE.Vector3(ROOM.rightX, ROOM.height / 2, ROOM.centerZ), 'shell', receive)

  const sideWidth = ROOM.width / 2 - BAY_WINDOW.sideOuterX
  addBox(group, materials, 'back-wall-left', new THREE.Vector3(sideWidth, ROOM.height, 0.24), new THREE.Vector3(-(BAY_WINDOW.sideOuterX + sideWidth / 2), ROOM.height / 2, ROOM.backZ), 'shell', receive)
  addBox(group, materials, 'back-wall-right', new THREE.Vector3(sideWidth, ROOM.height, 0.24), new THREE.Vector3(BAY_WINDOW.sideOuterX + sideWidth / 2, ROOM.height / 2, ROOM.backZ), 'shell', receive)
  addBox(group, materials, 'back-wall-header', new THREE.Vector3(BAY_WINDOW.sideOuterX * 2, ROOM.height - BAY_WINDOW.topY, 0.24), new THREE.Vector3(0, (ROOM.height + BAY_WINDOW.topY) / 2, ROOM.backZ), 'shell', receive)
  addBox(group, materials, 'back-wall-apron', new THREE.Vector3(BAY_WINDOW.sideOuterX * 2, BAY_WINDOW.sillY, 0.24), new THREE.Vector3(0, BAY_WINDOW.sillY / 2, ROOM.backZ), 'shell', receive)

  const trimShadow = { castShadow: true, receiveShadow: true }
  addBox(group, materials, 'left-base-trim', new THREE.Vector3(0.18, 0.3, ROOM.depth - 0.2), new THREE.Vector3(ROOM.leftX + 0.16, 0.2, ROOM.centerZ), 'trim', trimShadow)
  addBox(group, materials, 'right-base-trim', new THREE.Vector3(0.18, 0.3, ROOM.depth - 0.2), new THREE.Vector3(ROOM.rightX - 0.16, 0.2, ROOM.centerZ), 'trim', trimShadow)
  addBox(group, materials, 'back-base-trim-left', new THREE.Vector3(sideWidth, 0.3, 0.18), new THREE.Vector3(-(BAY_WINDOW.sideOuterX + sideWidth / 2), 0.2, ROOM.backZ + 0.16), 'trim', trimShadow)
  addBox(group, materials, 'back-base-trim-right', new THREE.Vector3(sideWidth, 0.3, 0.18), new THREE.Vector3(BAY_WINDOW.sideOuterX + sideWidth / 2, 0.2, ROOM.backZ + 0.16), 'trim', trimShadow)

  addBox(group, materials, 'left-crown', new THREE.Vector3(0.2, 0.22, ROOM.depth - 0.12), new THREE.Vector3(ROOM.leftX + 0.17, ROOM.height - 0.16, ROOM.centerZ), 'trim', trimShadow)
  addBox(group, materials, 'right-crown', new THREE.Vector3(0.2, 0.22, ROOM.depth - 0.12), new THREE.Vector3(ROOM.rightX - 0.17, ROOM.height - 0.16, ROOM.centerZ), 'trim', trimShadow)
  addBox(group, materials, 'back-crown', new THREE.Vector3(ROOM.width - 0.2, 0.22, 0.2), new THREE.Vector3(0, ROOM.height - 0.16, ROOM.backZ + 0.17), 'trim', trimShadow)

  return group
}
