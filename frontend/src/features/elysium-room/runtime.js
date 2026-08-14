import { createScene } from './scene/createScene.js'
import { createRoom } from './room/createRoom.js'
import { CameraRig } from './camera/CameraRig.js'
import { RoomAudio } from './audio/RoomAudio.js'
import { createEnvironmentState } from './environment/environmentState.js'
import { EnvironmentController } from './environment/EnvironmentController.js'
import { createInteractionConfig } from './interactions/interactionConfig.js'
import { InteractionManager } from './interactions/InteractionManager.js'
import { createHud } from './ui/createHud.js'

const HOVER_LABELS = Object.freeze({
  monitor: '进入归档',
  photoWall: '进入照片墙',
  books: '进入书籍',
  moviePoster: '进入电影',
  lamp: '台灯开关',
  recordPlayer: '播放唱片',
  recordRack: '切换唱片',
  window: '切换窗外景色',
})

const ROUTE_PATHS = Object.freeze({
  projects: '/archive',
  gallery: '/archive?type=photo',
  reading: '/books',
  movies: '/archive',
})

export async function mountElysiumRoom(root, { onNavigate, onOpenLauncher } = {}) {
  root.innerHTML = `
    <div class="room-stage"></div>
    <div class="hud-mount"></div>
  `

  const stage = root.querySelector('.room-stage')
  const canvas = document.createElement('canvas')
  canvas.id = 'room-canvas'
  canvas.setAttribute('aria-label', 'Elysium 三维房间')
  stage.appendChild(canvas)

  let runtime
  let room
  let audio
  let environment
  let rig
  let interactions
  let hud
  let frameId = null
  let disposed = false
  let pendingRoute = null
  let pendingLauncher = false
  let unlockAfterClose = false

  try {
    runtime = createScene(canvas)
    room = createRoom({ scene: runtime.scene, materials: runtime.materials, scenery: 'nature' })
    await room.ready
    if (disposed) {
      room.dispose()
      runtime.dispose()
      return () => {}
    }

    rig = new CameraRig(runtime.camera, { initialPreset: 'overview' })
    audio = new RoomAudio()
    environment = new EnvironmentController({
      state: createEnvironmentState(),
      scene: runtime.scene,
      materials: runtime.materials,
      lights: runtime.lights,
      registry: room.registry,
      audio,
    })
    hud = createHud(root.querySelector('.hud-mount'), {
      onCamera(name) {
        if (!rig.isTransitioning) {
          hud.setCamera(name)
          rig.setPreset(name)
        }
      },
      onTimeMode(mode) {
        environment.setTimeMode(mode)
      },
    })
    environment.subscribe((snapshot) => hud.render(snapshot))

    interactions = new InteractionManager({
      camera: runtime.camera,
      canvas,
      onHover(id, label) {
        hud.setHint(id ? `点击：${HOVER_LABELS[id] ?? label}` : '')
      },
    })
    Object.entries(room.registry).forEach(([id, entry]) => interactions.register({ id, ...entry }))

    const interactionConfig = createInteractionConfig({ environment })
    interactions.setActionHandler((id) => {
      if (rig.isTransitioning || interactions.locked) return
      if (id === 'monitor') {
        interactions.setLocked(true)
        rig.focus(interactionConfig.focusPoseFor(id))
        pendingLauncher = true
        return
      }
      const route = interactionConfig.getRouteFor(id)
      if (route) {
        interactions.setLocked(true)
        rig.focus(interactionConfig.focusPoseFor(id))
        pendingRoute = route
        return
      }
      interactionConfig.activateInRoom(id)
    })

    const onPointerMove = (event) => interactions.updatePointer(event)
    const onPointerDown = (event) => {
      audio.unlock()
      interactions.activate(event)
    }
    const onPointerLeave = () => interactions.clearHover()
    const unlockAudio = () => audio.unlock()
    canvas.addEventListener('pointermove', onPointerMove)
    canvas.addEventListener('pointerdown', onPointerDown)
    canvas.addEventListener('pointerleave', onPointerLeave)
    globalThis.addEventListener('pointerdown', unlockAudio, { once: true })

    let last = performance.now()
    const frame = () => {
      if (disposed) return
      const now = performance.now()
      const delta = Math.min(0.05, (now - last) / 1000)
      last = now
      environment.update(delta)
      rig.update(delta, interactions.pointer)
      const activePreset = rig.getActivePreset()
      if (activePreset && !rig.isTransitioning) hud.setCamera(activePreset)
      if (pendingRoute && !rig.isTransitioning) {
        const route = pendingRoute
        pendingRoute = null
        onNavigate?.(ROUTE_PATHS[route] ?? '/archive')
      }
      if (pendingLauncher && !rig.isTransitioning) {
        pendingLauncher = false
        onOpenLauncher?.(closeLauncher)
      }
      if (unlockAfterClose && !rig.isTransitioning) {
        unlockAfterClose = false
        interactions.setLocked(false)
      }
      runtime.render()
      frameId = globalThis.requestAnimationFrame(frame)
    }
    frameId = globalThis.requestAnimationFrame(frame)

    function closeLauncher() {
      rig.restore()
      unlockAfterClose = true
    }

    globalThis.__ROOM_APP__ = { rig, environment, interactions, audio, registry: room.registry, runtime }

    const cleanup = () => {
      disposed = true
      if (frameId !== null) globalThis.cancelAnimationFrame(frameId)
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('pointerdown', onPointerDown)
      canvas.removeEventListener('pointerleave', onPointerLeave)
      globalThis.removeEventListener('pointerdown', unlockAudio)
      interactions?.dispose?.()
      environment?.dispose?.()
      room?.dispose?.()
      audio?.dispose?.()
      runtime?.dispose?.()
      if (globalThis.__ROOM_APP__?.runtime === runtime) delete globalThis.__ROOM_APP__
      root.replaceChildren()
    }

    return cleanup
  } catch (error) {
    disposed = true
    room?.dispose?.()
    audio?.dispose?.()
    environment?.dispose?.()
    runtime?.dispose?.()
    throw error
  }
}
