import { describe, expect, it } from 'vitest'
import * as THREE from 'three'
import { CAMERA_PRESETS, CAMERA_PRESET_NAMES } from '../src/camera/cameraPresets.js'
import { CameraRig } from '../src/camera/CameraRig.js'
import { cubicEaseInOut } from '../src/camera/easing.js'

const finiteTuple = (value) => (
  Array.isArray(value)
  && value.length === 3
  && value.every(Number.isFinite)
)

function expectCameraLooksAt(camera, target, precision = 8) {
  const actual = new THREE.Vector3()
  camera.getWorldDirection(actual)
  const expected = new THREE.Vector3(...target).sub(camera.position).normalize()
  expect(actual.x).toBeCloseTo(expected.x, precision)
  expect(actual.y).toBeCloseTo(expected.y, precision)
  expect(actual.z).toBeCloseTo(expected.z, precision)
}

describe('camera pose data', () => {
  it('provides exactly three finite fixed-view presets with safe transition durations', () => {
    expect(CAMERA_PRESET_NAMES).toEqual(['overview', 'desk', 'right'])

    for (const name of CAMERA_PRESET_NAMES) {
      const pose = CAMERA_PRESETS[name]
      expect(finiteTuple(pose.position), `${name} position`).toBe(true)
      expect(finiteTuple(pose.target), `${name} target`).toBe(true)
      expect(Number.isFinite(pose.fov), `${name} fov`).toBe(true)
      expect(pose.duration, `${name} duration`).toBeGreaterThanOrEqual(0.8)
      expect(pose.duration, `${name} duration`).toBeLessThanOrEqual(2)
    }
  })

  it('rejects a focus pose containing a non-finite position, target, fov, or duration', () => {
    const camera = new THREE.PerspectiveCamera(40, 16 / 9, 0.1, 100)
    const rig = new CameraRig(camera)
    const valid = { position: [1, 2, 3], target: [0, 1, 0], fov: 36, duration: 1 }

    expect(() => rig.focus({ ...valid, position: [1, Number.NaN, 3] })).toThrow(TypeError)
    expect(() => rig.focus({ ...valid, target: [0, 1, Number.POSITIVE_INFINITY] })).toThrow(TypeError)
    expect(() => rig.focus({ ...valid, fov: Number.NaN })).toThrow(TypeError)
    expect(() => rig.focus({ ...valid, duration: Number.NaN })).toThrow(TypeError)
  })
})

describe('camera easing', () => {
  it('has exact endpoints and clamps values outside the transition interval', () => {
    expect(cubicEaseInOut(0)).toBe(0)
    expect(cubicEaseInOut(1)).toBe(1)
    expect(cubicEaseInOut(-2)).toBe(0)
    expect(cubicEaseInOut(3)).toBe(1)
    expect(cubicEaseInOut(0.25)).toBeCloseTo(0.0625, 12)
    expect(cubicEaseInOut(0.75)).toBeCloseTo(0.9375, 12)
  })
})

describe('CameraRig transitions', () => {
  it('interpolates position and look target without changing direction at transition start', () => {
    const camera = new THREE.PerspectiveCamera(40, 16 / 9, 0.1, 100)
    const rig = new CameraRig(camera, {
      initialPose: { position: [0, 2, 8], target: [0, 2, 0], fov: 40, duration: 1 },
    })
    const targetPose = { position: [4, 4, 4], target: [2, 1, -2], fov: 50, duration: 1 }

    rig.focus(targetPose)
    expect(camera.position.toArray()).toEqual([0, 2, 8])
    expectCameraLooksAt(camera, [0, 2, 0])

    rig.update(0.5, { x: 0, y: 0 })
    expect(camera.position.toArray()).toEqual([2, 3, 6])
    expect(camera.fov).toBe(45)
    expectCameraLooksAt(camera, [1, 1.5, -1])
  })

  it('clamps transition duration to 0.8–2 seconds and finishes on the exact pose', () => {
    const camera = new THREE.PerspectiveCamera(40, 16 / 10, 0.1, 100)
    const rig = new CameraRig(camera)
    const shortPose = { position: [2, 3, 5], target: [1, 2, -1], fov: 44, duration: 0.1 }

    rig.focus(shortPose)
    rig.update(0.79, { x: 0, y: 0 })
    expect(rig.isTransitioning).toBe(true)
    rig.update(0.01, { x: 0, y: 0 })
    expect(rig.isTransitioning).toBe(false)
    expect(camera.position.toArray()).toEqual([2, 3, 5])
    expect(camera.fov).toBe(44)
    expectCameraLooksAt(camera, [1, 2, -1])

    rig.focus({ position: [-2, 4, 6], target: [0, 3, 0], fov: 37, duration: 4 })
    rig.update(1.99, { x: 0, y: 0 })
    expect(rig.isTransitioning).toBe(true)
    rig.update(0.01, { x: 0, y: 0 })
    expect(rig.isTransitioning).toBe(false)
  })

  it('restores the fixed view that was active before a temporary focus pose', () => {
    const camera = new THREE.PerspectiveCamera(40, 16 / 9, 0.1, 100)
    const rig = new CameraRig(camera, { initialPreset: 'desk' })

    rig.focus({ position: [1, 3, 3], target: [0, 2, -2], fov: 34, duration: 0.8 })
    rig.update(0.8, { x: 0, y: 0 })
    rig.restore({ duration: 0.8 })
    rig.update(0.8, { x: 0, y: 0 })

    expect(camera.position.toArray()).toEqual(CAMERA_PRESETS.desk.position)
    expect(camera.fov).toBe(CAMERA_PRESETS.desk.fov)
    expectCameraLooksAt(camera, CAMERA_PRESETS.desk.target)
  })
})

describe('CameraRig pointer parallax', () => {
  it('clamps extreme pointer input to the same subtle offset as the normalized edge', () => {
    const edgeCamera = new THREE.PerspectiveCamera(40, 16 / 9, 0.1, 100)
    const extremeCamera = new THREE.PerspectiveCamera(40, 16 / 9, 0.1, 100)
    const edgeRig = new CameraRig(edgeCamera, { initialPreset: 'overview' })
    const extremeRig = new CameraRig(extremeCamera, { initialPreset: 'overview' })
    const baseDirection = new THREE.Vector3(...CAMERA_PRESETS.overview.target)
      .sub(new THREE.Vector3(...CAMERA_PRESETS.overview.position))
      .normalize()

    edgeRig.update(1 / 60, { x: 1, y: -1 })
    extremeRig.update(1 / 60, { x: 100, y: -100 })

    const edgeDirection = new THREE.Vector3()
    const extremeDirection = new THREE.Vector3()
    edgeCamera.getWorldDirection(edgeDirection)
    extremeCamera.getWorldDirection(extremeDirection)
    expect(extremeDirection.toArray()).toEqual(edgeDirection.toArray())
    expect(THREE.MathUtils.radToDeg(baseDirection.angleTo(edgeDirection))).toBeLessThanOrEqual(2.5)
  })
})
