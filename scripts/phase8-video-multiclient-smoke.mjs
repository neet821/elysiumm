import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const require = createRequire(path.join(root, 'frontend', 'package.json'))
const { io } = require('socket.io-client')
const { WebSocket: NodeWebSocket } = require('ws')
const python = path.join(root, 'backend', '.venv', 'bin', 'python')
const chromeBinary = process.env.CHROME_BINARY || '/usr/bin/google-chrome-stable'
const ffmpegBinary = process.env.FFMPEG_BINARY || '/usr/bin/ffmpeg'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-phase8-video-browser'
const password = 'Phase8Browser2026!'
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

class CdpClient {
  constructor(target, label) {
    this.errors = []
    this.label = label
    this.nextId = 1
    this.pending = new Map()
    this.requests = []
    this.target = target
  }

  async connect() {
    this.socket = new NodeWebSocket(this.target.webSocketDebuggerUrl)
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
    await this.send('DOM.enable')
    await this.send('Page.addScriptToEvaluateOnNewDocument', {
      source: `(() => {
        const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie')
        window.__phase8CookieReads = 0
        if (descriptor?.configurable) {
          Object.defineProperty(Document.prototype, 'cookie', {
            configurable: true,
            get() { window.__phase8CookieReads += 1; return descriptor.get.call(this) },
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
  const child = spawn(command, args, { cwd, env, stdio: ['ignore', log, log] })
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
  if (form) requestBody = form
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(body)
  }
  const response = await fetch(`${appBase}${pathname}`, { body: requestBody, headers, method })
  const text = await response.text()
  let payload = text
  try { payload = text ? JSON.parse(text) : null } catch { /* retain text */ }
  return { ok: response.ok, payload, status: response.status }
}

function expectOk(result, label) {
  assert(result.ok, `${label} failed (${result.status}): ${JSON.stringify(result.payload)}`)
  return result.payload
}

async function waitForApi(check, label, timeout = 15000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const result = await check()
    if (result) return result
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

async function registerAndLogin(appBase, username) {
  expectOk(await api(appBase, '/api/users/register', {
    body: { email: `${username}@example.com`, password, username },
    method: 'POST',
  }), `register ${username}`)
  const form = new URLSearchParams({ password, username })
  return expectOk(await api(appBase, '/api/auth/login', { form, method: 'POST' }), `login ${username}`)
}

async function uploadVideo(appBase, roomId, token, filePath, title) {
  const form = new FormData()
  form.set('title', title)
  form.set('file', new Blob([fs.readFileSync(filePath)], { type: 'video/webm' }), path.basename(filePath))
  return expectOk(await api(appBase, `/api/video/rooms/${roomId}/items/upload`, {
    form, method: 'POST', token,
  }), `upload ${title}`)
}

async function uploadSubtitle(appBase, roomId, itemId, token) {
  const form = new FormData()
  form.set('label', '中文验收字幕')
  form.set('language', 'zh-CN')
  form.set('file', new Blob([
    'WEBVTT\n\n00:00:00.000 --> 00:00:05.000\nPhase 8 fixture subtitle\n',
  ], { type: 'text/vtt' }), 'phase8-fixture.vtt')
  return expectOk(await api(appBase, `/api/video/rooms/${roomId}/items/${itemId}/subtitles`, {
    form, method: 'POST', token,
  }), 'upload subtitle')
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
  const state = await page.evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)})
    if (!element) return { found: false }
    if (element.disabled) return { disabled: true, found: true }
    element.click()
    return { disabled: false, found: true }
  })()`)
  assert(state.found, `${page.label} missing ${selector}`)
  assert.equal(state.disabled, false, `${page.label} disabled ${selector}`)
}

async function ensureVideoPlaying(page) {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const state = await page.evaluate(`(() => {
      const video = document.querySelector('[data-testid="video-room-media"]')
      if (!video) return { found: false, paused: true }
      if (!video.paused) return { found: true, paused: false }
      const button = document.querySelector('button[aria-label^="播放 "]')
      if (button && !button.disabled) button.click()
      return { found: true, paused: video.paused }
    })()`)
    assert(state.found, `${page.label} missing video media`)
    if (!state.paused) return
    await sleep(400)
  }
  await page.waitFor("document.querySelector('[data-testid=\"video-room-media\"]') && !document.querySelector('[data-testid=\"video-room-media\"]')?.paused", 20000)
}

async function clickText(page, text, selector = 'button') {
  const state = await page.evaluate(`(() => {
    const element = Array.from(document.querySelectorAll(${JSON.stringify(selector)}))
      .find((candidate) => candidate.textContent.trim().includes(${JSON.stringify(text)}))
    if (!element) return { found: false }
    if (element.disabled) return { disabled: true, found: true }
    element.click()
    return { disabled: false, found: true }
  })()`)
  assert(state.found, `${page.label} missing ${selector} containing ${text}`)
  assert.equal(state.disabled, false, `${page.label} disabled ${selector} containing ${text}`)
}

async function fill(page, selector, value) {
  const found = await page.evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)})
    if (!element) return false
    const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, ${JSON.stringify(value)})
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  })()`)
  assert(found, `${page.label} missing input ${selector}`)
}

async function selectValue(page, selector, value) {
  const changed = await page.evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)})
    if (!element) return false
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(element, ${JSON.stringify(String(value))})
    element.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  })()`)
  assert(changed, `${page.label} missing select ${selector}`)
}

async function capture(page, filename) {
  fs.mkdirSync(screenshotDir, { recursive: true })
  const shot = await page.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
  const output = path.join(screenshotDir, filename)
  fs.writeFileSync(output, Buffer.from(shot.data, 'base64'))
  return output
}

function localVideoFingerprint(filePath) {
  const content = fs.readFileSync(filePath)
  const sampleSize = 1024 * 1024
  const offsets = [
    0,
    Math.max(0, Math.floor(content.length / 2) - Math.floor(sampleSize / 2)),
    Math.max(0, content.length - sampleSize),
  ]
  const hash = crypto.createHash('sha256')
  hash.update(String(content.length))
  for (const offset of offsets) hash.update(content.subarray(offset, Math.min(content.length, offset + sampleSize)))
  return hash.digest('hex')
}

async function selectLocalFile(page, labelText, filePath) {
  const document = await page.send('DOM.getDocument', { depth: -1, pierce: true })
  const { nodeId } = await page.send('DOM.querySelector', {
    nodeId: document.root.nodeId,
    selector: 'label.border-amber-400 input[type="file"]',
  })
  assert(nodeId, `${page.label} could not resolve file input for ${labelText}`)
  await page.send('DOM.setFileInputFiles', { files: [filePath], nodeId })
}

async function inspectPage(page, appBase) {
  const state = await page.evaluate(`(() => {
    const video = document.querySelector('[data-testid="video-room-media"]')
    return {
      cookieReads: window.__phase8CookieReads || 0,
      fullscreenControl: Boolean(document.querySelector('button[aria-label="全屏播放"]:not(:disabled)')),
      hasIframe: Boolean(document.querySelector('iframe')),
      managedPathLeak: document.body.innerText.includes('private_storage') || document.body.innerText.includes('video_rooms/'),
      mediaError: video?.error?.message || null,
      notice: document.querySelector('main > div > p[role="status"]')?.textContent || null,
      overflow: document.documentElement.scrollWidth - innerWidth,
      pathname: location.pathname,
      // The current room toolbar uses a status span rather than a header element;
      // include all visible status announcements so this contract follows the
      // live accessibility markup instead of the retired layout.
      syncText: Array.from(document.querySelectorAll('[role="status"]'))
        .filter((node) => node.getClientRects().length > 0)
        .map((node) => node.textContent.trim())
        .join(' '),
    }
  })()`)
  const forbidden = page.requests.filter((url) => (
    (!url.startsWith(appBase) && !url.startsWith('data:') && !url.startsWith('blob:'))
    || /private_storage|video_rooms\//i.test(url)
  ))
  assert.equal(state.cookieReads, 0, `${page.label} read document.cookie`)
  assert.equal(state.fullscreenControl, true, `${page.label} has no fullscreen control`)
  assert.equal(state.hasIframe, false, `${page.label} rendered an iframe`)
  assert.equal(state.managedPathLeak, false, `${page.label} leaked a managed path`)
  assert.equal(state.mediaError, null, `${page.label} has a media error`)
  assert.equal(state.notice, null, `${page.label} shows a notice: ${state.notice}`)
  assert(state.overflow <= 1, `${page.label} overflows by ${state.overflow}px`)
  assert.match(state.syncText, /已与服务器同步/)
  assert.deepEqual(forbidden, [], `${page.label} made forbidden requests`)
  assert.deepEqual(page.errors, [], `${page.label} emitted browser errors`)
  return state
}

async function main() {
  assert(fs.existsSync(python), 'backend/.venv is required')
  assert(fs.existsSync(chromeBinary), `Chrome is unavailable: ${chromeBinary}`)
  assert(fs.existsSync(ffmpegBinary), `ffmpeg is unavailable: ${ffmpegBinary}`)
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'blue-album-phase8-'))
  const clients = []
  const processes = []
  const sockets = []

  try {
    const [backendPort, frontendPort, hostDebugPort, memberDebugPort] = await Promise.all([
      freePort(), freePort(), freePort(), freePort(),
    ])
    const appBase = `http://127.0.0.1:${frontendPort}`
    const backendBase = `http://127.0.0.1:${backendPort}`
    const hostDebugBase = `http://127.0.0.1:${hostDebugPort}`
    const memberDebugBase = `http://127.0.0.1:${memberDebugPort}`
    const firstVideoPath = path.join(temporaryRoot, 'fixture-alpha.webm')
    const secondVideoPath = path.join(temporaryRoot, 'fixture-beta.webm')
    await Promise.all([
      run(ffmpegBinary, [
        '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=0x075985:s=640x360:r=12',
        '-t', '90', '-c:v', 'libvpx', '-deadline', 'realtime', '-cpu-used', '8', '-pix_fmt', 'yuv420p', '-an', '-y', firstVideoPath,
      ]),
      run(ffmpegBinary, [
        '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=0x9f1239:s=640x360:r=12',
        '-t', '90', '-c:v', 'libvpx', '-deadline', 'realtime', '-cpu-used', '8', '-pix_fmt', 'yuv420p', '-an', '-y', secondVideoPath,
      ]),
    ])
    const environment = {
      ...process.env,
      ACCESS_TOKEN_EXPIRE_MINUTES: '60',
      CORS_ORIGINS: appBase,
      DATABASE_URL: `sqlite:///${path.join(temporaryRoot, 'phase8.sqlite')}`,
      PRIVATE_STORAGE_DIR: path.join(temporaryRoot, 'private-storage'),
      SECRET_KEY: 'phase8-browser-isolated-secret',
    }

    await run(python, [path.join(root, 'backend', 'run_migrations.py')], { cwd: root, env: environment })
    processes.push(startProcess(python, [
      '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(backendPort), '--log-level', 'warning',
    ], { cwd: path.join(root, 'backend'), env: environment, logPath: path.join(temporaryRoot, 'backend.log') }))
    await waitForUrl(`${backendBase}/api/health`)
    processes.push(startProcess('npm', [
      'run', 'dev', '--', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort',
    ], {
      cwd: path.join(root, 'frontend'),
      env: {
        ...process.env,
        VITE_BACKEND_PROXY_TARGET: backendBase,
        VITE_DEV_HOST: '127.0.0.1',
        VITE_DEV_PORT: String(frontendPort),
      },
      logPath: path.join(temporaryRoot, 'frontend.log'),
    }))
    await waitForUrl(appBase)

    const hostAuth = await registerAndLogin(appBase, 'phase8_host')
    const memberAuth = await registerAndLogin(appBase, 'phase8_member')
    const room = expectOk(await api(appBase, '/api/sync-rooms', {
      body: { control_mode: 'host_only', mode: 'url', room_name: 'Phase 8 Video Browser Room', type: 'video' },
      method: 'POST', token: hostAuth.access_token,
    }), 'create video room')
    expectOk(await api(appBase, `/api/sync-rooms/${room.id}/join`, {
      method: 'POST', token: memberAuth.access_token,
    }), 'member join')
    const first = (await uploadVideo(appBase, room.id, hostAuth.access_token, firstVideoPath, 'Fixture Alpha')).item
    const rejectedPrivateReference = await api(appBase, `/api/video/rooms/${room.id}/items/url`, {
      body: { source_url: 'https://media.example/phase8-remote.webm', title: 'External Reference' },
      method: 'POST', token: hostAuth.access_token,
    })
    assert.equal(rejectedPrivateReference.status, 400)
    assert.match(rejectedPrivateReference.payload.detail, /本机或内网|公共 DNS 无法验证/)
    const subtitle = (await uploadSubtitle(appBase, room.id, first.id, hostAuth.access_token)).subtitle
    expectOk(await api(appBase, `/api/video/rooms/${room.id}/playlist`, {
      body: { item_ids: [first.id] }, method: 'PUT', token: hostAuth.access_token,
    }), 'set initial playlist')
    expectOk(await api(appBase, `/api/video/rooms/${room.id}/items/${first.id}/select`, {
      body: { autoplay: false, expected_version: 0 }, method: 'POST', token: hostAuth.access_token,
    }), 'select first video')

    for (const [label, debugPort] of [['host', hostDebugPort], ['member', memberDebugPort]]) {
      processes.push(startProcess(chromeBinary, [
        '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--mute-audio',
        '--autoplay-policy=no-user-gesture-required', '--no-first-run', '--no-default-browser-check',
        `--remote-debugging-port=${debugPort}`, `--user-data-dir=${path.join(temporaryRoot, `${label}-chrome`)}`, 'about:blank',
      ], { cwd: root, env: process.env, logPath: path.join(temporaryRoot, `${label}-chrome.log`) }))
    }
    const host = new CdpClient(await chromeTarget(hostDebugBase), 'host')
    const member = new CdpClient(await chromeTarget(memberDebugBase), 'member')
    clients.push(host, member)
    await Promise.all([host.connect(), member.connect()])
    await Promise.all([authenticatePage(host, appBase, hostAuth), authenticatePage(member, appBase, memberAuth)])
    await Promise.all([host.setViewport(1440, 1000), member.setViewport(390, 844, true)])
    const roomUrl = `${appBase}/rooms/watch/${room.id}`
    await Promise.all([host.navigate(roomUrl), member.navigate(roomUrl)])
    const readyExpression = `document.querySelector('h1')?.textContent === 'Phase 8 Video Browser Room'
      && document.body.textContent.includes('已与服务器同步')
      && document.querySelector('[data-testid="video-room-media"]')?.readyState >= 1
      && document.querySelector('[data-testid="video-room-media"]')?.duration > 10`
    await Promise.all([host.waitFor(readyExpression, 25000), member.waitFor(readyExpression, 25000)])

    const driftProof = await host.evaluate(`(async () => {
      const module = await import('/src/features/player/roomSyncEngine.js')
      const apply = async (currentTime, targetTime) => {
        const player = { currentTime, isPlaying: true, playbackRate: 1, track: { id: 'fixture' } }
        const adapter = {
          pause() { player.isPlaying = false },
          play() { player.isPlaying = true; return Promise.resolve() },
          seek(value) { player.currentTime = value },
          setPlaybackRate(value) { player.playbackRate = value },
          snapshot() { return { ...player } },
        }
        const result = await module.applyAuthoritativeSnapshot(adapter, {
          media_id: 1,
          playback_rate: 1,
          position: targetTime,
          room_id: 1,
          server_now_ms: 10_000,
          started_at_server_ms: 10_000,
          state: 'playing',
          track_id: 1,
          version: 1,
        }, {
          clearTimer() {},
          clientNowMs: 10_000,
          mediaKind: 'video',
          receivedAtMs: 10_000,
          setTimer() { return 1 },
        })
        return result.correction
      }
      return {
        applied: {
          ignore: await apply(10, 10.1),
          rate: await apply(10, 10.75),
          seek: await apply(10, 12.1),
        },
        ignore: module.classifyDrift(10, 10.749).kind,
        rateAhead: module.classifyDrift(10, 11).kind,
        rateBehind: module.classifyDrift(10, 9).kind,
        seek: module.classifyDrift(10, 15).kind,
      }
    })()`)
    assert.deepEqual(driftProof, {
      applied: { ignore: 'none', rate: 'rate', seek: 'seek' },
      ignore: 'none',
      rateAhead: 'rate',
      rateBehind: 'rate',
      seek: 'seek',
    })

    let detail = expectOk(await api(appBase, `/api/video/rooms/${room.id}`, { token: hostAuth.access_token }), 'initial video detail')
    const firstDetail = detail.session.playlist.find((item) => item.id === first.id)
    assert.match(firstDetail.playback_url, new RegExp(`^/api/video/items/${first.id}/stream\\?access=`))
    assert.match(firstDetail.subtitles[0].src, new RegExp(`^/api/video/subtitles/${subtitle.id}/stream\\?access=`))
    assert(!JSON.stringify(detail).includes(temporaryRoot), 'video detail leaked a managed path')
    detail = await waitForApi(async () => {
      const current = expectOk(await api(appBase, `/api/video/rooms/${room.id}`, { token: hostAuth.access_token }), 'metadata detail')
      const item = current.session.playlist.find((candidate) => candidate.id === first.id)
      return item?.resolution?.width === 640 && item?.resolution?.height === 360 ? current : null
    }, 'browser metadata update')

    const deniedManage = await api(appBase, `/api/video/rooms/${room.id}/items/url`, {
      body: { source_url: 'https://media.example/denied.webm', title: 'Denied' },
      method: 'POST', token: memberAuth.access_token,
    })
    assert.equal(deniedManage.status, 403)
    const hostSocket = await connectRoomSocket(appBase, hostAuth, room.id)
    const memberSocket = await connectRoomSocket(appBase, memberAuth, room.id)
    sockets.push(hostSocket, memberSocket)
    const beforeDenied = detail.snapshot
    const denied = await socketControl(memberSocket, {
      action: 'play', playback_version: beforeDenied.version, room_id: room.id, time: beforeDenied.position,
    }, 'error')
    assert.match(denied.message, /权限/)
    assert.equal(expectOk(await api(appBase, `/api/video/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }), 'after denied').version, beforeDenied.version)

    await click(host, 'button[aria-label^="播放 "]')
    let playing = await waitForApi(async () => {
      const current = expectOk(await api(appBase, `/api/video/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }), 'play snapshot')
      return current.state === 'playing' ? current : null
    }, 'host play')
    await host.waitFor("document.querySelector('[data-testid=\"video-room-media\"]') && !document.querySelector('[data-testid=\"video-room-media\"]')?.paused")
    // A member must explicitly unlock local media once; autoplay policy is
    // intentionally not bypassed by the shared room state.
    await ensureVideoPlaying(member)
    await member.waitFor("document.querySelector('[data-testid=\"video-room-media\"]') && !document.querySelector('[data-testid=\"video-room-media\"]')?.paused")
    await selectValue(host, 'select[aria-label="共享播放速度"]', 1.25)
    playing = await waitForApi(async () => {
      const current = expectOk(await api(appBase, `/api/video/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }), 'rate snapshot')
      return current.playback_rate === 1.25 ? current : null
    }, 'shared playback rate')
    await Promise.all([
      host.waitFor("Number(document.querySelector('[data-testid=\"video-room-media\"]')?.playbackRate) === 1.25"),
      member.waitFor("Number(document.querySelector('[data-testid=\"video-room-media\"]')?.playbackRate) === 1.25"),
    ])
    playing = await socketControl(hostSocket, {
      action: 'seek', playback_version: playing.version, room_id: room.id, time: 4,
    })
    await member.waitFor("Number(document.querySelector('[data-testid=\"video-room-media\"]')?.currentTime) >= 3.7")

    expectOk(await api(appBase, `/api/video/rooms/${room.id}/subtitles/${subtitle.id}/select`, {
      method: 'PUT', token: hostAuth.access_token,
    }), 'select subtitle')
    await Promise.all([
      host.waitFor("document.body.textContent.includes('字幕：中文验收字幕') && document.querySelector('video track')?.default === true"),
      member.waitFor("document.body.textContent.includes('字幕：中文验收字幕') && document.querySelector('video track')?.default === true"),
    ])

    const bufferVisible = waitForSocketEvent(hostSocket, 'video_buffer_status')
    memberSocket.emit('video_buffer_status', { buffering: true, item_id: first.id, room_id: room.id })
    await bufferVisible
    await host.waitFor("document.body.textContent.includes('1 位成员正在缓冲') && document.body.textContent.includes('缓冲中')")
    memberSocket.emit('video_buffer_status', { buffering: false, item_id: first.id, room_id: room.id })
    await host.waitFor("!document.body.textContent.includes('1 位成员正在缓冲')")

    await fill(member, 'input[aria-label="聊天消息"]', 'Phase 8 public video hello')
    await clickText(member, '发送')
    await host.waitFor("document.body.textContent.includes('Phase 8 public video hello')")
    await selectValue(member, 'select[aria-label="消息接收人"]', hostAuth.user.id)
    await fill(member, 'input[aria-label="聊天消息"]', 'Phase 8 private video hello')
    await clickText(member, '发送')
    await host.waitFor("document.body.textContent.includes('Phase 8 private video hello')")

    detail = expectOk(await api(appBase, `/api/video/rooms/${room.id}`, { token: hostAuth.access_token }), 'current video detail')

    const extraTarget = await newTab(memberDebugBase, roomUrl)
    const memberTab = new CdpClient(extraTarget, 'member-tab')
    clients.push(memberTab)
    await memberTab.connect()
    await memberTab.setViewport(1000, 760)
    await memberTab.waitFor("document.querySelector('h1')?.textContent === 'Phase 8 Video Browser Room' && document.body.textContent.includes('已与服务器同步')", 20000)
    await closeTab(memberDebugBase, extraTarget.id)
    memberTab.close()
    await sleep(700)
    const membersAfterTab = expectOk(await api(appBase, `/api/sync-rooms/${room.id}/members`, { token: hostAuth.access_token }), 'members after tab close')
    assert(membersAfterTab.some((item) => item.user_id === memberAuth.user.id && item.is_online !== false), 'closing one tab marked member offline')

    expectOk(await api(appBase, `/api/sync-rooms/${room.id}`, {
      body: { control_mode: 'all_members' }, method: 'PUT', token: hostAuth.access_token,
    }), 'enable member control')
    await member.navigate(roomUrl)
    await member.waitFor("document.body.textContent.includes('全员控制') && document.body.textContent.includes('已与服务器同步')", 20000)
    const memberErrorsBeforeOutage = member.errors.length
    await member.send('Network.emulateNetworkConditions', {
      connectionType: 'none', downloadThroughput: 0, latency: 0, offline: true, uploadThroughput: 0,
    })
    await member.waitFor("document.body.textContent.includes('正在恢复') || document.body.textContent.includes('同步暂时失败')", 10000)
    let outageSnapshot = expectOk(await api(appBase, `/api/video/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }), 'outage baseline')
    outageSnapshot = await socketControl(hostSocket, {
      action: outageSnapshot.state === 'playing' ? 'pause' : 'play',
      playback_version: outageSnapshot.version,
      room_id: room.id,
      time: outageSnapshot.position,
    })
    await member.send('Network.emulateNetworkConditions', {
      connectionType: 'cellular3g', downloadThroughput: 256000, latency: 250, offline: false, uploadThroughput: 128000,
    })
    await member.waitFor("document.body.textContent.includes('已与服务器同步')", 25000)
    // Network errors emitted during the deliberate offline window are
    // expected. Keep all errors from the rest of the scenario strict.
    member.errors.splice(memberErrorsBeforeOutage)
    const staleConflict = await socketControl(memberSocket, {
      action: 'seek', playback_version: outageSnapshot.version - 1, room_id: room.id, time: 1,
    }, 'playback_conflict')
    assert.equal(staleConflict.snapshot.version, outageSnapshot.version)
    await member.navigate(roomUrl)
    await member.waitFor(readyExpression, 25000)
    // Reloading a playing room resets the browser's local autoplay grant;
    // unlock the member tab explicitly before checking shared playback.
    await click(member, 'button[aria-label^="播放 "]')

    let finalSnapshot = await waitForApi(async () => {
      const current = expectOk(await api(appBase, `/api/video/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }), 'final snapshot')
      return current.state === 'playing' ? current : null
    }, 'member playback unlock', 5000).catch(() => null)
    if (!finalSnapshot || finalSnapshot.state !== 'playing') {
      finalSnapshot = expectOk(
        await api(appBase, `/api/video/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }),
        'member unlock retry baseline',
      )
      if (finalSnapshot.state !== 'playing') {
        // If the member's event is still in flight, the host retry may race
        // with it and receive a valid playback conflict. Retry from a fresh
        // snapshot only when the room is still paused.
        try {
          finalSnapshot = await socketControl(hostSocket, {
            action: 'play', playback_version: finalSnapshot.version, room_id: room.id, time: finalSnapshot.position,
          })
        } catch (error) {
          finalSnapshot = await waitForApi(async () => {
            const current = expectOk(await api(appBase, `/api/video/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }), 'final retry snapshot')
            return current.state === 'playing' ? current : null
          }, 'member playback unlock after retry', 5000)
        }
      }
    }
    // The browser timer normally emits this event every five seconds, but a
    // CI scheduler can pause that timer while the page is backgrounded during
    // the preceding reconnect exercise.  Send one explicit valid host
    // heartbeat so this protocol assertion is deterministic; the UI timer is
    // still exercised by the playing-room checks above.
    const heartbeatProof = waitForSocketEvent(hostSocket, 'time_heartbeat', 13_000)
    hostSocket.emit('time_heartbeat', {
      playback_version: finalSnapshot.version,
      position: finalSnapshot.position,
      room_id: room.id,
    })
    await Promise.all([ensureVideoPlaying(host), ensureVideoPlaying(member)])
    const heartbeat = await heartbeatProof
    assert.equal(heartbeat.version, finalSnapshot.version)
    const driftDeadline = Date.now() + 6_000
    let positions = []
    let finalError = Number.POSITIVE_INFINITY
    let authorityError = Number.POSITIVE_INFINITY
    let authorityTarget = 0
    while (Date.now() < driftDeadline) {
      positions = await Promise.all([host, member].map((page) => page.evaluate(`(() => {
        const video = document.querySelector('[data-testid="video-room-media"]')
        return { currentTime: video?.currentTime || 0, playbackRate: video?.playbackRate || 0 }
      })()`)))
      const authoritative = expectOk(
        await api(appBase, `/api/video/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }),
        'authoritative drift snapshot',
      )
      authorityTarget = authoritative.state === 'playing'
        ? authoritative.position
          + Math.max(0, authoritative.server_now_ms - authoritative.started_at_server_ms)
            / 1_000 * authoritative.playback_rate
        : authoritative.position
      finalError = Math.abs(positions[0].currentTime - positions[1].currentTime)
      authorityError = Math.max(...positions.map((item) => Math.abs(item.currentTime - authorityTarget)))
      if (finalError <= 0.6 && authorityError <= 0.6) break
      await sleep(500)
    }
    assert(
      finalError <= 0.6,
      `final video client drift is ${finalError.toFixed(3)}s: ${JSON.stringify(positions)}`,
    )
    assert(
      authorityError <= 0.6,
      `final server authority drift is ${authorityError.toFixed(3)}s from ${authorityTarget.toFixed(3)}s: ${JSON.stringify(positions)}`,
    )

    await Promise.all([
      host.waitFor("document.body.textContent.includes('Fixture Alpha') && document.body.textContent.includes('Phase 8 public video hello')"),
      member.waitFor("document.body.textContent.includes('Fixture Alpha') && document.body.textContent.includes('Phase 8 public video hello')"),
    ])
    const screenshots = [
      await capture(host, 'phase8-video-host-desktop.png'),
      await capture(member, 'phase8-video-member-mobile.png'),
    ]
    const states = await Promise.all([inspectPage(host, appBase), inspectPage(member, appBase)])

    const localFingerprint = localVideoFingerprint(firstVideoPath)
    const localCreated = expectOk(await api(appBase, `/api/video/rooms/${room.id}/items/local`, {
      body: {
        file_size: fs.statSync(firstVideoPath).size,
        filename: path.basename(firstVideoPath),
        fingerprint: localFingerprint,
        title: '本地同步验收视频',
      },
      method: 'POST',
      token: hostAuth.access_token,
    }), 'register local video')
    const beforeLocal = expectOk(await api(appBase, `/api/video/rooms/${room.id}/snapshot`, { token: hostAuth.access_token }), 'before local selection')
    expectOk(await api(appBase, `/api/video/rooms/${room.id}/items/${localCreated.item.id}/select`, {
      body: { autoplay: false, expected_version: beforeLocal.version },
      method: 'POST',
      token: hostAuth.access_token,
    }), 'select local video')
    await Promise.all([
      host.waitFor("document.body.textContent.includes('选择房间要求的本地视频')"),
      member.waitFor("document.body.textContent.includes('选择房间要求的本地视频')"),
    ])

    await selectLocalFile(member, '选择房间要求的本地视频', secondVideoPath)
    await member.waitFor("document.body.textContent.includes('所选文件与房间要求的本地视频不一致')")
    await selectLocalFile(host, '选择房间要求的本地视频', firstVideoPath)
    await selectLocalFile(member, '选择房间要求的本地视频', firstVideoPath)
    await Promise.all([
      host.waitFor("Array.from(document.querySelectorAll('span')).filter((node) => node.textContent.trim() === '本地文件已准备').length >= 2"),
      member.waitFor("Array.from(document.querySelectorAll('span')).filter((node) => node.textContent.trim() === '本地文件已准备').length >= 2"),
    ])
    assert.equal(host.requests.filter((url) => url.includes(`/api/video/rooms/${room.id}/upload`)).length, 0, 'host uploaded local file content')
    assert.equal(member.requests.filter((url) => url.includes(`/api/video/rooms/${room.id}/upload`)).length, 0, 'member uploaded local file content')

    await member.navigate(roomUrl)
    await member.waitFor("document.body.textContent.includes('选择房间要求的本地视频') && document.body.textContent.includes('等待选择本地文件')", 20000)
    await selectLocalFile(member, '选择房间要求的本地视频', firstVideoPath)
    await member.waitFor("document.body.textContent.includes('本地视频已准备，可以同步播放')")
    const localDetail = expectOk(await api(appBase, `/api/video/rooms/${room.id}`, { token: hostAuth.access_token }), 'local detail')
    assert.equal(localDetail.session.current_source, 'legacy_local')
    assert.equal(localDetail.session.required_local_fingerprint, localFingerprint)
    assert(!JSON.stringify(localDetail).includes(temporaryRoot), 'local video detail leaked a local path')

    console.log(JSON.stringify({
      driftProof,
      privateReferenceRejected: rejectedPrivateReference.payload.detail,
      finalAuthorityErrorSeconds: Number(authorityError.toFixed(3)),
      finalAuthorityTargetSeconds: Number(authorityTarget.toFixed(3)),
      finalErrorSeconds: Number(finalError.toFixed(3)),
      heartbeat,
      metadata: detail.session.playlist.find((item) => item.id === first.id)?.resolution,
      localSync: {
        fingerprint: localFingerprint,
        itemId: localCreated.item.id,
        refreshedMemberReselected: true,
        uploadedContent: false,
      },
      positions,
      roomId: room.id,
      screenshots,
      states,
      subtitleId: subtitle.id,
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
    fs.rmSync(temporaryRoot, { force: true, recursive: true })
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
