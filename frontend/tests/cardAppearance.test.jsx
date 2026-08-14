import { describe, expect, it } from 'vitest'

import { createCardAppearance } from '../src/components/home/cardAppearance.js'

describe('stable homepage card appearance', () => {
  it('returns identical values for the same content key', () => {
    expect(createCardAppearance('post-42', 'note')).toEqual(createCardAppearance('post-42', 'note'))
  })

  it('covers the approved white-paper textures across representative keys', () => {
    const variants = new Set(Array.from({ length: 200 }, (_, index) => (
      createCardAppearance(`post-${index}`, 'note').paperVariant
    )))

    expect(variants).toEqual(new Set(['plain', 'ruled', 'dotted', 'grid', 'fiber']))
  })

  it('does not bind a paper texture to one tape color', () => {
    const appearances = Array.from({ length: 300 }, (_, index) => (
      createCardAppearance(`post-${index}`, 'note')
    ))
    const ruledTapeColors = new Set(
      appearances
        .filter((appearance) => appearance.paperVariant === 'ruled')
        .map((appearance) => appearance.style['--tape-1-color']),
    )

    expect(ruledTapeColors.size).toBeGreaterThan(2)
  })

  it('keeps angle, scale, and tape placement inside safe bounds', () => {
    for (let index = 0; index < 300; index += 1) {
      const appearance = createCardAppearance(`photo-${index}`, 'photo')
      expect(Number.parseFloat(appearance.style['--card-rotate'])).toBeGreaterThanOrEqual(-2.4)
      expect(Number.parseFloat(appearance.style['--card-rotate'])).toBeLessThanOrEqual(2.4)
      expect(Number.parseFloat(appearance.style['--tape-1-left'])).toBeGreaterThanOrEqual(18)
      expect(Number.parseFloat(appearance.style['--tape-1-left'])).toBeLessThanOrEqual(82)
      expect(Number.parseFloat(appearance.style['--card-scale'])).toBeGreaterThanOrEqual(0.97)
      expect(Number.parseFloat(appearance.style['--card-scale'])).toBeLessThanOrEqual(1.02)
    }
  })
})
