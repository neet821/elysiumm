export const environmentPalettes = Object.freeze({
  dawn: Object.freeze({
    sky: '#f5b99a',
    horizon: '#f8d7b5',
    ambient: '#ffd6a4',
    accent: '#ee8a5d',
    text: '#f6f7fb',
    ink: '#101010',
  }),
  day: Object.freeze({
    sky: '#87bfe6',
    horizon: '#d7edf8',
    ambient: '#fff1c9',
    accent: '#4f92c4',
    text: '#f6f7fb',
    ink: '#101010',
  }),
  dusk: Object.freeze({
    sky: '#7566a6',
    horizon: '#e49a89',
    ambient: '#e8b07b',
    accent: '#d4675a',
    text: '#f6f7fb',
    ink: '#101010',
  }),
  night: Object.freeze({
    sky: '#10182f',
    horizon: '#27365e',
    ambient: '#798cc0',
    accent: '#b7c7ff',
    text: '#f6f7fb',
    ink: '#101010',
  }),
})

export function createPageThemeVariables(palette) {
  return {
    '--sky': palette.sky,
    '--horizon': palette.horizon,
    '--ambient': palette.ambient,
    '--accent': palette.accent,
    '--text': palette.text,
    '--ink': palette.ink,
  }
}
