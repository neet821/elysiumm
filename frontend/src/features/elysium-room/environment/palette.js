const palette = (values) => Object.freeze(values)

export const environmentPalettes = Object.freeze({
  dawn: palette({
    sky: '#e7d8c9', horizon: '#eee4d9', ambient: '#d7b98f', accent: '#a9724d',
    wall: '#e8ded3', trim: '#f3ece4', frame: '#e9e2d9', floor: '#c7a17a', wood: '#b98555',
    dark: '#30302f', screen: '#1b1b1a', paper: '#eee7dd', plant: '#748064', metal: '#9b968f',
    record: '#191a19', glass: '#dddeda', ink: '#3b3834', softInk: '#777168', text: '#302e2b',
  }),
  day: palette({
    sky: '#f6f0e8', horizon: '#fbf6ee', ambient: '#dfbd91', accent: '#9d704c',
    wall: '#fffaf3', trim: '#fffdf8', frame: '#f8f1e7', floor: '#e2c096', wood: '#ca9a65',
    dark: '#2c2e2d', screen: '#181918', paper: '#eee8df', plant: '#6f7f65', metal: '#9a958c',
    record: '#171817', glass: '#dde3df', ink: '#383632', softInk: '#746e65', text: '#302f2c',
  }),
  dusk: palette({
    sky: '#756b68', horizon: '#c99a7d', ambient: '#b47b59', accent: '#bd7250',
    wall: '#b8a79a', trim: '#d4c5b8', frame: '#cfc1b4', floor: '#a27656', wood: '#9b6544',
    dark: '#292828', screen: '#131313', paper: '#d5c5b8', plant: '#59644f', metal: '#817873',
    record: '#151515', glass: '#8c8f8b', ink: '#292725', softInk: '#5d554f', text: '#f2eae2',
  }),
  night: palette({
    sky: '#171b24', horizon: '#2f3540', ambient: '#514b4c', accent: '#c08a63',
    wall: '#4b4b4d', trim: '#626164', frame: '#66676a', floor: '#5b4a3e', wood: '#704d36',
    dark: '#202122', screen: '#0c0d0e', paper: '#8d8580', plant: '#4b5c4b', metal: '#68686a',
    record: '#0e0f10', glass: '#3c4550', ink: '#171719', softInk: '#3d3d40', text: '#f1ece7',
  }),
})

export function createPageThemeVariables(active) {
  return {
    '--sky': active.sky,
    '--horizon': active.horizon,
    '--ambient': active.ambient,
    '--accent': active.accent,
    '--text': active.text,
    '--ink': active.ink,
    '--surface': active.trim,
  }
}
