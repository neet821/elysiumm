import * as THREE from 'three'
import { createMaterialRegistry } from './primitives.js'

export function createScene(canvas) {
  if (!canvas) throw new TypeError('createScene requires a canvas')

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100)
  camera.position.set(10.5, 7.5, 14)
  camera.lookAt(0, 2.2, -1.2)

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false })
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio ?? 1, 2))

  const hemisphere = new THREE.HemisphereLight('#dbeeff', '#d6b58d', 2.1)
  const sun = new THREE.DirectionalLight('#fff2d1', 2.8)
  sun.position.set(-4, 9, 7)
  sun.castShadow = true
  sun.shadow.mapSize.set(1024, 1024)
  sun.shadow.camera.left = -10
  sun.shadow.camera.right = 10
  sun.shadow.camera.top = 10
  sun.shadow.camera.bottom = -10
  scene.add(hemisphere, sun)

  const materials = createMaterialRegistry()
  let frameId = null

  function resize() {
    const width = Math.max(1, canvas.clientWidth || globalThis.innerWidth || 1)
    const height = Math.max(1, canvas.clientHeight || globalThis.innerHeight || 1)
    const pixelRatio = renderer.getPixelRatio()
    const needsResize = canvas.width !== Math.round(width * pixelRatio)
      || canvas.height !== Math.round(height * pixelRatio)

    if (needsResize) renderer.setSize(width, height, false)
    camera.aspect = width / height
    camera.updateProjectionMatrix()
  }

  function render() {
    resize()
    renderer.render(scene, camera)
  }

  function tick() {
    render()
    frameId = globalThis.requestAnimationFrame?.(tick) ?? null
  }

  return {
    scene,
    camera,
    renderer,
    materials,
    lights: { hemisphere, sun },
    render,
    resize,
    start() {
      if (frameId === null) tick()
    },
    stop() {
      if (frameId !== null) globalThis.cancelAnimationFrame?.(frameId)
      frameId = null
    },
    dispose() {
      if (frameId !== null) globalThis.cancelAnimationFrame?.(frameId)
      frameId = null
      materials.dispose()
      renderer.dispose()
    },
  }
}
