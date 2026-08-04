import { describe, expect, it } from 'vitest'
import { classifyLocalHour, createEnvironmentState } from '../src/environment/environmentState.js'
import { createPageThemeVariables, environmentPalettes } from '../src/environment/palette.js'

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

  it('maps every page theme color to a CSS variable from the selected palette', () => {
    const palette = {
      sky: '#111111',
      horizon: '#222222',
      ambient: '#333333',
      accent: '#444444',
      text: '#555555',
      ink: '#666666',
    }

    expect(createPageThemeVariables(palette)).toEqual({
      '--sky': '#111111',
      '--horizon': '#222222',
      '--ambient': '#333333',
      '--accent': '#444444',
      '--text': '#555555',
      '--ink': '#666666',
    })
  })
})
