import { describe, expect, it } from 'vitest'
import { classifyLocalHour, createEnvironmentState } from '../src/environment/environmentState.js'
import { environmentPalettes } from '../src/environment/palette.js'

describe('classifyLocalHour', () => {
  it('assigns every transition hour to its intended environment mode', () => {
    expect(classifyLocalHour(5)).toBe('night')
    expect(classifyLocalHour(6)).toBe('dawn')
    expect(classifyLocalHour(9)).toBe('day')
    expect(classifyLocalHour(17)).toBe('dusk')
    expect(classifyLocalHour(20)).toBe('night')
  })
})

describe('createEnvironmentState', () => {
  it('uses the supplied clock in AUTO mode and keeps a manual override until AUTO is restored', () => {
    let currentHour = 8
    const environment = createEnvironmentState(() => new Date(2026, 7, 4, currentHour))

    expect(environment.getState()).toEqual({ mode: 'dawn', isAuto: true })

    environment.setMode('night')
    currentHour = 13
    expect(environment.getState()).toEqual({ mode: 'night', isAuto: false })

    environment.setMode('auto')
    expect(environment.getState()).toEqual({ mode: 'day', isAuto: true })
  })
})

describe('environmentPalettes', () => {
  it('provides a palette for every environment mode the state can select', () => {
    expect(Object.keys(environmentPalettes).sort()).toEqual(['dawn', 'day', 'dusk', 'night'])
  })
})
