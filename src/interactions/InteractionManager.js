import * as THREE from 'three'

const HOVER_COLOR = '#d84315'

export class InteractionManager {
  constructor({ camera, canvas, onHover = () => {} }) {
    if (!camera || !canvas) {
      throw new TypeError('InteractionManager requires camera and canvas')
    }
    this.camera = camera
    this.canvas = canvas
    this.onHover = onHover
    this.items = new Map()
    this.proxies = []
    this.pointer = { x: 0, y: 0 }
    this.locked = false
    this.hoveredId = null
    this._handler = null
    this._raycaster = new THREE.Raycaster()
    this._ndc = new THREE.Vector2()
    this._originColors = new Map()
  }

  register({ id, proxy, visual, label }) {
    if (!id || !proxy) return
    if (this.items.has(id)) return
    this.items.set(id, { id, proxy, visual, label: label ?? '' })
    this.proxies.push(proxy)
  }

  setActionHandler(handler) {
    this._handler = handler
  }

  setLocked(locked) {
    this.locked = locked
    if (locked) this._clearHover()
  }

  updatePointer(event) {
    if (this.locked) return
    const rect = this.canvas.getBoundingClientRect()
    if (!rect.width || !rect.height) return
    this._ndc.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    )
    this.pointer.x = this._ndc.x
    this.pointer.y = this._ndc.y
    this._raycaster.setFromCamera(this._ndc, this.camera)
    const hits = this._raycaster.intersectObjects(this.proxies, false)
    this._setHover(hits[0]?.object.userData.interactionId ?? null)
  }

  activate(event) {
    this.updatePointer(event)
    const id = this.hoveredId
    if (!id) return null
    this._handler?.(id)
    return id
  }

  screenPositionFor(id, { nx = 0.5, ny = 0.5 } = {}) {
    const item = this.items.get(id)
    if (!item) return null
    const rect = this.canvas.getBoundingClientRect()
    const geometry = item.proxy.geometry
    const width = geometry?.parameters?.width ?? 1
    const height = geometry?.parameters?.height ?? 1
    const depth = geometry?.parameters?.depth ?? 1

    const frontPoint = new THREE.Vector3(0, 0, depth / 2)
    const backPoint = new THREE.Vector3(0, 0, -depth / 2)
    item.proxy.localToWorld(frontPoint)
    item.proxy.localToWorld(backPoint)
    frontPoint.project(this.camera)
    backPoint.project(this.camera)
    const frontFacesCamera = frontPoint.z <= backPoint.z
    const zSign = frontFacesCamera ? 1 : -1

    const projected = []
    for (const [sx, sy] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) {
      const corner = new THREE.Vector3(
        sx * (width / 2),
        sy * (height / 2),
        zSign * (depth / 2),
      )
      item.proxy.localToWorld(corner)
      corner.project(this.camera)
      projected.push(corner)
    }
    const minX = Math.min(...projected.map((point) => point.x))
    const maxX = Math.max(...projected.map((point) => point.x))
    const minY = Math.min(...projected.map((point) => point.y))
    const maxY = Math.max(...projected.map((point) => point.y))
    const ndcX = THREE.MathUtils.clamp(minX + (maxX - minX) * nx, -1, 1)
    const ndcY = THREE.MathUtils.clamp(minY + (maxY - minY) * ny, -1, 1)
    const depthAtPoint = Math.max(...projected.map((point) => point.z))
    return {
      x: (ndcX * 0.5 + 0.5) * rect.width + rect.left,
      y: (-ndcY * 0.5 + 0.5) * rect.height + rect.top,
      behind: depthAtPoint > 1,
    }
  }

  clearHover() {
    this._clearHover()
  }

  _setHover(id) {
    if (id === this.hoveredId) return
    if (this.hoveredId) this._clearHover()
    if (id && this.items.has(id)) {
      const item = this.items.get(id)
      this.hoveredId = id
      this._emphasize(item, true)
      globalThis.document.body.style.cursor = 'pointer'
      this.onHover(id, item.label)
    }
  }

  _clearHover() {
    if (!this.hoveredId) return
    const item = this.items.get(this.hoveredId)
    if (item) this._emphasize(item, false)
    this.hoveredId = null
    globalThis.document.body.style.cursor = ''
    this.onHover(null, '')
  }

  _emphasize(item, on) {
    item.visual?.traverse((object) => {
      const outline = object.userData?.outline
      if (!outline) return
      const material = outline.material
      if (on) {
        if (!this._originColors.has(material)) {
          this._originColors.set(material, material.color.getHex())
        }
        material.color.set(HOVER_COLOR)
      } else if (this._originColors.has(material)) {
        material.color.setHex(this._originColors.get(material))
        this._originColors.delete(material)
      }
    })
  }
}
