import * as THREE from 'three'
import { createOutlinedBox, createOutlinedMesh } from '../scene/primitives.js'
import { RECORD_WALL } from './layout.js'

function addBox(parent, materials, name, size, position, materialKey, shadows = {}) {
  const object = createOutlinedBox(size, materialKey, materials, shadows)
  object.name = name
  object.position.copy(position)
  parent.add(object)
  return object
}

function addCylinder(parent, materials, name, radiusTop, radiusBottom, height, position, materialKey, shadows = {}) {
  const object = createOutlinedMesh(new THREE.CylinderGeometry(radiusTop, radiusBottom, height, 20), materialKey, materials, shadows)
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

function createTonearm(materials) {
  const tonearm = new THREE.Group()
  tonearm.name = 'record-tonearm'
  tonearm.position.set(0.5, 0.23, 0.1)
  addCylinder(tonearm, materials, 'tonearm-pivot', 0.09, 0.11, 0.14, new THREE.Vector3(0, 0, 0), 'metal')
  const arm = addCylinder(tonearm, materials, 'tonearm-arm', 0.022, 0.022, 0.66, new THREE.Vector3(-0.18, 0.05, 0.2), 'metal')
  arm.rotation.z = -0.72
  arm.rotation.x = 0.32
  addBox(tonearm, materials, 'tonearm-head', new THREE.Vector3(0.16, 0.07, 0.11), new THREE.Vector3(-0.4, 0.03, 0.41), 'dark')
  return tonearm
}

function createCabinet(group, materials) {
  const cabinet = new THREE.Group()
  cabinet.name = 'record-cabinet'
  const { cabinetWidth: width, cabinetHeight: height, cabinetDepth: depth } = RECORD_WALL
  const shadow = { castShadow: true, receiveShadow: true }
  addBox(cabinet, materials, 'cabinet-top', new THREE.Vector3(width, 0.16, depth), new THREE.Vector3(0, height, depth / 2), 'dark', shadow)
  addBox(cabinet, materials, 'cabinet-bottom', new THREE.Vector3(width, 0.14, depth - 0.04), new THREE.Vector3(0, 0.1, depth / 2), 'dark', shadow)
  addBox(cabinet, materials, 'cabinet-left-side', new THREE.Vector3(0.16, height, depth), new THREE.Vector3(-width / 2 + 0.08, height / 2, depth / 2), 'dark', shadow)
  addBox(cabinet, materials, 'cabinet-right-side', new THREE.Vector3(0.16, height, depth), new THREE.Vector3(width / 2 - 0.08, height / 2, depth / 2), 'dark', shadow)

  const division = 1.18
  addBox(cabinet, materials, 'cabinet-divider-left', new THREE.Vector3(0.13, height - 0.12, depth - 0.04), new THREE.Vector3(-division, height / 2, depth / 2), 'dark', { receiveShadow: true })
  addBox(cabinet, materials, 'cabinet-divider-right', new THREE.Vector3(0.13, height - 0.12, depth - 0.04), new THREE.Vector3(division, height / 2, depth / 2), 'dark', { receiveShadow: true })

  addBox(cabinet, materials, 'cabinet-left-door', new THREE.Vector3(width / 2 - division - 0.15, height - 0.28, 0.1), new THREE.Vector3(-(width / 2 + division) / 2, height / 2, depth + 0.01), 'dark', { castShadow: true })
  addBox(cabinet, materials, 'cabinet-right-door', new THREE.Vector3(width / 2 - division - 0.15, height - 0.28, 0.1), new THREE.Vector3((width / 2 + division) / 2, height / 2, depth + 0.01), 'dark', { castShadow: true })
  addBox(cabinet, materials, 'cabinet-open-shelf', new THREE.Vector3(2.18, 0.1, depth - 0.12), new THREE.Vector3(0, height * 0.54, depth / 2), 'dark', { receiveShadow: true })

  for (let index = 0; index < 8; index += 1) {
    addBox(cabinet, materials, `cabinet-record-${index + 1}`, new THREE.Vector3(0.08, 0.5, 0.58), new THREE.Vector3(-0.75 + index * 0.18, 0.33, depth * 0.58), index % 3 === 0 ? 'wood' : 'paper')
  }
  for (let index = 0; index < 3; index += 1) {
    addBox(cabinet, materials, `cabinet-book-${index + 1}`, new THREE.Vector3(0.72 - index * 0.08, 0.08, 0.5), new THREE.Vector3(0.15, height * 0.62 + index * 0.09, depth * 0.56), index === 1 ? 'wood' : 'paper')
  }
  group.add(cabinet)
  return cabinet
}

function createShelfCollections(group, materials) {
  const shelves = new THREE.Group()
  shelves.name = 'wall-shelves'
  const levels = [3.02, 4.12, 5.18]
  const widths = [3.35, 3.45, 2.7]
  const centers = [-0.2, -0.2, -0.52]
  levels.forEach((y, index) => {
    addBox(shelves, materials, `wall-shelf-${index + 1}`, new THREE.Vector3(widths[index], 0.13, 0.52), new THREE.Vector3(centers[index], y, 0.28), 'wood', { castShadow: true })
  })

  const albumDisplay = new THREE.Group()
  albumDisplay.name = 'shelf-album-display'
  for (let index = 0; index < 3; index += 1) {
    const cover = addBox(albumDisplay, materials, `display-album-${index + 1}`, new THREE.Vector3(0.8, 0.86, 0.07), new THREE.Vector3(-1.02 + index * 0.9, 3.51 + (index % 2) * 0.04, 0.41), index === 1 ? 'dark' : index === 2 ? 'paper' : 'accent')
    cover.rotation.x = -0.12
    addBox(cover, materials, `display-album-art-${index + 1}`, new THREE.Vector3(0.46, 0.48, 0.025), new THREE.Vector3(0, 0.03, 0.055), index === 1 ? 'paper' : 'dark')
  }
  shelves.add(albumDisplay)

  const books = new THREE.Group()
  books.name = 'book-collection'
  for (let index = 0; index < 18; index += 1) {
    addBox(books, materials, `compact-disc-${index + 1}`, new THREE.Vector3(0.075, 0.43, 0.32), new THREE.Vector3(-1.25 + index * 0.11, 4.4, 0.34), index % 7 === 0 ? 'wood' : 'paper')
  }
  shelves.add(books)

  const topPlant = new THREE.Group()
  topPlant.name = 'shelf-plant'
  topPlant.position.set(-1.25, 5.28, 0.32)
  addCylinder(topPlant, materials, 'shelf-plant-pot', 0.18, 0.14, 0.3, new THREE.Vector3(0, 0.15, 0), 'paper')
  const leaves = createOutlinedMesh(new THREE.SphereGeometry(0.24, 12, 8), 'plant', materials)
  leaves.name = 'shelf-plant-leaves'
  leaves.position.set(0, 0.43, 0)
  leaves.scale.set(0.9, 1.25, 0.85)
  topPlant.add(leaves)
  shelves.add(topPlant)

  const middlePlant = new THREE.Group()
  middlePlant.name = 'middle-shelf-plant'
  middlePlant.position.set(1.18, 4.2, 0.34)
  addCylinder(middlePlant, materials, 'middle-shelf-plant-pot', 0.14, 0.11, 0.24, new THREE.Vector3(0, 0.12, 0), 'paper')
  const middleLeaves = createOutlinedMesh(new THREE.SphereGeometry(0.18, 12, 8), 'plant', materials)
  middleLeaves.name = 'middle-shelf-plant-leaves'
  middleLeaves.position.set(0, 0.34, 0)
  middleLeaves.scale.set(0.85, 1.2, 0.85)
  middlePlant.add(middleLeaves)
  shelves.add(middlePlant)

  for (const [index, x, height] of [[1, -0.45, 0.66], [2, 0.28, 0.54]]) {
    const frame = addBox(shelves, materials, `shelf-photo-frame-${index}`, new THREE.Vector3(0.48, height, 0.08), new THREE.Vector3(x, 5.55 + (height - 0.54) / 2, 0.37), 'dark')
    addBox(frame, materials, `shelf-photo-paper-${index}`, new THREE.Vector3(0.36, height - 0.12, 0.03), new THREE.Vector3(0, 0, 0.055), 'paper')
    addBox(frame, materials, `shelf-photo-image-${index}`, new THREE.Vector3(0.22, height * 0.5, 0.02), new THREE.Vector3(0, 0.01, 0.082), index === 1 ? 'wood' : 'dark')
  }
  group.add(shelves)
  return { shelves, books }
}

export function createRecordZone({ materials }) {
  const group = new THREE.Group()
  group.name = 'record-zone'
  group.position.set(RECORD_WALL.x, 0, RECORD_WALL.z)
  group.rotation.y = -Math.PI / 2

  createCabinet(group, materials)

  const recordPlayer = new THREE.Group()
  recordPlayer.name = 'record-player'
  recordPlayer.position.set(-0.7, RECORD_WALL.cabinetHeight + 0.2, 0.48)
  addBox(recordPlayer, materials, 'record-player-plinth', new THREE.Vector3(1.62, 0.16, 0.74), new THREE.Vector3(0, 0, 0), 'wood', { castShadow: true })
  const record = addCylinder(recordPlayer, materials, 'spinning-record', 0.44, 0.44, 0.05, new THREE.Vector3(-0.16, 0.12, 0), 'record', { castShadow: true })
  addCylinder(record, materials, 'record-label', 0.12, 0.12, 0.055, new THREE.Vector3(0, 0.004, 0), 'accent')
  const tonearm = createTonearm(materials)
  recordPlayer.add(tonearm)
  const cover = addBox(recordPlayer, materials, 'record-dust-cover', new THREE.Vector3(1.62, 0.045, 0.75), new THREE.Vector3(0, 0.62, -0.28), 'glass')
  cover.rotation.x = -1.02
  group.add(recordPlayer)

  const rack = new THREE.Group()
  rack.name = 'album-rack'
  rack.position.set(2.05, RECORD_WALL.cabinetHeight + 0.15, 0.48)
  addBox(rack, materials, 'album-rack-base', new THREE.Vector3(1.62, 0.1, 0.72), new THREE.Vector3(0, 0.03, 0), 'dark', { castShadow: true })
  addBox(rack, materials, 'album-rack-left', new THREE.Vector3(0.08, 0.78, 0.7), new THREE.Vector3(-0.77, 0.42, 0), 'dark')
  addBox(rack, materials, 'album-rack-right', new THREE.Vector3(0.08, 0.78, 0.7), new THREE.Vector3(0.77, 0.42, 0), 'dark')
  const albumCards = []
  for (let index = 0; index < 13; index += 1) {
    const album = addBox(rack, materials, `album-${index + 1}`, new THREE.Vector3(0.06, 0.7 + (index % 3) * 0.03, 0.62), new THREE.Vector3(-0.64 + index * 0.105, 0.4, 0), index % 5 === 0 ? 'wood' : index % 4 === 0 ? 'accent' : 'paper')
    album.rotation.z = index % 6 === 0 ? -0.04 : 0
    albumCards.push(album)
  }
  group.add(rack)

  const { books } = createShelfCollections(group, materials)
  const playerProxy = createProxy(group, 'recordPlayer', new THREE.Vector3(1.85, 1.15, 1.0), new THREE.Vector3(-0.7, 1.95, 0.5))
  const rackProxy = createProxy(group, 'recordRack', new THREE.Vector3(1.85, 1.2, 1.0), new THREE.Vector3(2.05, 2.0, 0.5))
  const booksProxy = createProxy(group, 'books', new THREE.Vector3(2.4, 0.82, 0.72), new THREE.Vector3(-0.3, 4.42, 0.42))

  return {
    group,
    registry: {
      recordPlayer: { visual: recordPlayer, proxy: playerProxy, label: 'Record player', record, tonearm },
      recordRack: { visual: rack, proxy: rackProxy, label: 'Album collection', albums: albumCards },
      books: { visual: books, proxy: booksProxy, label: 'Reading list' },
    },
    dispose() {
      playerProxy.material.dispose()
      rackProxy.material.dispose()
      booksProxy.material.dispose()
    },
  }
}
