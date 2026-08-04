const pose = (position, target, fov, duration) => Object.freeze({
  position: Object.freeze(position),
  target: Object.freeze(target),
  fov,
  duration,
})

export const CAMERA_PRESET_NAMES = Object.freeze(['overview', 'desk', 'right'])

export const CAMERA_PRESETS = Object.freeze({
  overview: pose([-9.8, 6.6, 11.5], [0.4, 2.55, -0.65], 38, 1.35),
  desk: pose([-1.2, 2.9, 4.2], [-1.2, 2.75, -2.7], 42, 1.1),
  right: pose([0.5, 2.85, 0.05], [5.78, 2.85, 0.05], 52, 1.2),
})
