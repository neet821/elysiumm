import * as THREE from 'three'
import { createOutlinedBox, createOutlinedMesh } from '../scene/primitives.js'

function addBox(parent, materials, name, size, position, materialKey, shadows = {}) {
  const object = createOutlinedBox(size, materialKey, materials, shadows)
  object.name = name
  object.position.copy(position)
  parent.add(object)
  return object
}

function addCylinder(parent, materials, name, radiusTop, radiusBottom, height, position, materialKey, shadows = {}) {
  const object = createOutlinedMesh(
    new THREE.CylinderGeometry(radiusTop, radiusBottom, height, 20),
    materialKey,
    materials,
    shadows,
  )
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
  tonearm.position.set(0.58, 0.25, 0.12)
  addCylinder(tonearm, materials, 'tonearm-pivot', 0.1, 0.12, 0.16, new THREE.Vector3(0, 0, 0), 'metal')
  const arm = addCylinder(tonearm, materials, 'tonearm-arm', 0.025, 0.025, 0.72, new THREE.Vector3(-0.19, 0.06, 0.23), 'metal')
  arm.rotation.z = -0.72
  arm.rotation.x = 0.34
  addBox(tonearm, materials, 'tonearm-head', new THREE.Vector3(0.18, 0.08, 0.12), new THREE.Vector3(-0.42, 0.04, 0.45), 'dark')
  return tonearm
}

export function createRecordZone({ materials }) {
  const group = new THREE.Group()
  group.name = 'record-zone'
  group.position.set(6.12, 0, -0.05)
  group.rotation.y = -Math.PI / 2

  const cabinet = new THREE.Group()
  cabinet.name = 'record-cabinet'
  const cabinetShadows = { castShadow: true, receiveShadow: true }
  addBox(cabinet, materials, 'cabinet-top', new THREE.Vector3(5.2, 0.18, 0.92), new THREE.Vector3(0, 1.38, 0.46), 'dark', cabinetShadows)
  addBox(cabinet, materials, 'cabinet-bottom', new THREE.Vector3(5.2, 0.16, 0.88), new THREE.Vector3(0, 0.16, 0.44), 'dark', cabinetShadows)
  for (const x of [-2.5, -0.82, 0.82, 2.5]) {
    const dividerShadows = Math.abs(x) > 2 ? cabinetShadows : { receiveShadow: true }
    addBox(cabinet, materials, `cabinet-divider-${x}`, new THREE.Vector3(0.16, 1.18, 0.88), new THREE.Vector3(x, 0.76, 0.44), 'dark', dividerShadows)
  }
  addBox(cabinet, materials, 'cabinet-middle-shelf', new THREE.Vector3(1.52, 0.11, 0.82), new THREE.Vector3(0, 0.75, 0.42), 'dark', { receiveShadow: true })
  group.add(cabinet)

  const recordPlayer = new THREE.Group()
  recordPlayer.name = 'record-player'
  recordPlayer.position.set(-1.35, 1.53, 0.42)
  addBox(recordPlayer, materials, 'record-player-plinth', new THREE.Vector3(1.72, 0.18, 0.76), new THREE.Vector3(0, 0, 0), 'wood', { castShadow: true })
  const record = addCylinder(recordPlayer, materials, 'spinning-record', 0.48, 0.48, 0.055, new THREE.Vector3(-0.18, 0.13, 0), 'record', { castShadow: true })
  addCylinder(record, materials, 'record-label', 0.13, 0.13, 0.062, new THREE.Vector3(0, 0.005, 0), 'accent')
  const tonearm = createTonearm(materials)
  recordPlayer.add(tonearm)
  const cover = addBox(recordPlayer, materials, 'record-dust-cover', new THREE.Vector3(1.7, 0.06, 0.78), new THREE.Vector3(0, 0.67, -0.29), 'glass')
  cover.rotation.x = -1.0
  group.add(recordPlayer)

  const rack = new THREE.Group()
  rack.name = 'album-rack'
  rack.position.set(1.72, 1.48, 0.43)
  addBox(rack, materials, 'album-rack-base', new THREE.Vector3(1.68, 0.12, 0.78), new THREE.Vector3(0, 0.03, 0), 'dark', { castShadow: true })
  addBox(rack, materials, 'album-rack-left', new THREE.Vector3(0.1, 0.8, 0.76), new THREE.Vector3(-0.79, 0.42, 0), 'dark')
  addBox(rack, materials, 'album-rack-right', new THREE.Vector3(0.1, 0.8, 0.76), new THREE.Vector3(0.79, 0.42, 0), 'dark')
  const albumCards = []
  for (let index = 0; index < 15; index += 1) {
    const album = addBox(
      rack,
      materials,
      `album-${index + 1}`,
      new THREE.Vector3(0.055, 0.72 + (index % 3) * 0.035, 0.68),
      new THREE.Vector3(-0.65 + index * 0.093, 0.43, 0),
      index % 4 === 0 ? 'accent' : index % 3 === 0 ? 'paper' : 'wood',
      {},
    )
    album.rotation.z = (index % 5 === 0 ? -1 : index % 6 === 0 ? 1 : 0) * 0.05
    albumCards.push(album)
  }
  group.add(rack)

  const shelves = new THREE.Group()
  shelves.name = 'wall-shelves'
  for (const [index, y] of [2.8, 3.75, 4.7].entries()) {
    addBox(shelves, materials, `wall-shelf-${index + 1}`, new THREE.Vector3(3.5, 0.13, 0.56), new THREE.Vector3(0, y, 0.3), 'wood', { castShadow: true })
  }
  group.add(shelves)

  const books = new THREE.Group()
  books.name = 'book-collection'
  books.position.set(0, 3.02, 0.34)
  for (let index = 0; index < 12; index += 1) {
    const width = 0.16 + (index % 3) * 0.035
    const book = addBox(
      books,
      materials,
      `book-${index + 1}`,
      new THREE.Vector3(width, 0.58 + (index % 4) * 0.055, 0.38),
      new THREE.Vector3(-1.38 + index * 0.24, 0.31, 0),
      index % 4 === 0 ? 'accent' : index % 3 === 0 ? 'wood' : 'paper',
      {},
    )
    book.rotation.z = index === 10 ? -0.12 : 0
  }
  group.add(books)

  const cds = new THREE.Group()
  cds.name = 'compact-disc-row'
  cds.position.set(0.45, 3.96, 0.34)
  for (let index = 0; index < 20; index += 1) {
    addBox(cds, materials, `compact-disc-${index + 1}`, new THREE.Vector3(0.07, 0.46, 0.34), new THREE.Vector3(-1.0 + index * 0.1, 0.24, 0), index % 5 === 0 ? 'accent' : 'paper')
  }
  group.add(cds)

  const shelfPlant = new THREE.Group()
  shelfPlant.name = 'shelf-plant'
  shelfPlant.position.set(-0.95, 4.76, 0.34)
  addCylinder(shelfPlant, materials, 'shelf-plant-pot', 0.2, 0.14, 0.34, new THREE.Vector3(0, 0.17, 0), 'paper')
  const leaves = createOutlinedMesh(new THREE.SphereGeometry(0.28, 12, 8), 'plant', materials)
  leaves.name = 'shelf-plant-leaves'
  leaves.position.set(0, 0.47, 0)
  leaves.scale.set(0.85, 1.2, 0.85)
  shelfPlant.add(leaves)
  group.add(shelfPlant)

  const playerProxy = createProxy(group, 'recordPlayer', new THREE.Vector3(2.0, 1.15, 1.1), new THREE.Vector3(-1.35, 1.9, 0.48))
  const rackProxy = createProxy(group, 'recordRack', new THREE.Vector3(1.9, 1.35, 1.05), new THREE.Vector3(1.72, 1.95, 0.47))
  const booksProxy = createProxy(group, 'books', new THREE.Vector3(3.3, 0.9, 0.8), new THREE.Vector3(0, 3.32, 0.42))

  return {
    group,
    registry: {
      recordPlayer: {
        visual: recordPlayer,
        proxy: playerProxy,
        label: 'Record player',
        record,
        tonearm,
      },
      recordRack: {
        visual: rack,
        proxy: rackProxy,
        label: 'Album collection',
        albums: albumCards,
      },
      books: { visual: books, proxy: booksProxy, label: 'Reading list' },
    },
    dispose() {
      playerProxy.material.dispose()
      rackProxy.material.dispose()
      booksProxy.material.dispose()
    },
  }
}
