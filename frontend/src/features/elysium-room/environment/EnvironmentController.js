import * as THREE from 'three'
import { createEnvironmentState } from './environmentState.js'
import { createPageThemeVariables, environmentPalettes } from './palette.js'

const SCENERY_BY_MODE = Object.freeze({
  dawn: 'cloudy',
  day: 'nature',
  dusk: 'city',
  night: 'night',
})

const SCENERY_ORDER = Object.freeze(['nature', 'city', 'cloudy', 'night'])

const LIGHT_BY_MODE = Object.freeze({
  dawn: { hemisphere: 1.0, sun: 1.35, sunColor: '#ffd9b0' },
  day: { hemisphere: 2.1, sun: 0.55, sunColor: '#fff4df' },
  dusk: { hemisphere: 0.82, sun: 1.0, sunColor: '#ffbc91' },
  night: { hemisphere: 0.42, sun: 0.14, sunColor: '#a9b8d2' },
})

const ALBUM_COLORS = Object.freeze([
  '#9b6648',
  '#536f78',
  '#756c76',
  '#60715e',
  '#855b3d',
  '#9a7b4e',
])

export class EnvironmentController {
  constructor({
    state = createEnvironmentState(),
    scene,
    materials,
    lights,
    registry,
    audio = null,
  } = {}) {
    if (!scene || !materials || !lights || !registry) {
      throw new TypeError('EnvironmentController requires scene, materials, lights, and registry')
    }
    this.state = state
    this.scene = scene
    this.materials = materials
    this.lights = lights
    this.registry = registry
    this.audio = audio
    this.lampOn = false
    this.recordOn = false
    this.albumIndex = 0
    this._listeners = new Set()
    this._disposables = []
    this._lampLight = null
    this._lampGlow = null
    this._tonearmTarget = 0
    this._albumCard = null
    this._albumCardMaterial = null
    this._albumLineMaterial = null
    this._setupLamp()
    this._setupAlbumCard()
    this.apply()
  }

  subscribe(listener) {
    this._listeners.add(listener)
    listener(this.getSnapshot())
    return () => this._listeners.delete(listener)
  }

  getSnapshot() {
    return {
      ...this.state.getState(),
      scenery: this.registry.window.group.userData.scenery ?? 'nature',
      lampOn: this.lampOn,
      recordOn: this.recordOn,
      albumIndex: this.albumIndex,
      albumColor: ALBUM_COLORS[this.albumIndex],
    }
  }

  apply() {
    const snapshot = this.state.getState()
    const palette = environmentPalettes[snapshot.mode]
    this.materials.applyPalette(palette)
    this.scene.background = new THREE.Color(palette.sky)

    const lighting = LIGHT_BY_MODE[snapshot.mode]
    this.lights.hemisphere.intensity = lighting.hemisphere
    this.lights.sun.intensity = lighting.sun
    this.lights.sun.color.set(lighting.sunColor)

    const documentRoot = globalThis.document?.documentElement
    if (documentRoot) {
      for (const [name, value] of Object.entries(createPageThemeVariables(palette))) {
        documentRoot.style.setProperty(name, value)
      }
      documentRoot.dataset.environment = snapshot.mode
      globalThis.document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute('content', palette.sky)
    }

    this._switchScenery(SCENERY_BY_MODE[snapshot.mode])
    this._emit()
  }

  setTimeMode(mode) {
    this.state.setMode(mode)
    this.apply()
  }

  async cycleScenery() {
    const current = this.registry.window.group.userData.scenery ?? 'nature'
    const next = SCENERY_ORDER[(SCENERY_ORDER.indexOf(current) + 1) % SCENERY_ORDER.length]
    await this._switchScenery(next)
  }

  async _switchScenery(name) {
    const current = this.registry.window.group.userData.scenery
    if (name === current) return
    const applied = await this.registry.window.setScenery(name)
    if (applied) this._emit()
  }

  toggleLamp() {
    this.lampOn = !this.lampOn
    if (this._lampLight) this._lampLight.intensity = this.lampOn ? 1.5 : 0
    if (this._lampGlow) this._lampGlow.visible = this.lampOn
    this._emit()
  }

  toggleRecord() {
    if (this.audio) {
      this.recordOn = this.audio.toggle()
    } else {
      this.recordOn = !this.recordOn
    }
    this._tonearmTarget = this.recordOn ? 0.5 : 0
    this._emit()
  }

  cycleAlbum() {
    this.albumIndex = (this.albumIndex + 1) % ALBUM_COLORS.length
    if (this._albumCardMaterial) {
      this._albumCardMaterial.color.set(ALBUM_COLORS[this.albumIndex])
    }
    this._emit()
  }

  update(delta) {
    const dt = Number.isFinite(delta) && delta > 0 ? delta : 0
    const record = this.registry.recordPlayer?.record
    if (record && this.recordOn) {
      record.rotation.y += dt * 2.4
    }
    const tonearm = this.registry.recordPlayer?.tonearm
    if (tonearm) {
      tonearm.rotation.y = THREE.MathUtils.lerp(
        tonearm.rotation.y,
        this._tonearmTarget,
        Math.min(1, dt * 4),
      )
    }
  }

  _setupLamp() {
    const lamp = this.registry.lamp
    if (!lamp?.visual) return

    this._lampLight = new THREE.PointLight('#ffb066', 0, 7, 1.8)
    lamp.visual.getWorldPosition(this._lampLight.position)
    this._lampLight.position.y += 0.2
    this.scene.add(this._lampLight)

    const glowMaterial = new THREE.MeshBasicMaterial({
      color: '#ffd9a0',
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
    })
    const glow = new THREE.Mesh(new THREE.SphereGeometry(0.42, 12, 8), glowMaterial)
    glow.name = 'lamp-glow'
    glow.position.set(0, 0.74, 0)
    glow.scale.set(1, 0.65, 1)
    glow.visible = false
    lamp.visual.add(glow)
    this._lampGlow = glow

    this._disposables.push(() => {
      glowMaterial.dispose()
      this.scene.remove(this._lampLight)
    })
  }

  _setupAlbumCard() {
    const rack = this.registry.recordRack
    if (!rack?.visual) return

    this._albumCardMaterial = new THREE.MeshBasicMaterial({ color: ALBUM_COLORS[0] })
    this._albumLineMaterial = new THREE.LineBasicMaterial({ color: '#101010' })
    const geometry = new THREE.BoxGeometry(0.46, 0.17, 0.05)
    const card = new THREE.Mesh(geometry, this._albumCardMaterial)
    card.name = 'now-playing-album-card'
    card.position.set(0, 0.13, 0.39)
    const outline = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), this._albumLineMaterial)
    const holder = new THREE.Group()
    holder.name = 'now-playing-album'
    holder.add(card, outline)
    rack.visual.add(holder)
    this._albumCard = holder

    this._disposables.push(() => {
      this._albumCardMaterial.dispose()
      this._albumLineMaterial.dispose()
      geometry.dispose()
    })
  }

  _emit() {
    const snapshot = this.getSnapshot()
    this._listeners.forEach((listener) => listener(snapshot))
  }

  dispose() {
    this._disposables.forEach((dispose) => dispose())
    this._disposables = []
    this._listeners.clear()
  }
}
