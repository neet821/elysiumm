import './styles.css'
import { createRoom } from './room/createRoom.js'
import { createScene } from './scene/createScene.js'
import { CameraRig } from './camera/CameraRig.js'
import { RoomAudio } from './audio/RoomAudio.js'
import { createEnvironmentState } from './environment/environmentState.js'
import { EnvironmentController } from './environment/EnvironmentController.js'
import { createInteractionConfig } from './interactions/interactionConfig.js'
import { InteractionManager } from './interactions/InteractionManager.js'
import { routeFromHash } from './routes/routeConfig.js'
import { createHud } from './ui/createHud.js'
import { RouteOverlay } from './ui/RouteOverlay.js'

const HOVER_LABELS = Object.freeze({
  monitor: '进入 Projects',
  photoWall: '进入 Gallery',
  books: '进入 Reading',
  moviePoster: '进入 Movies',
  lamp: '台灯开关',
  recordPlayer: '播放唱片',
  recordRack: '切换唱片',
  window: '切换窗外景色',
})

async function boot() {
  const app = document.querySelector('#app')
  app.innerHTML = `
    <div class="room-stage"></div>
    <div class="hud-mount"></div>
    <div class="route-mount"></div>
  `

  const stage = app.querySelector('.room-stage')
  const canvas = document.createElement('canvas')
  canvas.id = 'room-canvas'
  stage.appendChild(canvas)

  const runtime = createScene(canvas)
  const room = createRoom({
    scene: runtime.scene,
    materials: runtime.materials,
    scenery: 'nature',
  })
  await room.ready

  const rig = new CameraRig(runtime.camera, { initialPreset: 'overview' })
  const audio = new RoomAudio()
  const environment = new EnvironmentController({
    state: createEnvironmentState(),
    scene: runtime.scene,
    materials: runtime.materials,
    lights: runtime.lights,
    registry: room.registry,
    audio,
  })

  const hud = createHud(app.querySelector('.hud-mount'), {
    onCamera(name) {
      if (overlay.isOpen()) return
      hud.setCamera(name)
      rig.setPreset(name)
    },
    onTimeMode(mode) {
      environment.setTimeMode(mode)
    },
  })
  environment.subscribe((snapshot) => hud.render(snapshot))

  const overlay = new RouteOverlay(app.querySelector('.route-mount'), {
    onBack() {
      if (globalThis.location.hash) {
        globalThis.history.back()
      } else {
        overlay.close()
      }
    },
  })

  const interactions = new InteractionManager({
    camera: runtime.camera,
    canvas,
    onHover(id, label) {
      hud.setHint(id ? `点击：${HOVER_LABELS[id] ?? label}` : '')
    },
  })
  Object.entries(room.registry).forEach(([id, entry]) => {
    interactions.register({ id, ...entry })
  })

  const interactionConfig = createInteractionConfig({ environment })
  interactions.setActionHandler((id) => {
    if (overlay.isOpen() || rig.isTransitioning || interactions.locked) return
    const route = interactionConfig.getRouteFor(id)
    if (route) {
      interactions.setLocked(true)
      rig.focus(interactionConfig.focusPoseFor(id))
      pendingRoute = route
      return
    }
    interactionConfig.activateInRoom(id)
  })

  canvas.addEventListener('pointermove', (event) => interactions.updatePointer(event))
  canvas.addEventListener('pointerdown', (event) => {
    audio.unlock()
    interactions.activate(event)
  })
  canvas.addEventListener('pointerleave', () => interactions.clearHover())
  globalThis.addEventListener('pointerdown', () => audio.unlock(), { once: true })

  let pendingRoute = null
  let unlockingAfterClose = false

  function handleRouteChange() {
    const route = routeFromHash()
    if (route) {
      overlay.open(route)
      interactions.setLocked(true)
      return
    }
    if (overlay.isOpen()) {
      overlay.close()
      interactions.setLocked(true)
      rig.restore()
      unlockingAfterClose = true
    }
  }

  globalThis.addEventListener('hashchange', handleRouteChange)
  if (routeFromHash()) handleRouteChange()

  let last = performance.now()
  function frame() {
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
      globalThis.location.hash = `#/${route}`
      overlay.open(route)
    }
    if (unlockingAfterClose && !rig.isTransitioning) {
      unlockingAfterClose = false
      interactions.setLocked(false)
    }

    runtime.render()
    globalThis.requestAnimationFrame(frame)
  }
  globalThis.requestAnimationFrame(frame)

  globalThis.__ROOM_APP__ = {
    rig,
    environment,
    interactions,
    audio,
    overlay,
    hud,
    registry: room.registry,
    runtime,
  }
}

boot()
