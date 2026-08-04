import * as THREE from 'three'
import { CAMERA_PRESETS } from './cameraPresets.js'
import { cubicEaseInOut } from './easing.js'

const MIN_TRANSITION_DURATION = 0.8
const MAX_TRANSITION_DURATION = 2
const PARALLAX_POSITION_AMOUNT = 0.055
const PARALLAX_TARGET_AMOUNT = 0.14
const PARALLAX_RESPONSE = 9

function isFiniteTuple(value) {
  return Array.isArray(value) && value.length === 3 && value.every(Number.isFinite)
}

function validatePose(pose, label = 'camera pose') {
  if (!pose || !isFiniteTuple(pose.position) || !isFiniteTuple(pose.target)) {
    throw new TypeError(`${label} requires finite position and target tuples`)
  }
  if (!Number.isFinite(pose.fov) || pose.fov <= 0 || pose.fov >= 180) {
    throw new TypeError(`${label} requires a finite fov between 0 and 180`)
  }
  if (!Number.isFinite(pose.duration)) {
    throw new TypeError(`${label} requires a finite duration`)
  }
  return pose
}

function copyPose(pose) {
  return {
    position: new THREE.Vector3(...pose.position),
    target: new THREE.Vector3(...pose.target),
    fov: pose.fov,
    duration: pose.duration,
  }
}

function serializablePose(pose) {
  return {
    position: pose.position.toArray(),
    target: pose.target.toArray(),
    fov: pose.fov,
    duration: pose.duration,
  }
}

function clampDuration(duration) {
  return THREE.MathUtils.clamp(duration, MIN_TRANSITION_DURATION, MAX_TRANSITION_DURATION)
}

function validateDuration(duration) {
  if (!Number.isFinite(duration)) {
    throw new TypeError('camera transition requires a finite duration')
  }
}

function finitePointerComponent(value) {
  return THREE.MathUtils.clamp(Number.isFinite(value) ? value : 0, -1, 1)
}

export class CameraRig {
  constructor(camera, options = {}) {
    if (!camera?.isPerspectiveCamera) {
      throw new TypeError('CameraRig requires a PerspectiveCamera')
    }

    this.camera = camera
    this.isTransitioning = false
    this._transition = null
    this._activePreset = null
    this._restorePose = null
    this._isFocused = false
    this._pointer = new THREE.Vector2()
    this._right = new THREE.Vector3()
    this._up = new THREE.Vector3()
    this._direction = new THREE.Vector3()
    this._renderPosition = new THREE.Vector3()
    this._renderTarget = new THREE.Vector3()

    const initialPreset = options.initialPreset ?? 'overview'
    const initialSource = options.initialPose ?? CAMERA_PRESETS[initialPreset]
    validatePose(initialSource, options.initialPose ? 'initial pose' : `camera preset "${initialPreset}"`)
    const initial = copyPose(initialSource)
    this._basePosition = initial.position
    this._baseTarget = initial.target
    this._baseFov = initial.fov
    if (!options.initialPose) this._activePreset = initialPreset
    this._applyCamera(new THREE.Vector2())
  }

  setPreset(name, options = {}) {
    const preset = CAMERA_PRESETS[name]
    if (!preset) throw new RangeError(`Unknown camera preset: ${name}`)
    validateDuration(options.duration ?? preset.duration)

    this._activePreset = name
    this._isFocused = false
    this._restorePose = null
    this._startTransition(preset, options)
    return this
  }

  focus(targetPose, options = {}) {
    validatePose(targetPose, 'focus pose')
    validateDuration(options.duration ?? targetPose.duration)
    if (!this._isFocused) {
      const returnPose = this._activePreset ? CAMERA_PRESETS[this._activePreset] : {
        position: this._basePosition.toArray(),
        target: this._baseTarget.toArray(),
        fov: this._baseFov,
        duration: targetPose.duration,
      }
      this._restorePose = copyPose(returnPose)
    }
    this._isFocused = true
    this._startTransition(targetPose, options)
    return this
  }

  restore(options = {}) {
    if (!this._restorePose) return this
    const targetPose = serializablePose(this._restorePose)
    validateDuration(options.duration ?? targetPose.duration)
    this._isFocused = false
    this._restorePose = null
    this._startTransition(targetPose, options)
    return this
  }

  getActivePreset() {
    return this._activePreset
  }

  update(delta, pointer = {}) {
    const elapsed = Number.isFinite(delta) && delta > 0 ? delta : 0

    if (this._transition) {
      this._transition.elapsed = Math.min(
        this._transition.duration,
        this._transition.elapsed + elapsed,
      )
      const progress = this._transition.elapsed / this._transition.duration
      const eased = cubicEaseInOut(progress)

      this._basePosition.lerpVectors(
        this._transition.start.position,
        this._transition.end.position,
        eased,
      )
      this._baseTarget.lerpVectors(
        this._transition.start.target,
        this._transition.end.target,
        eased,
      )
      this._baseFov = THREE.MathUtils.lerp(
        this._transition.start.fov,
        this._transition.end.fov,
        eased,
      )

      if (progress >= 1) {
        this._basePosition.copy(this._transition.end.position)
        this._baseTarget.copy(this._transition.end.target)
        this._baseFov = this._transition.end.fov
        this._transition = null
        this.isTransitioning = false
      }
    }

    const desiredX = finitePointerComponent(pointer?.x)
    const desiredY = finitePointerComponent(pointer?.y)
    const response = elapsed > 0 ? 1 - Math.exp(-PARALLAX_RESPONSE * elapsed) : 0
    this._pointer.x = THREE.MathUtils.lerp(this._pointer.x, desiredX, response)
    this._pointer.y = THREE.MathUtils.lerp(this._pointer.y, desiredY, response)
    this._applyCamera(this._pointer)
    return this.isTransitioning
  }

  _startTransition(sourcePose, options) {
    validatePose(sourcePose)
    const end = copyPose(sourcePose)
    const requestedDuration = options.duration ?? sourcePose.duration
    validateDuration(requestedDuration)

    this._transition = {
      start: {
        position: this._basePosition.clone(),
        target: this._baseTarget.clone(),
        fov: this._baseFov,
      },
      end,
      duration: clampDuration(requestedDuration),
      elapsed: 0,
    }
    this.isTransitioning = true
  }

  _applyCamera(pointer) {
    this._direction.subVectors(this._baseTarget, this._basePosition).normalize()
    this._right.crossVectors(this._direction, this.camera.up).normalize()
    this._up.crossVectors(this._right, this._direction).normalize()

    this._renderPosition.copy(this._basePosition)
      .addScaledVector(this._right, pointer.x * PARALLAX_POSITION_AMOUNT)
      .addScaledVector(this._up, pointer.y * PARALLAX_POSITION_AMOUNT)
    this._renderTarget.copy(this._baseTarget)
      .addScaledVector(this._right, pointer.x * PARALLAX_TARGET_AMOUNT)
      .addScaledVector(this._up, pointer.y * PARALLAX_TARGET_AMOUNT)

    this.camera.position.copy(this._renderPosition)
    this.camera.fov = this._baseFov
    this.camera.updateProjectionMatrix()
    this.camera.lookAt(this._renderTarget)
  }
}
