const pose = (position, target, fov, duration) => Object.freeze({
  position: Object.freeze(position),
  target: Object.freeze(target),
  fov,
  duration,
})

export const CAMERA_PRESET_NAMES = Object.freeze(['overview', 'desk', 'right'])

export const CAMERA_PRESETS = Object.freeze({
  overview: pose([-5.05, 5.2, 7.55], [0.9, 2.78, -0.9], 48, 1.35),
  desk: pose([0, 3.25, 5.55], [0, 3.28, -4.55], 46, 1.1),
  right: pose([-0.75, 3.1, 0.4], [6.58, 3.1, 0.4], 52, 1.2),
})
