import { describe, expect, it } from 'vitest'

import { buildRoomShareUrl, normalizeSearchQuery } from '../src/pages/roomShareUtils.js'

describe('room share and search helpers', () => {
  it('builds a complete share URL from the current room route', () => {
    expect(buildRoomShareUrl({ origin: 'https://elysiumm.top', pathname: '/rooms/watch/42', search: '?source=room' }))
      .toBe('https://elysiumm.top/rooms/watch/42?source=room')
  })

  it('keeps spaces between search terms while trimming only the edges', () => {
    expect(normalizeSearchQuery('  blue   album  ')).toBe('blue   album')
  })
})
