import * as THREE from 'three'
import { createOutlinedBox } from '../scene/primitives.js'

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
  for (let x = -6.2; x <= 6.2; x += 0.62) {
    points.push(new THREE.Vector3(x, 0.012, -3.85), new THREE.Vector3(x, 0.012, 4.05))
  }
  for (let z = -3.2; z <= 3.6; z += 1.15) {
    const offset = Math.round((z + 3.2) / 1.15) % 2 === 0 ? 0 : 0.31
    for (let x = -6.2 + offset; x < 6.2; x += 1.86) {
      points.push(new THREE.Vector3(x, 0.014, z), new THREE.Vector3(Math.min(x + 0.62, 6.2), 0.014, z))
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
  wall.position.set(6.22, 4.15, -2.66)
  wall.rotation.y = -Math.PI / 2

  const wirePoints = []
  for (let x = -0.72; x <= 0.72; x += 0.24) {
    wirePoints.push(new THREE.Vector3(x, -1.12, 0), new THREE.Vector3(x, 1.12, 0))
  }
  for (let y = -1.12; y <= 1.12; y += 0.28) {
    wirePoints.push(new THREE.Vector3(-0.72, y, 0), new THREE.Vector3(0.72, y, 0))
  }
  const wireGeometry = new THREE.BufferGeometry().setFromPoints(wirePoints)
  const wires = new THREE.LineSegments(wireGeometry, materials.get('paper').edge)
  wires.name = 'photo-grid-wires'
  wall.add(wires)
  const photos = []
  const placements = [
    [-0.42, 0.63, -0.04, 0.34, 0.48],
    [0.36, 0.72, -0.02, 0.42, 0.54],
    [-0.3, -0.02, 0.03, 0.48, 0.58],
    [0.4, -0.2, -0.05, 0.36, 0.46],
    [-0.32, -0.72, 0.04, 0.38, 0.5],
  ]
  placements.forEach(([x, y, rotation, width, height], index) => {
    const photo = addBox(wall, materials, `photo-${index + 1}`, new THREE.Vector3(width, height, 0.065), new THREE.Vector3(x, y, 0.07), index % 2 === 0 ? 'paper' : 'wood')
    photo.rotation.z = rotation
    addBox(photo, materials, `photo-image-${index + 1}`, new THREE.Vector3(width * 0.7, height * 0.62, 0.025), new THREE.Vector3(0, 0.03, 0.055), index % 3 === 0 ? 'accent' : 'dark')
    photos.push(photo)
  })
  return { wall, photos }
}

function createMoviePoster(materials) {
  const poster = new THREE.Group()
  poster.name = 'movie-poster-frame'
  poster.position.set(6.2, 4.05, 2.62)
  poster.rotation.y = -Math.PI / 2
  addBox(poster, materials, 'movie-poster-border', new THREE.Vector3(1.55, 2.25, 0.12), new THREE.Vector3(0, 0, 0), 'dark', { castShadow: true })
  addBox(poster, materials, 'movie-poster-paper', new THREE.Vector3(1.35, 2.03, 0.07), new THREE.Vector3(0, 0, 0.09), 'paper')
  addBox(poster, materials, 'movie-poster-title', new THREE.Vector3(0.82, 0.09, 0.035), new THREE.Vector3(0, 0.73, 0.145), 'dark')
  addBox(poster, materials, 'movie-poster-image', new THREE.Vector3(0.94, 0.84, 0.035), new THREE.Vector3(0, 0.02, 0.145), 'accent')
  addBox(poster, materials, 'movie-poster-credit-one', new THREE.Vector3(0.68, 0.055, 0.035), new THREE.Vector3(0, -0.68, 0.145), 'dark')
  addBox(poster, materials, 'movie-poster-credit-two', new THREE.Vector3(0.5, 0.045, 0.035), new THREE.Vector3(0, -0.82, 0.145), 'dark')
  return poster
}

function createBackWallArt(materials) {
  const art = new THREE.Group()
  art.name = 'back-wall-art'
  const frame = addBox(art, materials, 'small-wall-frame', new THREE.Vector3(1.15, 0.9, 0.08), new THREE.Vector3(-5.35, 3.85, -3.87), 'dark')
  frame.rotation.y = 0.02
  addBox(art, materials, 'small-wall-print', new THREE.Vector3(0.98, 0.73, 0.055), new THREE.Vector3(-5.35, 3.85, -3.81), 'paper')
  addBox(art, materials, 'small-wall-print-mark', new THREE.Vector3(0.48, 0.32, 0.03), new THREE.Vector3(-5.35, 3.87, -3.77), 'accent')
  return art
}

export function createDecor({ materials }) {
  const group = new THREE.Group()
  group.name = 'room-decor'
  group.add(createFloorBoards(materials), createBackWallArt(materials))

  const { wall: photoWall, photos } = createPhotoWall(materials)
  const moviePoster = createMoviePoster(materials)
  group.add(photoWall, moviePoster)

  const photoProxy = createProxy(photoWall, 'photoWall', new THREE.Vector3(1.7, 2.45, 0.38), new THREE.Vector3(0, 0, 0.15))
  const posterProxy = createProxy(moviePoster, 'moviePoster', new THREE.Vector3(1.78, 2.48, 0.38), new THREE.Vector3(0, 0, 0.17))

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
