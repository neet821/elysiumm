import { describe, expect, it } from 'vitest'
import { BoxGeometry, Texture } from 'three'
import { createBayWindow } from '../src/room/createBayWindow.js'
import { createRoom } from '../src/room/createRoom.js'
import { BAY_WINDOW } from '../src/room/layout.js'
import { createMaterialRegistry, createOutlinedMesh } from '../src/scene/primitives.js'
import { SCENERY_URLS, loadSceneryTexture, resolveSceneryUrl } from '../src/scene/textureLoader.js'

describe('material registry', () => {
  it('recolors every fill and edge material that has already been created', () => {
    const registry = createMaterialRegistry({
      shell: { fill: 'horizon', edge: 'ink' },
      trim: { fill: 'accent', edge: 'text' },
    })
    const shell = registry.get('shell')
    const trim = registry.get('trim')

    registry.applyPalette({
      horizon: '#112233',
      accent: '#aabbcc',
      ink: '#010203',
      text: '#f1f2f3',
    })

    expect(shell.fill.color.getHexString()).toBe('112233')
    expect(shell.edge.color.getHexString()).toBe('010203')
    expect(trim.fill.color.getHexString()).toBe('aabbcc')
    expect(trim.edge.color.getHexString()).toBe('f1f2f3')
  })

  it('keeps shadows off by default and enables them only when explicitly requested', () => {
    const registry = createMaterialRegistry()
    const defaultMesh = createOutlinedMesh(new BoxGeometry(1, 1, 1), 'shell', registry)
    const shadedMesh = createOutlinedMesh(
      new BoxGeometry(1, 1, 1),
      'shell',
      registry,
      { castShadow: true, receiveShadow: true },
    )

    expect(defaultMesh.userData.fillMesh.castShadow).toBe(false)
    expect(defaultMesh.userData.fillMesh.receiveShadow).toBe(false)
    expect(shadedMesh.userData.fillMesh.castShadow).toBe(true)
    expect(shadedMesh.userData.fillMesh.receiveShadow).toBe(true)
    registry.dispose()
  })
})

describe('scenery URL mapping', () => {
  it('resolves all four local views and safely falls back to nature', () => {
    expect(SCENERY_URLS).toEqual({
      nature: '/scenery/nature-window.webp',
      city: '/scenery/city.svg',
      cloudy: '/scenery/cloudy.svg',
      night: '/scenery/night.svg',
    })
    expect(resolveSceneryUrl('city')).toBe('/scenery/city.svg')
    expect(resolveSceneryUrl('missing-view')).toBe('/scenery/nature-window.webp')
    expect(resolveSceneryUrl()).toBe('/scenery/nature-window.webp')
  })

  it('records the fallback view after an unknown scenery is requested', async () => {
    const materials = createMaterialRegistry()
    const bayWindow = createBayWindow({
      materials,
      scenery: 'missing-view',
      textureLoader: { loadAsync: async () => new Texture() },
    })

    await bayWindow.ready

    expect(bayWindow.group.userData.scenery).toBe('nature')
    expect(bayWindow.group.userData.sceneryUrl).toBe('/scenery/nature-window.webp')
    bayWindow.dispose()
    materials.dispose()
  })

  it('returns the effective scenery name when a known view falls back after loading fails', async () => {
    const fallbackTexture = new Texture()
    const loader = {
      async loadAsync(url) {
        if (url === '/scenery/city.svg') throw new Error('city unavailable')
        if (url === '/scenery/nature-window.webp') return fallbackTexture
        throw new Error(`unexpected URL: ${url}`)
      },
    }

    const result = await loadSceneryTexture('city', loader)

    expect(result.scenery).toBe('nature')
    expect(result.texture).toBe(fallbackTexture)
  })

  it('records nature as the active view when a known scenery asset falls back', async () => {
    const materials = createMaterialRegistry()
    const bayWindow = createBayWindow({
      materials,
      scenery: 'city',
      textureLoader: {
        async loadAsync(url) {
          if (url === '/scenery/city.svg') throw new Error('city unavailable')
          return new Texture()
        },
      },
    })

    await bayWindow.ready

    expect(bayWindow.group.userData.scenery).toBe('nature')
    expect(bayWindow.group.userData.sceneryUrl).toBe('/scenery/nature-window.webp')
    bayWindow.dispose()
    materials.dispose()
  })
})

describe('bay window structure', () => {
  it('builds six divided front units and one perpendicular return on each side', () => {
    const materials = createMaterialRegistry()
    const bayWindow = createBayWindow({
      materials,
      textureLoader: { loadAsync: async () => new Texture() },
    })

    for (let index = 1; index <= 6; index += 1) {
      expect(bayWindow.group.getObjectByName(`bay-front-upper-glass-${index}`)).toBeTruthy()
      expect(bayWindow.group.getObjectByName(`bay-front-lower-glass-${index}`)).toBeTruthy()
      expect(bayWindow.group.getObjectByName(`bay-front-crossbar-${index}`)).toBeTruthy()
    }
    for (const [side, direction] of [['left', -1], ['right', 1]]) {
      const sideWindow = bayWindow.group.getObjectByName(`bay-${side}-side-window`)
      expect(sideWindow).toBeTruthy()
      expect(Math.abs(sideWindow.rotation.y)).toBeCloseTo(Math.PI / 2, 8)
      expect(sideWindow.position.x).toBeCloseTo(direction * BAY_WINDOW.frontWidth / 2, 8)
      expect(bayWindow.group.getObjectByName(`bay-${side}-side-window-upper-glass`)).toBeTruthy()
      expect(bayWindow.group.getObjectByName(`bay-${side}-side-window-lower-glass`)).toBeTruthy()
      expect(bayWindow.group.getObjectByName(`bay-${side}-side-window-crossbar`)).toBeTruthy()
      expect(bayWindow.group.getObjectByName(`${side}-side-outside-scenery`)).toBeTruthy()
    }

    bayWindow.dispose()
    materials.dispose()
  })
})

describe('room disposal', () => {
  it('disposes every geometry owned by meshes, scenery, proxies, and outline lines', async () => {
    const materials = createMaterialRegistry()
    const room = createRoom({
      materials,
      textureLoader: { loadAsync: async () => new Texture() },
    })
    await room.ready

    const geometries = new Set()
    const disposed = new Set()
    room.group.traverse((object) => {
      if (!object.geometry) return
      geometries.add(object.geometry)
      object.geometry.addEventListener('dispose', () => disposed.add(object.geometry))
    })

    room.dispose()

    expect(disposed.size).toBe(geometries.size)
    materials.dispose()
  })
})
