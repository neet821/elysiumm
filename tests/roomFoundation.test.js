import { describe, expect, it } from 'vitest'
import { Texture } from 'three'
import { createBayWindow } from '../src/room/createBayWindow.js'
import { createMaterialRegistry } from '../src/scene/primitives.js'
import { SCENERY_URLS, resolveSceneryUrl } from '../src/scene/textureLoader.js'

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
})

describe('scenery URL mapping', () => {
  it('resolves all four local views and safely falls back to nature', () => {
    expect(SCENERY_URLS).toEqual({
      nature: '/scenery/nature.svg',
      city: '/scenery/city.svg',
      cloudy: '/scenery/cloudy.svg',
      night: '/scenery/night.svg',
    })
    expect(resolveSceneryUrl('city')).toBe('/scenery/city.svg')
    expect(resolveSceneryUrl('missing-view')).toBe('/scenery/nature.svg')
    expect(resolveSceneryUrl()).toBe('/scenery/nature.svg')
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
    expect(bayWindow.group.userData.sceneryUrl).toBe('/scenery/nature.svg')
    bayWindow.dispose()
    materials.dispose()
  })
})
