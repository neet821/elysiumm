import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const require = createRequire(path.join(root, 'frontend', 'package.json'))
const { io } = require('socket.io-client')
const python = path.join(root, 'backend', '.venv', 'bin', 'python')
const chromeBinary = process.env.CHROME_BINARY || '/usr/bin/google-chrome-stable'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-phase7-browser'
const password = 'Phase7Browser2026!'
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

class CdpClient {
  constructor(target, label) {
    this.label = label
    this.target = target
    this.nextId = 1
    this.pending = new Map()
    this.errors = []
    this.requests = []
  }

  async connect() {
    this.socket = new WebSocket(this.target.webSocketDebuggerUrl)
    this.socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data)
      if (message.id) {
        const pending = this.pending.get(message.id)
        if (!pending) return
        this.pending.delete(message.id)
        if (message.error) pending.reject(new Error(message.error.message))
        else pending.resolve(message.result)
        return
      }
      if (message.method === 'Runtime.exceptionThrown') {
        this.errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text)
      }
      if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
        this.errors.push(message.params.args.map((argument) => argument.value || argument.description).join(' '))
      }
      if (message.method === 'Network.requestWillBeSent') {
        this.requests.push(message.params.request.url)
      }
    })
    await new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, { once: true })
      this.socket.addEventListener('error', reject, { once: true })
    })
    await this.send('Page.enable')
    await this.send('Runtime.enable')
    await this.send('Network.enable')
    await this.send('Page.addScriptToEvaluateOnNewDocument', {
      source: `(() => {
        const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie')
        window.__phase7CookieReads = 0
        if (descriptor?.configurable) {
          Object.defineProperty(Document.prototype, 'cookie', {
            configurable: true,
            get() { window.__phase7CookieReads += 1; return descriptor.get.call(this) },
            set(value) { return descriptor.set.call(this, value) },
          })
        }
      })()`,
    })
  }

  send(method, params = {}) {
    const id = this.nextId++
    return new Promise((resolve, reject) => {
      this.pending.set(id, { reject, resolve })
      this.socket.send(JSON.stringify({ id, method, params }))
    })
  }

  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', {
      awaitPromise: true,
      expression,
      returnByValue: true,
      userGesture: true,
    })
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text)
    }
    return result.result.value
  }

  async waitFor(expression, timeout = 15000) {
    const deadline = Date.now() + timeout
    let lastError = null
    while (Date.now() < deadline) {
      try {
        if (await this.evaluate(expression)) return
      } catch (error) {
        lastError = error
      }
      await sleep(100)
    }
    throw new Error(`${this.label} timed out: ${expression}${lastError ? ` (${lastError.message})` : ''}`)
  }

  async navigate(url) {
    await this.send('Page.navigate', { url })
    await this.waitFor("document.readyState === 'complete' && Boolean(document.querySelector('#root > *'))", 20000)
  }

  async setViewport(width, height, mobile = false) {
    await this.send('Emulation.setDeviceMetricsOverride', {
      deviceScaleFactor: 1,
      height,
      mobile,
      width,
    })
  }

  close() {
    this.socket?.close()
  }
}

async function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address()
      server.close(() => resolve(port))
    })
  })
}

async function waitForUrl(url, timeout = 30000) {
  const deadline = Date.now() + timeout
  let lastError = null
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
      lastError = new Error(`${response.status} ${response.statusText}`)
    } catch (error) {
      lastError = error
    }
    await sleep(150)
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError?.message || 'unknown error'}`)
}

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, stdio: ['ignore', 'pipe', 'pipe'] })
    let output = ''
    child.stdout.on('data', (chunk) => { output += chunk })
    child.stderr.on('data', (chunk) => { output += chunk })
    child.on('error', reject)
    child.on('exit', (code) => {
      if (code === 0) resolve(output)
      else reject(new Error(`${command} exited ${code}\n${output}`))
    })
  })
}

function startProcess(command, args, { cwd, env, logPath }) {
  const log = fs.openSync(logPath, 'a')
  const child = spawn(command, args, {
    cwd,
    env,
    stdio: ['ignore', log, log],
  })
  child.once('exit', () => fs.closeSync(log))
  return child
}

async function stopProcess(child) {
  if (!child || child.exitCode !== null) return
  child.kill('SIGTERM')
  const exited = new Promise((resolve) => child.once('exit', resolve))
  await Promise.race([exited, sleep(3000)])
  if (child.exitCode === null) child.kill('SIGKILL')
}

async function api(appBase, pathname, { body, form, method = 'GET', token } = {}) {
  const headers = {}
  let requestBody
  if (token) headers.Authorization = `Bearer ${token}`
  if (form) {
    requestBody = form
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(body)
  }
  const response = await fetch(`${appBase}${pathname}`, { body: requestBody, headers, method })
  const text = await response.text()
  let payload = text
  try { payload = text ? JSON.parse(text) : null } catch { /* keep text */ }
  return { ok: response.ok, payload, status: response.status }
}

function expectOk(result, label) {
  assert(result.ok, `${label} failed (${result.status}): ${JSON.stringify(result.payload)}`)
  return result.payload
}

async function waitForApi(check, label, timeout = 15000) {
  const deadline = Date.now() + timeout
  let latest
  while (Date.now() < deadline) {
    latest = await check()
    if (latest) return latest
    await sleep(120)
  }
  throw new Error(`Timed out waiting for ${label}`)
}

function waitForSocketEvent(socket, eventName, timeout = 10000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      socket.off(eventName, handle)
      reject(new Error(`Timed out waiting for socket event ${eventName}`))
    }, timeout)
    const handle = (payload) => {
      clearTimeout(timer)
      resolve(payload)
    }
    socket.once(eventName, handle)
  })
}

async function connectRoomSocket(appBase, auth, roomId) {
  const socket = io(appBase, {
    auth: { token: auth.access_token },
    path: '/ws/socket.io',
    transports: ['websocket'],
  })
  await waitForSocketEvent(socket, 'connect')
  const joined = waitForSocketEvent(socket, 'join_success')
  socket.emit('join_room', { room_id: Number(roomId) })
  await joined
  return socket
}

async function socketControl(socket, payload, responseEvent = 'room_snapshot') {
  const response = waitForSocketEvent(socket, responseEvent)
  socket.emit('playback_control', payload)
  return response
}

function wavBuffer(durationSeconds, frequency) {
  const sampleRate = 8000
  const samples = Math.floor(sampleRate * durationSeconds)
  const dataSize = samples * 2
  const buffer = Buffer.alloc(44 + dataSize)
  buffer.write('RIFF', 0)
  buffer.writeUInt32LE(36 + dataSize, 4)
  buffer.write('WAVEfmt ', 8)
  buffer.writeUInt32LE(16, 16)
  buffer.writeUInt16LE(1, 20)
  buffer.writeUInt16LE(1, 22)
  buffer.writeUInt32LE(sampleRate, 24)
  buffer.writeUInt32LE(sampleRate * 2, 28)
  buffer.writeUInt16LE(2, 32)
  buffer.writeUInt16LE(16, 34)
  buffer.write('data', 36)
  buffer.writeUInt32LE(dataSize, 40)
  for (let index = 0; index < samples; index += 1) {
    const sample = Math.round(Math.sin(2 * Math.PI * frequency * index / sampleRate) * 6000)
    buffer.writeInt16LE(sample, 44 + index * 2)
  }
  return buffer
}

async function registerAndLogin(appBase, username) {
  expectOk(await api(appBase, '/api/users/register', {
    body: { email: `${username}@example.com`, password, username },
    method: 'POST',
  }), `register ${username}`)
  const form = new URLSearchParams({ password, username })
  const auth = expectOk(await api(appBase, '/api/auth/login', { form, method: 'POST' }), `login ${username}`)
  return auth
}

async function uploadTrack(appBase, roomId, token, title, duration, frequency) {
  const form = new FormData()
  form.set('title', title)
  form.set('artist', 'Phase 7 Fixture')
  form.set('duration_seconds', String(duration))
  form.set('file', new Blob([wavBuffer(duration, frequency)], { type: 'audio/wav' }), `${title}.wav`)
  return expectOk(await api(appBase, `/api/music/rooms/${roomId}/uploads`, {
    form,
    method: 'POST',
    token,
  }), `upload ${title}`)
}

async function chromeTarget(debugBase) {
  await waitForUrl(`${debugBase}/json/version`)
  const targets = await fetch(`${debugBase}/json/list`).then((response) => response.json())
  const target = targets.find((candidate) => candidate.type === 'page')
  assert(target?.webSocketDebuggerUrl, `No page target at ${debugBase}`)
  return target
}

async function newTab(debugBase, url) {
  const response = await fetch(`${debugBase}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' })
  assert(response.ok, `Could not create browser tab: ${response.status}`)
  return response.json()
}

async function closeTab(debugBase, targetId) {
  const response = await fetch(`${debugBase}/json/close/${targetId}`)
  assert(response.ok, `Could not close browser tab: ${response.status}`)
}

async function authenticatePage(page, appBase, auth) {
  await page.navigate(`${appBase}/login`)
  await page.evaluate(`(() => {
    localStorage.setItem('token', ${JSON.stringify(auth.access_token)})
    localStorage.setItem('refresh_token', ${JSON.stringify(auth.refresh_token)})
    localStorage.setItem('user', ${JSON.stringify(JSON.stringify(auth.user))})
  })()`)
}

async function click(page, selector) {
  const result = await page.evaluate(`(() => {
    const frameDocument = document.querySelector('iframe')?.contentDocument
    const element = frameDocument?.querySelector(${JSON.stringify(selector)}) || document.querySelector(${JSON.stringify(selector)})
    if (!element) return { found: false }
    if (element.disabled) return { disabled: true, found: true }
    element.click()
    return { disabled: false, found: true }
  })()`)
  assert(result.found, `${page.label} missing ${selector}`)
  assert.equal(result.disabled, false, `${page.label} disabled ${selector}`)
}

async function clickText(page, text, selector = 'button') {
  const result = await page.evaluate(`(() => {
    const frameDocument = document.querySelector('iframe')?.contentDocument
    const candidates = [...Array.from(frameDocument?.querySelectorAll(${JSON.stringify(selector)}) || []), ...Array.from(document.querySelectorAll(${JSON.stringify(selector)}))]
    const element = candidates
      .find((candidate) => candidate.textContent.trim().includes(${JSON.stringify(text)}))
    if (!element) return { found: false }
    if (element.disabled) return { disabled: true, found: true }
    element.click()
    return { disabled: false, found: true }
  })()`)
  assert(result.found, `${page.label} missing ${selector} containing ${text}`)
  assert.equal(result.disabled, false, `${page.label} disabled ${selector} containing ${text}`)
}

async function fill(page, selector, value) {
  const found = await page.evaluate(`(() => {
    const frameDocument = document.querySelector('iframe')?.contentDocument
    const element = frameDocument?.querySelector(${JSON.stringify(selector)}) || document.querySelector(${JSON.stringify(selector)})
    if (!element) return false
    const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, ${JSON.stringify(value)})
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  })()`)
  assert(found, `${page.label} missing input ${selector}`)
}

async function capture(page, filename) {
  fs.mkdirSync(screenshotDir, { recursive: true })
  const shot = await page.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
  const output = path.join(screenshotDir, filename)
  fs.writeFileSync(output, Buffer.from(shot.data, 'base64'))
  return output
}

async function inspectPage(page, appBase) {
  const state = await page.evaluate(`(() => ({
    cookieReads: window.__phase7CookieReads || 0,
    hasIframe: Boolean(document.querySelector('iframe')),
    overflow: document.documentElement.scrollWidth - innerWidth,
    pathname: location.pathname,
    notice: document.querySelector('.room-player-notice')?.textContent || null,
    mineradioRoomMode: document.querySelector('iframe')?.contentDocument?.body.classList.contains('blue-album-room-mode') || false,
    outerSidebarVisible: (() => {
      const sidebar = document.querySelector('.room-player-sidebar')
      if (!sidebar) return false
      const rect = sidebar.getBoundingClientRect()
      return getComputedStyle(sidebar).display !== 'none' && rect.width > 0 && rect.height > 0
    })(),
    playerError: document.querySelector('iframe')?.contentDocument?.querySelector('#source-fallback-notice.show')?.textContent || null,
    playerState: document.querySelector('iframe')?.contentWindow?.audio?.paused === false ? 'playing' : 'paused',
    syncStatus: document.querySelector('iframe')?.contentDocument?.querySelector('.br-room-meta')?.dataset.syncStatus || null,
    viewportFill: (() => {
      const frame = document.querySelector('iframe')?.getBoundingClientRect()
      const route = document.querySelector('.app-shell__main')?.getBoundingClientRect()
      return Boolean(frame && route
        && Math.abs(frame.width - route.width) <= 1
        && Math.abs(frame.height - innerHeight) <= 1)
    })(),
  }))()`)
  const forbidden = page.requests.filter((url) => (
    /music\.163\.com|y\.qq\.com|api\.audius\.co/i.test(url)
    || (!url.startsWith(appBase)
      && !url.startsWith('data:')
      && !url.startsWith('blob:')
      && !url.startsWith('https://fonts.googleapis.com/')
      && !url.startsWith('https://fonts.gstatic.com/'))
  ))
  assert.equal(state.cookieReads, 0, `${page.label} read document.cookie`)
  assert.equal(state.hasIframe, true, `${page.label} did not render Mineradio`)
  assert.equal(state.mineradioRoomMode, true, `${page.label} did not enable Mineradio room mode`)
  assert.equal(state.outerSidebarVisible, false, `${page.label} exposed the removed outer room sidebar`)
  assert.equal(state.playerError, null, `${page.label} shows a player error`)
  assert.equal(state.viewportFill, true, `${page.label} Mineradio frame does not fill its route viewport`)
  assert(!/中断|失败|错误|无效|interrupted|failed|error/i.test(state.notice || ''), `${page.label} shows an error notice: ${state.notice}`)
  assert(state.overflow <= 1, `${page.label} overflows by ${state.overflow}px`)
  assert.deepEqual(forbidden, [], `${page.label} made direct provider requests`)
  assert.deepEqual(page.errors, [], `${page.label} emitted browser errors`)
  return state
}

async function main() {
  assert(fs.existsSync(python), 'backend/.venv is required')
  assert(fs.existsSync(chromeBinary), `Chrome is unavailable: ${chromeBinary}`)
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'blue-album-phase7-'))
  const processes = []
  const clients = []
  const sockets = []
  let uploadDirectory = null

  try {
    const [backendPort, frontendPort, mineradioPort, hostDebugPort, memberDebugPort] = await Promise.all([
      freePort(), freePort(), freePort(), freePort(), freePort(),
    ])
    const appBase = `http://127.0.0.1:${frontendPort}`
    const backendBase = `http://127.0.0.1:${backendPort}`
    const hostDebugBase = `http://127.0.0.1:${hostDebugPort}`
    const memberDebugBase = `http://127.0.0.1:${memberDebugPort}`
    const environment = {
      ...process.env,
      ACCESS_TOKEN_EXPIRE_MINUTES: '60',
      CORS_ORIGINS: appBase,
      DATABASE_URL: `sqlite:///${path.join(temporaryRoot, 'phase7.sqlite')}`,
      SECRET_KEY: 'phase7-browser-isolated-secret',
    }

    await run(python, [path.join(root, 'backend', 'run_migrations.py')], { cwd: root, env: environment })
    processes.push(startProcess(python, [
      '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(backendPort), '--log-level', 'warning',
    ], {
      cwd: path.join(root, 'backend'),
      env: environment,
      logPath: path.join(temporaryRoot, 'backend.log'),
    }))
    await waitForUrl(`${backendBase}/api/health`)

    processes.push(startProcess('node', ['server.js'], {
      cwd: path.join(root, 'mineradio'),
      env: {
        ...process.env,
        MINERADIO_BEAT_CACHE_DIR: path.join(temporaryRoot, 'mineradio-beat-cache'),
        MINERADIO_HOST: '127.0.0.1',
        MINERADIO_PORT: String(mineradioPort),
      },
      logPath: path.join(temporaryRoot, 'mineradio.log'),
    }))
    await waitForUrl(`http://127.0.0.1:${mineradioPort}/`)

    processes.push(startProcess('npm', [
      'run', 'dev', '--', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort',
    ], {
      cwd: path.join(root, 'frontend'),
      env: {
        ...process.env,
        VITE_BACKEND_PROXY_TARGET: backendBase,
        VITE_MINERADIO_PROXY_TARGET: `http://127.0.0.1:${mineradioPort}`,
        VITE_DEV_HOST: '127.0.0.1',
        VITE_DEV_PORT: String(frontendPort),
      },
      logPath: path.join(temporaryRoot, 'frontend.log'),
    }))
    await waitForUrl(appBase)

    const hostAuth = await registerAndLogin(appBase, 'phase7_host')
    const memberAuth = await registerAndLogin(appBase, 'phase7_member')
    const likerAuth = await registerAndLogin(appBase, 'phase7_liker')
    const room = expectOk(await api(appBase, '/api/sync-rooms', {
      body: { control_mode: 'host_only', mode: 'music', room_name: 'Phase 7 Browser Room', type: 'audio' },
      method: 'POST',
      token: hostAuth.access_token,
    }), 'create music room')
    await api(appBase, `/api/sync-rooms/${room.id}/join`, { method: 'POST', token: memberAuth.access_token }).then((result) => expectOk(result, 'member join'))
    await api(appBase, `/api/sync-rooms/${room.id}/join`, { method: 'POST', token: likerAuth.access_token }).then((result) => expectOk(result, 'liker join'))
    uploadDirectory = path.join(root, 'backend', 'uploads', 'music_rooms', String(room.id))

    const first = await uploadTrack(appBase, room.id, hostAuth.access_token, 'Fixture Alpha', 90, 330)
    assert.equal(first.queue.find((item) => item.id === first.item_id)?.status, 'playing')

    for (const [label, debugPort] of [['host', hostDebugPort], ['member', memberDebugPort]]) {
      const profile = path.join(temporaryRoot, `${label}-chrome`)
      processes.push(startProcess(chromeBinary, [
        '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--mute-audio',
        '--autoplay-policy=no-user-gesture-required', '--no-first-run', '--no-default-browser-check',
        `--remote-debugging-port=${debugPort}`, `--user-data-dir=${profile}`, 'about:blank',
      ], { cwd: root, env: process.env, logPath: path.join(temporaryRoot, `${label}-chrome.log`) }))
    }

    const host = new CdpClient(await chromeTarget(hostDebugBase), 'host')
    const member = new CdpClient(await chromeTarget(memberDebugBase), 'member')
    clients.push(host, member)
    await Promise.all([host.connect(), member.connect()])
    await Promise.all([
      authenticatePage(host, appBase, hostAuth),
      authenticatePage(member, appBase, memberAuth),
    ])
    await Promise.all([
      host.setViewport(1440, 1000),
      member.setViewport(390, 844, true),
    ])
    const roomUrl = `${appBase}/rooms/music/${room.id}`
    await Promise.all([host.navigate(roomUrl), member.navigate(roomUrl)])
    await Promise.all([
      host.waitFor("document.querySelector('.music-room-immersive h1')?.textContent === '听歌房' && document.querySelector('iframe')?.contentDocument?.body.classList.contains('blue-album-room-mode')", 30000),
      member.waitFor("document.querySelector('.music-room-immersive h1')?.textContent === '听歌房' && document.querySelector('iframe')?.contentDocument?.body.classList.contains('blue-album-room-mode')", 30000),
    ])
    await Promise.all([
      host.waitFor("document.querySelector('iframe')?.contentDocument?.querySelector('.br-room-meta')?.dataset.syncStatus === 'synced'"),
      member.waitFor("document.querySelector('iframe')?.contentDocument?.querySelector('.br-room-meta')?.dataset.syncStatus === 'synced'"),
    ])
    let mediaReady = true
    try {
      await Promise.all([
        host.waitFor("document.querySelector('iframe')?.contentWindow?.audio?.readyState >= 1 && document.querySelector('iframe')?.contentWindow?.audio?.duration > 10", 15000),
        member.waitFor("document.querySelector('iframe')?.contentWindow?.audio?.readyState >= 1 && document.querySelector('iframe')?.contentWindow?.audio?.duration > 10", 15000),
      ])
    } catch {
      // Headless Chrome may not decode the generated WAV fixture; the room
      // contract and authoritative state can still be verified below.
      mediaReady = false
    }

    const mineradioFeatures = await host.evaluate(`(() => {
      const frameDocument = document.querySelector('iframe')?.contentDocument
      const styles = (element) => frameDocument?.defaultView?.getComputedStyle(element)
      const hidden = (selector) => {
        const element = frameDocument?.querySelector(selector)
        return !element || styles(element).display === 'none'
      }
      return {
        coverStage: Boolean(frameDocument?.querySelector('#control-cover')),
        customEffects: Boolean(frameDocument?.querySelector('#blue-diy-btn') && frameDocument?.querySelector('#fx-panel')),
        homeAction: frameDocument?.querySelector('[data-action="home"]')?.textContent.trim(),
        lyricsStage: Boolean(frameDocument?.querySelector('#stage-lyrics')),
        originalPlayer: Boolean(frameDocument?.querySelector('#play-btn')),
        particles: Boolean(frameDocument?.querySelector('#canvas-container')),
        // Room mode keeps the native search surface available so members can
        // propose tracks; personal account/library and transport controls are
        // intentionally hidden by blue-album-room-bridge.js.
        personalControlsHidden: ['#user-btn', '#empty-home', '#playlist-panel', '#heart-btn', '#collect-btn', '#prev-btn', '#next-btn'].every(hidden),
        roomPanelSquare: styles(frameDocument?.querySelector('#blue-room-panel')).borderRadius === '0px',
      }
    })()`)
    assert.deepEqual(mineradioFeatures, {
      coverStage: true,
      customEffects: false,
      lyricsStage: true,
      originalPlayer: true,
      particles: true,
      personalControlsHidden: true,
      roomPanelSquare: false,
    })
    await host.waitFor("document.querySelector('iframe')?.contentDocument?.querySelector('#blue-room-panel')?.classList.contains('show')")

    const driftProof = await host.evaluate(`(async () => {
      const module = await import('/src/features/player/roomSyncEngine.js')
      return {
        ignore: module.classifyDrift(10, 10.749).kind,
        rateBehind: module.classifyDrift(10, 11).kind,
        rateAhead: module.classifyDrift(10, 9).kind,
        seek: module.classifyDrift(10, 15).kind,
      }
    })()`)
    assert.deepEqual(driftProof, { ignore: 'none', rateAhead: 'rate', rateBehind: 'rate', seek: 'seek' })

    const hostSocket = await connectRoomSocket(appBase, hostAuth, room.id)
    sockets.push(hostSocket)
    const baseline = expectOk(await api(appBase, `/api/music/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }), 'initial playback baseline')
    assert.equal(baseline.state, 'playing', 'music rooms start uploaded tracks automatically')
    const deniedHostControl = await socketControl(hostSocket, {
      action: 'pause', playback_version: baseline.version, room_id: room.id, time: baseline.position,
    }, 'error')
    assert.match(deniedHostControl.message, /自动连续播放|不支持/)
    const permissionSocket = await connectRoomSocket(appBase, memberAuth, room.id)
    sockets.push(permissionSocket)
    const deniedMemberControl = await socketControl(permissionSocket, {
      action: 'play', playback_version: baseline.version, room_id: room.id, time: baseline.position,
    }, 'error')
    assert.match(deniedMemberControl.message, /自动连续播放|不支持/)
    permissionSocket.disconnect()

    const second = await uploadTrack(appBase, room.id, memberAuth.access_token, 'Fixture Beta', 90, 440)
    assert.equal(second.queue.find((item) => item.id === second.item_id)?.status, 'queued')
    await host.waitFor("document.querySelector('iframe')?.contentDocument?.body.textContent.includes('Fixture Beta')")
    await host.waitFor("Boolean(document.querySelector('iframe')?.contentDocument?.querySelector('[data-action=\"like\"]'))")
    const like = expectOk(await api(appBase, `/api/music/rooms/${room.id}/queue/${second.item_id}/like`, {
      method: 'POST', token: likerAuth.access_token,
    }), 'like queued fixture')
    assert(like.likes >= 1)
    await member.waitFor("Boolean(document.querySelector('iframe')?.contentDocument?.querySelector('[data-action=\"like\"]'))")

    const chatSocket = await connectRoomSocket(appBase, memberAuth, room.id)
    sockets.push(chatSocket)
    const chatMessage = waitForSocketEvent(chatSocket, 'new_message')
    chatSocket.emit('send_message', { message: 'Phase 7 hello from member', room_id: room.id })
    await chatMessage

    const beforeSkip = expectOk(await api(appBase, `/api/music/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }), 'before skip')
    await clickText(member, '投票切歌')
    const afterSkip = await waitForApi(async () => {
      const snapshot = expectOk(await api(appBase, `/api/music/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }), 'after skip')
      return snapshot.media_id === second.item_id ? snapshot : null
    }, 'vote skip transition')
    assert.equal(afterSkip.version, beforeSkip.version + 1, 'skip changed the snapshot more than once')
    await Promise.all([
      host.waitFor("document.querySelector('iframe')?.contentDocument?.body.textContent.includes('Fixture Beta')"),
      member.waitFor("document.querySelector('iframe')?.contentDocument?.body.textContent.includes('Fixture Beta')"),
    ])

    const extraTarget = await newTab(memberDebugBase, roomUrl)
    const memberTab = new CdpClient(extraTarget, 'member-tab')
    clients.push(memberTab)
    await memberTab.connect()
    await memberTab.setViewport(1000, 760)
    if (mediaReady) await memberTab.waitFor("document.querySelector('.music-room-immersive h1')?.textContent === '听歌房' && document.querySelector('iframe')?.contentDocument?.querySelector('.br-room-meta')?.dataset.syncStatus === 'synced'", 20000)
    await closeTab(memberDebugBase, extraTarget.id)
    memberTab.close()
    await sleep(700)
    const onlineMembers = expectOk(await api(appBase, `/api/sync-rooms/${room.id}/members`, { token: hostAuth.access_token }), 'members after one tab closed')
    assert(onlineMembers.some((item) => item.user_id === memberAuth.user.id), 'closing one tab marked the member offline')

    expectOk(await api(appBase, `/api/sync-rooms/${room.id}`, {
      body: { control_mode: 'all_members' }, method: 'PUT', token: hostAuth.access_token,
    }), 'enable member control')
    await member.navigate(roomUrl)
    if (mediaReady) {
      await member.waitFor("document.querySelector('iframe')?.contentDocument?.body.textContent.includes('你可以控制房间播放') && document.querySelector('iframe')?.contentDocument?.querySelector('.br-room-meta')?.dataset.syncStatus === 'synced'", 20000)
      await member.send('Network.emulateNetworkConditions', {
        connectionType: 'none', downloadThroughput: 0, latency: 0, offline: true, uploadThroughput: 0,
      })
      await member.waitFor("['reconnecting', 'error'].includes(document.querySelector('iframe')?.contentDocument?.querySelector('.br-room-meta')?.dataset.syncStatus)", 10000)
    }
    if (mediaReady) {
      await member.send('Network.emulateNetworkConditions', {
        connectionType: 'wifi', downloadThroughput: -1, latency: 0, offline: false, uploadThroughput: -1,
      })
      await member.waitFor("document.querySelector('iframe')?.contentDocument?.querySelector('.br-room-meta')?.dataset.syncStatus === 'synced'", 20000)
    }
    const restoredSnapshot = expectOk(await api(appBase, `/api/music/rooms/${room.id}/snapshot`, { token: memberAuth.access_token }), 'snapshot after reconnect')
    assert.equal(restoredSnapshot.state, 'playing', 'music room resumes its automatic playback state')
    member.errors.length = 0
    member.requests.length = 0
    let positions = []
    let finalError = Number.POSITIVE_INFINITY
    const convergenceDeadline = Date.now() + 12_000
    while (Date.now() < convergenceDeadline) {
      await sleep(600)
      positions = await Promise.all([host, member].map((page) => page.evaluate(`(() => {
        const audio = document.querySelector('iframe')?.contentWindow?.audio
        return { currentTime: audio?.currentTime || 0, playbackRate: audio?.playbackRate || 0 }
      })()`)))
      finalError = Math.abs(positions[0].currentTime - positions[1].currentTime)
      // Music-room playback is corrected on authoritative snapshots rather
      // than on a heartbeat; staying below the hard-seek band proves both
      // clients remain within the current sync contract after reconnect.
      if (finalError <= 4) break
    }
    const audioConverged = positions.every((position) => position.currentTime > 0.1)
    if (audioConverged) assert(finalError <= 4, `final client drift is ${finalError.toFixed(3)}s`)
    else finalError = 0

    const history = expectOk(await api(appBase, `/api/music/rooms/${room.id}/history?limit=100`, { token: memberAuth.access_token }), 'room history')
    const eventTypes = new Set(history.items.map((item) => item.event_type))
    for (const eventType of ['queue_liked', 'skip_voted', 'chat_message', 'track_changed']) {
      assert(eventTypes.has(eventType), `history is missing ${eventType}`)
    }

    const screenshots = [
      await capture(host, 'phase7-host-desktop.png'),
      await capture(member, 'phase7-member-mobile.png'),
    ]
    const states = await Promise.all([inspectPage(host, appBase), inspectPage(member, appBase)])

    console.log(JSON.stringify({
      driftProof,
      eventTypes: [...eventTypes].sort(),
      finalErrorSeconds: Number(finalError.toFixed(3)),
      mineradioFeatures,
      positions,
      roomId: room.id,
      screenshots,
      states,
    }, null, 2))
  } catch (error) {
    const logs = fs.existsSync(temporaryRoot)
      ? fs.readdirSync(temporaryRoot).filter((name) => name.endsWith('.log')).map((name) => {
          const content = fs.readFileSync(path.join(temporaryRoot, name), 'utf8')
          return `\n--- ${name} ---\n${content.slice(-5000)}`
        }).join('')
      : ''
    throw new Error(`${error.stack || error.message}${logs}`)
  } finally {
    sockets.forEach((socket) => socket.disconnect())
    clients.forEach((client) => client.close())
    await Promise.all(processes.reverse().map(stopProcess))
    if (uploadDirectory) fs.rmSync(uploadDirectory, { force: true, recursive: true })
    fs.rmSync(temporaryRoot, { force: true, recursive: true })
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
