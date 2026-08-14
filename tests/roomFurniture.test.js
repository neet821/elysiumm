import { describe, expect, it } from 'vitest'
import { Texture } from 'three'
import { createRoom } from '../src/room/createRoom.js'
import { createMaterialRegistry } from '../src/scene/primitives.js'

const furnitureIds = [
  'monitor',
  'lamp',
  'recordPlayer',
  'recordRack',
  'photoWall',
  'books',
  'moviePoster',
]

function makeRoom() {
  const materials = createMaterialRegistry()
  const room = createRoom({
    materials,
    textureLoader: { loadAsync: async () => new Texture() },
  })
  return { materials, room }
}

describe('room furniture registry', () => {
  it('exposes every furnished interaction as a visible object, dedicated proxy, and label', () => {
    const { materials, room } = makeRoom()

    expect(Object.keys(room.registry).sort()).toEqual([...furnitureIds, 'window'].sort())
    for (const id of furnitureIds) {
      const entry = room.registry[id]
      expect(entry.visual, `${id} visual`).toBeTruthy()
      expect(entry.proxy, `${id} proxy`).toBeTruthy()
      expect(entry.proxy.userData.interactionId).toBe(id)
      expect(entry.proxy.material.transparent).toBe(true)
      expect(entry.proxy.material.opacity).toBe(0)
      expect(entry.label, `${id} label`).toEqual(expect.any(String))
      expect(entry.label.length).toBeGreaterThan(0)
    }

    room.dispose()
    materials.dispose()
  })

  it('keeps the record and lamp parts needed by later animation controllers', () => {
    const { materials, room } = makeRoom()

    expect(room.registry.recordPlayer.record.name).toBe('spinning-record')
    expect(room.registry.recordPlayer.tonearm.name).toBe('record-tonearm')
    expect(room.registry.lamp.shade.name).toBe('desk-lamp-shade')
    expect(room.registry.lamp.bulb.name).toBe('desk-lamp-bulb')

    room.dispose()
    materials.dispose()
  })
})

describe('furnished room structure', () => {
  it('builds recognizable desk, record, and personal-detail zones', () => {
    const { materials, room } = makeRoom()

    expect(room.deskZone.group.name).toBe('desk-zone')
    expect(room.recordZone.group.name).toBe('record-zone')
    expect(room.decor.group.name).toBe('room-decor')

    const requiredParts = [
      'desk-top',
      'keyboard',
      'record-cabinet',
      'cabinet-left-door',
      'cabinet-open-shelf',
      'cabinet-right-door',
      'album-rack',
      'wall-shelves',
      'shelf-album-display',
      'photo-grid',
      'photo-grid-wires',
      'movie-poster-frame',
      'floor-boards',
    ]
    for (const name of requiredParts) {
      expect(room.group.getObjectByName(name), name).toBeTruthy()
    }
    expect(room.group.getObjectByName('desk-chair')).toBeUndefined()
    expect(room.group.getObjectByName('desk-plant')).toBeUndefined()

    room.dispose()
    materials.dispose()
  })

  it('casts shadows only from a restrained set of large furniture silhouettes', () => {
    const { materials, room } = makeRoom()
    const shadowCasters = []
    room.group.traverse((object) => {
      if (object.isMesh && object.castShadow) shadowCasters.push(object.parent.name)
    })

    expect(shadowCasters).toEqual(expect.arrayContaining([
      'desk-top',
      'monitor-screen',
      'desk-lamp-shade',
      'cabinet-top',
      'record-player-plinth',
      'spinning-record',
      'album-rack-base',
      'wall-shelf-1',
      'movie-poster-border',
    ]))
    expect(shadowCasters).not.toEqual(expect.arrayContaining([
      'desk-lamp-stem',
      'record-label',
      'tonearm-arm',
      'album-1',
      'compact-disc-1',
      'shelf-plant-pot',
      'photo-1',
    ]))
    expect(shadowCasters.length).toBeLessThanOrEqual(56)

    room.dispose()
    materials.dispose()
  })
})
