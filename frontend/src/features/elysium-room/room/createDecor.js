import * as THREE from 'three'
import { createOutlinedBox } from '../scene/primitives.js'
import { RECORD_WALL, ROOM } from './layout.js'

function addBox(parent, materials, name, size, position, materialKey, shadows = {}) {
  const object = createOutlinedBox(size, materialKey, materials, shadows)
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

function createFloorBoards(materials) {
  const points = []
  for (let x = ROOM.leftX + 0.45; x <= ROOM.rightX - 0.35; x += 0.72) {
    points.push(new THREE.Vector3(x, 0.014, ROOM.backZ + 0.15), new THREE.Vector3(x, 0.014, ROOM.frontZ - 0.1))
  }
  for (let z = ROOM.backZ + 1.1, row = 0; z < ROOM.frontZ; z += 1.3, row += 1) {
    const offset = row % 2 ? 0.36 : 0
    for (let x = ROOM.leftX + offset; x < ROOM.rightX; x += 2.16) {
      points.push(new THREE.Vector3(x, 0.016, z), new THREE.Vector3(Math.min(x + 0.72, ROOM.rightX), 0.016, z))
    }
  }
  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  const boards = new THREE.LineSegments(geometry, materials.get('floor').edge)
  boards.name = 'floor-boards'
  return boards
}

function createPhotoWall(materials) {
  const wall = new THREE.Group()
  wall.name = 'photo-grid'
  wall.position.set(RECORD_WALL.x - 0.13, 4.28, RECORD_WALL.z - 2.78)
  wall.rotation.y = -Math.PI / 2
  const wirePoints = []
  for (let x = -0.62; x <= 0.62; x += 0.21) {
    wirePoints.push(new THREE.Vector3(x, -1.08, 0), new THREE.Vector3(x, 1.08, 0))
  }
  for (let y = -1.08; y <= 1.08; y += 0.27) {
    wirePoints.push(new THREE.Vector3(-0.62, y, 0), new THREE.Vector3(0.62, y, 0))
  }
  const wires = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(wirePoints), materials.get('dark').edge)
  wires.name = 'photo-grid-wires'
  wall.add(wires)

  const photos = []
  const placements = [
    [-0.34, 0.65, -0.05, 0.34, 0.48], [0.34, 0.72, 0.03, 0.42, 0.56],
    [-0.28, 0.02, 0.04, 0.44, 0.58], [0.36, -0.17, -0.04, 0.34, 0.46],
    [-0.28, -0.7, 0.04, 0.38, 0.52], [0.32, -0.75, -0.02, 0.3, 0.4],
  ]
  placements.forEach(([x, y, rotation, width, height], index) => {
    const photo = addBox(wall, materials, `photo-${index + 1}`, new THREE.Vector3(width, height, 0.045), new THREE.Vector3(x, y, 0.06), 'paper')
    photo.rotation.z = rotation
    addBox(photo, materials, `photo-image-${index + 1}`, new THREE.Vector3(width * 0.7, height * 0.62, 0.02), new THREE.Vector3(0, 0.03, 0.04), index % 3 === 0 ? 'wood' : 'dark')
    photos.push(photo)
  })
  return { wall, photos }
}

function createMoviePoster(materials) {
  const poster = new THREE.Group()
  poster.name = 'movie-poster-frame'
  poster.position.set(RECORD_WALL.x - 0.12, 4.1, RECORD_WALL.z + 2.72)
  poster.rotation.y = -Math.PI / 2
  addBox(poster, materials, 'movie-poster-border', new THREE.Vector3(1.48, 2.28, 0.1), new THREE.Vector3(0, 0, 0), 'dark', { castShadow: true })
  addBox(poster, materials, 'movie-poster-paper', new THREE.Vector3(1.3, 2.08, 0.055), new THREE.Vector3(0, 0, 0.075), 'paper')
  addBox(poster, materials, 'movie-poster-title', new THREE.Vector3(0.88, 0.1, 0.025), new THREE.Vector3(0, 0.78, 0.12), 'dark')
  addBox(poster, materials, 'movie-poster-subtitle', new THREE.Vector3(0.56, 0.055, 0.025), new THREE.Vector3(0, 0.61, 0.12), 'dark')
  addBox(poster, materials, 'movie-poster-portrait-left', new THREE.Vector3(0.4, 0.83, 0.028), new THREE.Vector3(-0.24, -0.02, 0.12), 'wood')
  addBox(poster, materials, 'movie-poster-portrait-right', new THREE.Vector3(0.38, 0.72, 0.03), new THREE.Vector3(0.26, -0.16, 0.125), 'dark')
  addBox(poster, materials, 'movie-poster-credit-one', new THREE.Vector3(0.72, 0.05, 0.025), new THREE.Vector3(0, -0.75, 0.12), 'dark')
  addBox(poster, materials, 'movie-poster-credit-two', new THREE.Vector3(0.48, 0.04, 0.025), new THREE.Vector3(0, -0.88, 0.12), 'dark')
  return poster
}

export function createDecor({ materials }) {
  const group = new THREE.Group()
  group.name = 'room-decor'
  group.add(createFloorBoards(materials))
  const { wall: photoWall, photos } = createPhotoWall(materials)
  const moviePoster = createMoviePoster(materials)
  group.add(photoWall, moviePoster)
  const photoProxy = createProxy(photoWall, 'photoWall', new THREE.Vector3(1.48, 2.36, 0.34), new THREE.Vector3(0, 0, 0.14))
  const posterProxy = createProxy(moviePoster, 'moviePoster', new THREE.Vector3(1.68, 2.48, 0.34), new THREE.Vector3(0, 0, 0.16))
  return {
    group,
    registry: {
      photoWall: { visual: photoWall, proxy: photoProxy, label: 'Gallery', photos },
      moviePoster: { visual: moviePoster, proxy: posterProxy, label: 'Movies' },
    },
    dispose() {
      photoProxy.material.dispose()
      posterProxy.material.dispose()
    },
  }
}
