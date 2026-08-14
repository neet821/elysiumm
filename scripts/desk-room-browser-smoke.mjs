import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawn } from 'node:child_process'

const appBase = process.env.BLUE_ALBUM_URL || 'http://127.0.0.1:5173'
const outputDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-desk-room'
const debugPort = Number(process.env.CHROME_DEBUG_PORT || 9241)
const chromeBinary = process.env.CHROME_BIN || '/usr/bin/google-chrome-stable'
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

class CdpClient {
  constructor(url) {
    this.url = url
    this.nextId = 1
    this.pending = new Map()
  }

  async connect() {
    this.socket = new WebSocket(this.url)
    this.socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data)
      if (!message.id) return
      const pending = this.pending.get(message.id)
      if (!pending) return
      this.pending.delete(message.id)
      if (message.error) pending.reject(new Error(message.error.message))
      else pending.resolve(message.result)
    })
    await new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, { once: true })
      this.socket.addEventListener('error', reject, { once: true })
    })
  }

  send(method, params = {}) {
    const id = this.nextId
    this.nextId += 1
    return new Promise((resolve, reject) => {
      this.pending.set(id, { reject, resolve })
      this.socket.send(JSON.stringify({ id, method, params }))
    })
  }

  async evaluate(expression) {
    const response = await this.send('Runtime.evaluate', { awaitPromise: true, expression, returnByValue: true, userGesture: true })
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text)
    return response.result.value
  }

  async waitFor(expression, timeout = 12000) {
    const deadline = Date.now() + timeout
    while (Date.now() < deadline) {
      if (await this.evaluate(expression)) return
      await sleep(100)
    }
    throw new Error(`Timed out waiting for: ${expression}`)
  }
}

async function getTarget() {
  const deadline = Date.now() + 10000
  while (Date.now() < deadline) {
    try {
      const targets = await fetch(`http://127.0.0.1:${debugPort}/json/list`).then((response) => response.json())
      const page = targets.find((target) => target.type === 'page')
      if (page) return page
    } catch {
      // Chrome is still starting.
    }
    await sleep(100)
  }
  throw new Error('Chrome debugging endpoint did not start')
}

async function capture(client, filename) {
  fs.mkdirSync(outputDir, { recursive: true })
  const shot = await client.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
  const outputPath = path.join(outputDir, filename)
  fs.writeFileSync(outputPath, Buffer.from(shot.data, 'base64'))
  return outputPath
}

async function clickByText(client, text) {
  const clicked = await client.evaluate(`(() => {
    const element = [...document.querySelectorAll('button')].find((button) => button.textContent.trim() === ${JSON.stringify(text)})
    if (!element) return false
    element.click()
    return true
  })()`)
  assert.equal(clicked, true, `Missing button: ${text}`)
}

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'blue-album-desk-room-chrome-'))
const chrome = spawn(chromeBinary, [
  '--headless=new', '--disable-gpu', '--enable-unsafe-swiftshader', '--no-sandbox', '--disable-dev-shm-usage',
  `--remote-debugging-port=${debugPort}`, `--user-data-dir=${profile}`, '--window-size=1440,900', 'about:blank',
], { stdio: 'ignore' })

try {
  const target = await getTarget()
  const client = new CdpClient(target.webSocketDebuggerUrl)
  await client.connect()
  await client.send('Page.enable')
  await client.send('Runtime.enable')
  await client.send('Emulation.setDeviceMetricsOverride', { deviceScaleFactor: 1, height: 900, mobile: false, width: 1440 })
  await client.send('Page.navigate', { url: appBase })
  await client.waitFor(`document.readyState === 'complete' && document.querySelector('.desk-room__shell-layer')?.complete`)
  await clickByText(client, '午后')
  await clickByText(client, '城市')
  await sleep(700)

  const desktop = await client.evaluate(`(() => {
    const room = document.querySelector('.desk-room')
    const layers = [...document.querySelectorAll('.desk-room__layer')]
    return {
      label: room?.getAttribute('aria-label'),
      mode: room?.dataset.renderMode,
      view: room?.dataset.view,
      layers: layers.length,
      loaded: layers.every((image) => image.complete && image.naturalWidth > 0),
      overflow: document.documentElement.scrollWidth - innerWidth,
    }
  })()`)
  assert.deepEqual(desktop, { label: '窗前书桌房间', mode: 'layered', view: 'city', layers: 4, loaded: true, overflow: 0 })
  const desktopScreenshot = await capture(client, 'desktop-afternoon-city.png')

  const parallax = await client.evaluate(`(() => {
    const visual = document.querySelector('.desk-room__visual')
    const rect = visual.getBoundingClientRect()
    visual.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, clientX: rect.right - 20, clientY: rect.top + 40 }))
    return new Promise((resolve) => requestAnimationFrame(() => resolve({
      chair: visual.style.getPropertyValue('--chair-x'),
      desk: visual.style.getPropertyValue('--desk-x'),
      room: visual.style.getPropertyValue('--room-x'),
      view: visual.style.getPropertyValue('--view-x'),
    })))
  })()`)
  assert.notEqual(parallax.chair, '0px')
  assert.notEqual(parallax.desk, parallax.chair)
  assert.notEqual(parallax.room, parallax.view)

  await clickByText(client, '夜晚')
  await clickByText(client, '雨')
  await client.waitFor(`document.querySelector('.desk-room')?.dataset.time === 'night' && Boolean(document.querySelector('.desk-room__rain-layer'))`)
  const nightScreenshot = await capture(client, 'desktop-night-rain.png')
  await clickByText(client, '午后')
  await clickByText(client, '晴')

  await clickByText(client, '进入电脑')
  await client.waitFor(`Boolean(document.querySelector('[role="dialog"][aria-label="电脑桌面"]'))`)
  const links = await client.evaluate(`[...document.querySelectorAll('.desk-room__computer-links a')].map((link) => new URL(link.href).pathname)`)
  assert.deepEqual(links, ['/live', '/music', '/tools'])
  await client.evaluate(`window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))`)
  await client.waitFor(`!document.querySelector('[role="dialog"][aria-label="电脑桌面"]')`)

  await client.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] })
  await client.waitFor(`document.querySelector('.desk-room')?.dataset.motion === 'reduced'`)
  await client.send('Emulation.setDeviceMetricsOverride', { deviceScaleFactor: 1, height: 844, mobile: true, width: 390 })
  await sleep(500)
  const mobile = await client.evaluate(`({ overflow: document.documentElement.scrollWidth - innerWidth, width: innerWidth, motion: document.querySelector('.desk-room')?.dataset.motion })`)
  assert.deepEqual(mobile, { overflow: 0, width: 390, motion: 'reduced' })
  const mobileScreenshot = await capture(client, 'mobile-reduced-motion.png')

  console.log(JSON.stringify({ desktop, desktopScreenshot, links, mobile, mobileScreenshot, nightScreenshot, parallax }, null, 2))
  client.socket.close()
} finally {
  chrome.kill('SIGTERM')
  fs.rmSync(profile, { force: true, recursive: true })
}
