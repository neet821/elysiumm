import * as THREE from 'three'

const DEFAULT_DEFINITIONS = Object.freeze({
  floor: Object.freeze({ fill: 'floor', edge: 'softInk' }),
  shell: Object.freeze({ fill: 'wall', edge: 'ink' }),
  trim: Object.freeze({ fill: 'trim', edge: 'softInk' }),
  frame: Object.freeze({ fill: 'frame', edge: 'ink' }),
  accent: Object.freeze({ fill: 'accent', edge: 'ink' }),
  glass: Object.freeze({ fill: 'glass', edge: 'softInk', transparent: true, opacity: 0.1 }),
  wood: Object.freeze({ fill: 'wood', edge: 'ink' }),
  dark: Object.freeze({ fill: 'dark', edge: 'ink' }),
  screen: Object.freeze({ fill: 'screen', edge: 'softInk' }),
  paper: Object.freeze({ fill: 'paper', edge: 'ink' }),
  plant: Object.freeze({ fill: 'plant', edge: 'ink' }),
  metal: Object.freeze({ fill: 'metal', edge: 'ink' }),
  record: Object.freeze({ fill: 'record', edge: 'softInk' }),
})

export function createMaterialRegistry(definitions = DEFAULT_DEFINITIONS) {
  const materials = new Map()
  let activePalette = null

  function applyPairPalette(pair) {
    if (!activePalette) return

    const definition = definitions[pair.key]
    const fillColor = activePalette[definition.fill] ?? activePalette.horizon ?? '#f2f0ea'
    const edgeColor = activePalette[definition.edge] ?? activePalette.ink ?? '#101010'
    pair.fill.color.set(fillColor)
    pair.edge.color.set(edgeColor)
  }

  return {
    get(key) {
      if (!definitions[key]) {
        throw new RangeError(`unknown material key: ${key}`)
      }

      if (!materials.has(key)) {
        const definition = definitions[key]
        const pair = {
          key,
          fill: new THREE.MeshStandardMaterial({
            color: '#f2f0ea',
            roughness: 0.86,
            metalness: 0.02,
            transparent: definition.transparent ?? false,
            opacity: definition.opacity ?? 1,
            side: definition.transparent ? THREE.DoubleSide : THREE.FrontSide,
          }),
          edge: new THREE.LineBasicMaterial({ color: '#101010', transparent: true, opacity: 0.92 }),
        }
        materials.set(key, pair)
        applyPairPalette(pair)
      }

      return materials.get(key)
    },

    applyPalette(palette) {
      activePalette = palette
      materials.forEach(applyPairPalette)
    },

    dispose() {
      materials.forEach(({ fill, edge }) => {
        fill.dispose()
        edge.dispose()
      })
      materials.clear()
    },
  }
}

export const materialRegistry = createMaterialRegistry()

export function createOutlinedMesh(geometry, materialKey, registry = materialRegistry, shadows = {}) {
  const { fill, edge } = registry.get(materialKey)
  const group = new THREE.Group()
  const mesh = new THREE.Mesh(geometry, fill)
  const outline = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), edge)

  mesh.castShadow = shadows.castShadow ?? false
  mesh.receiveShadow = shadows.receiveShadow ?? false
  outline.renderOrder = 2
  group.add(mesh, outline)
  group.userData.fillMesh = mesh
  group.userData.outline = outline
  return group
}

export function createOutlinedBox(size, materialKey, registry = materialRegistry, shadows = {}) {
  return createOutlinedMesh(new THREE.BoxGeometry(size.x, size.y, size.z), materialKey, registry, shadows)
}

export function disposeObjectGeometries(root) {
  const geometries = new Set()
  root.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry)
  })
  geometries.forEach((geometry) => geometry.dispose())
}
