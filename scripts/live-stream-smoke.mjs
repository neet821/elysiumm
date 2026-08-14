import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'


const root = path.resolve(import.meta.dirname, '..')
const python = path.join(root, 'backend', '.venv', 'bin', 'python')
const chromeBinary = process.env.CHROME_BINARY || '/usr/bin/google-chrome-stable'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-live-browser'
const password = 'LiveBrowser2026!'
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))


class CdpClient {
  constructor(target, label, downloadPath) {
    this.errors = []
    this.failedResponses = []
    this.label = label
    this.nextId = 1
    this.pending = new Map()
    this.requests = []
    this.target = target
    this.downloadPath = downloadPath
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
        this.errors.push(message.params.args.map((entry) => entry.value || entry.description).join(' '))
      }
      if (message.method === 'Network.requestWillBeSent') {
        this.requests.push(message.params.request.url)
      }
      if (message.method === 'Network.responseReceived' && message.params.response.status >= 400) {
        this.failedResponses.push({
          status: message.params.response.status,
          url: message.params.response.url,
        })
      }
    })
    await new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, { once: true })
      this.socket.addEventListener('error', reject, { once: true })
    })
    await this.send('Page.enable')
    await this.send('Runtime.enable')
    await this.send('Network.enable')
    await this.send('Browser.setDownloadBehavior', {
      behavior: 'allow',
      downloadPath: this.downloadPath,
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

  async waitFor(expression, timeout = 20000) {
    const deadline = Date.now() + timeout
    let lastError
    while (Date.now() < deadline) {
      try {
        if (await this.evaluate(expression)) return
      } catch (error) {
        lastError = error
      }
      await sleep(100)
    }
    const state = await this.evaluate(`({
      url: location.href,
      text: document.body?.innerText?.slice(0, 1600) || '',
    })`)
    throw new Error(`${this.label} timed out: ${expression}${lastError ? ` (${lastError.message})` : ''}\n${JSON.stringify(state)}`)
  }

  async navigate(url) {
    await this.send('Page.navigate', { url })
    await this.waitFor("document.readyState === 'complete' && Boolean(document.querySelector('#root > *'))")
  }

  async setViewport(width, height) {
    await this.send('Emulation.setDeviceMetricsOverride', {
      deviceScaleFactor: 1,
      height,
      mobile: width <= 430,
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
  let lastError
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
  await Promise.race([new Promise((resolve) => child.once('exit', resolve)), sleep(3000)])
  if (child.exitCode === null) child.kill('SIGKILL')
}

async function api(appBase, pathname, {
  body,
  form,
  headers: extraHeaders = {},
  method = 'GET',
  token,
} = {}) {
  const headers = { ...extraHeaders }
  let requestBody
  if (token) headers.Authorization = `Bearer ${token}`
  if (form) requestBody = form
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(body)
  }
  const response = await fetch(`${appBase}${pathname}`, {
    body: requestBody,
    headers,
    method,
  })
  const text = await response.text()
  let payload = text
  try { payload = text ? JSON.parse(text) : null } catch { /* Keep file or text responses as-is. */ }
  return { ok: response.ok, payload, status: response.status }
}

function expectOk(result, label) {
  assert(result.ok, `${label} failed (${result.status}): ${JSON.stringify(result.payload)}`)
  return result.payload
}

async function register(appBase, username) {
  return expectOk(await api(appBase, '/api/users/register', {
    body: { email: `${username}@example.com`, password, username },
    method: 'POST',
  }), `register ${username}`)
}

async function login(appBase, username) {
  return expectOk(await api(appBase, '/api/auth/login', {
    form: new URLSearchParams({ password, username }),
    method: 'POST',
  }), `login ${username}`)
}

async function chromeTarget(debugBase) {
  await waitForUrl(`${debugBase}/json/version`)
  const targets = await fetch(`${debugBase}/json/list`).then((response) => response.json())
  const target = targets.find((candidate) => candidate.type === 'page')
  assert(target?.webSocketDebuggerUrl, `No Chrome page target at ${debugBase}`)
  return target
}

async function authenticatePage(page, appBase, auth) {
  await page.navigate(`${appBase}/login`)
  await page.evaluate(`(() => {
    localStorage.setItem('token', ${JSON.stringify(auth.access_token)})
    localStorage.setItem('refresh_token', ${JSON.stringify(auth.refresh_token)})
    localStorage.setItem('user', ${JSON.stringify(JSON.stringify(auth.user))})
  })()`)
}

async function clickAria(page, label) {
  const clicked = await page.evaluate(`(() => {
    const element = document.querySelector('[aria-label=${JSON.stringify(label)}]')
    if (!element || element.disabled) return false
    element.click()
    return true
  })()`)
  assert(clicked, `${page.label} could not click ${label}`)
}

async function clickText(page, text, selector = 'button') {
  const clicked = await page.evaluate(`(() => {
    const element = Array.from(document.querySelectorAll(${JSON.stringify(selector)}))
      .find((candidate) => candidate.textContent.trim().includes(${JSON.stringify(text)}))
    if (!element || element.disabled) return false
    element.click()
    return true
  })()`)
  assert(clicked, `${page.label} could not click ${text}`)
}

async function setControl(page, labelText, value) {
  const changed = await page.evaluate(`(() => {
    const label = Array.from(document.querySelectorAll('label')).find((candidate) => (
      candidate.textContent.replace('*', '').trim().startsWith(${JSON.stringify(labelText)})
    ))
    const control = (label?.htmlFor ? document.getElementById(label.htmlFor) : null)
      || label?.querySelector('input, select, textarea')
    if (!control) return false
    const prototype = control instanceof HTMLSelectElement
      ? HTMLSelectElement.prototype
      : control instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(control, ${JSON.stringify(String(value))})
    control.dispatchEvent(new Event('input', { bubbles: true }))
    control.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  })()`)
  assert(changed, `${page.label} missing control ${labelText}`)
}

async function assertViewport(page, width, height) {
  await page.setViewport(width, height)
  await sleep(150)
  const metrics = await page.evaluate(`({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  })`)
  assert(metrics.scroll <= metrics.client + 1, `${page.label} overflows at ${width}x${height}: ${JSON.stringify(metrics)}`)
}

function assertClean(page, allowedFailures = []) {
  const failures = page.failedResponses.filter((entry) => (
    !allowedFailures.some((allowed) => entry.status === allowed.status && entry.url.includes(allowed.path))
    && !entry.url.endsWith('/favicon.ico')
  ))
  assert.deepEqual(page.errors, [], `${page.label} console errors: ${JSON.stringify(page.errors)}`)
  assert.deepEqual(failures, [], `${page.label} failed responses: ${JSON.stringify(failures)}`)
}

async function startFakeMediaServer(port) {
  const state = { online: false, recording: true }
  const server = http.createServer(async (request, response) => {
    const requestUrl = new URL(request.url, `http://127.0.0.1:${port}`)
    if (
      request.method === 'GET'
      && requestUrl.pathname === '/v3/config/paths/get/live/stream'
    ) {
      response.setHeader('Content-Type', 'application/json')
      response.end(JSON.stringify({ record: state.recording }))
      return
    }
    if (request.method === 'GET' && requestUrl.pathname === '/v3/paths/get/live/stream') {
      if (!state.online) {
        response.writeHead(404).end()
        return
      }
      response.setHeader('Content-Type', 'application/json')
      response.end(JSON.stringify({
        bitRate: 4200000,
        source: { id: 'browser-publisher' },
        tracks2: [
          { bitrate: 4000000, codec: 'H264', fps: 30, height: 1080, width: 1920 },
          { bitrate: 192000, codec: 'MPEG4Audio' },
        ],
      }))
      return
    }
    if (
      request.method === 'PATCH'
      && requestUrl.pathname === '/v3/config/paths/patch/live/stream'
    ) {
      let body = ''
      for await (const chunk of request) body += chunk
      const payload = JSON.parse(body)
      assert.equal(typeof payload.record, 'boolean')
      state.recording = payload.record
      response.setHeader('Content-Type', 'application/json')
      response.end('{}')
      return
    }
    if (
      request.method === 'POST'
      && requestUrl.pathname === '/v3/paths/kick/live/stream'
    ) {
      state.online = false
      response.setHeader('Content-Type', 'application/json')
      response.end('{}')
      return
    }
    if (request.method === 'GET' && requestUrl.pathname.endsWith('/index.m3u8')) {
      response.setHeader('Content-Type', 'application/vnd.apple.mpegurl')
      response.end([
        '#EXTM3U',
        '#EXT-X-VERSION:7',
        '#EXT-X-TARGETDURATION:2',
        '#EXT-X-MEDIA-SEQUENCE:1',
        '#EXT-X-MAP:URI="init.mp4"',
        '#EXTINF:2.0,',
        'segment.m4s',
        '',
      ].join('\n'))
      return
    }
    if (request.method === 'GET' && /\.(mp4|m4s)$/.test(requestUrl.pathname)) {
      response.setHeader('Content-Type', 'video/mp4')
      response.end(Buffer.from([0, 0, 0, 24, 102, 116, 121, 112, 105, 115, 111, 109]))
      return
    }
    response.writeHead(404).end()
  })
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(port, '127.0.0.1', resolve)
  })
  return { server, state }
}


async function main() {
  assert(fs.existsSync(python), 'backend/.venv is required')
  assert(fs.existsSync(chromeBinary), `Chrome is unavailable: ${chromeBinary}`)
  fs.rmSync(screenshotDir, { recursive: true, force: true })
  fs.mkdirSync(screenshotDir, { recursive: true })
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'blue-album-live-'))
  const clients = []
  const processes = []
  let media

  try {
    const ports = await Promise.all(Array.from({ length: 7 }, () => freePort()))
    const [
      backendPort,
      frontendPort,
      mediaPort,
      adminDebugPort,
      allowedDebugPort,
      deniedDebugPort,
      guestDebugPort,
    ] = ports
    const appBase = `http://127.0.0.1:${frontendPort}`
    const backendBase = `http://127.0.0.1:${backendPort}`
    const recordingRoot = path.join(temporaryRoot, 'recordings')
    fs.mkdirSync(recordingRoot, { recursive: true })
    media = await startFakeMediaServer(mediaPort)
    const environment = {
      ...process.env,
      ACCESS_TOKEN_EXPIRE_MINUTES: '60',
      CORS_ORIGINS: appBase,
      DATABASE_URL: `sqlite:///${path.join(temporaryRoot, 'live.sqlite')}`,
      LIVE_COOKIE_SECURE: '0',
      LIVE_DISK_RESERVE_BYTES: '0',
      LIVE_MEDIAMTX_API_URL: `http://127.0.0.1:${mediaPort}`,
      LIVE_OFFLINE_GRACE_SECONDS: '1',
      LIVE_PUBLIC_BASE_URL: appBase,
      LIVE_RECORDING_ROOT: recordingRoot,
      SECRET_KEY: 'live-browser-isolated-secret',
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
        VITE_LIVE_MEDIA_PROXY_TARGET: `http://127.0.0.1:${mediaPort}`,
      },
      logPath: path.join(temporaryRoot, 'frontend.log'),
    }))
    await waitForUrl(appBase)

    const initialStatus = expectOk(await api(appBase, '/api/live/status'), 'initial live status')
    assert.equal(initialStatus.status, 'waiting')
    await register(appBase, 'live_admin')
    await register(appBase, 'live_allowed')
    await register(appBase, 'live_denied')
    await run(python, ['-c', [
      'import models',
      'from database import SessionLocal',
      'db = SessionLocal()',
      "admin = db.query(models.User).filter(models.User.username == 'live_admin').one()",
      "admin.role = 'admin'",
      'db.commit()',
      'db.close()',
    ].join('; ')], { cwd: path.join(root, 'backend'), env: environment })
    const adminAuth = await login(appBase, 'live_admin')
    const allowedAuth = await login(appBase, 'live_allowed')
    const deniedAuth = await login(appBase, 'live_denied')

    media.state.online = true
    await run(python, ['-c', 'from live_reconcile_task import run_live_reconcile_once; run_live_reconcile_once()'], {
      cwd: path.join(root, 'backend'),
      env: environment,
    })
    assert.equal(expectOk(await api(appBase, '/api/live/status'), 'online live status').status, 'live')

    const users = expectOk(await api(appBase, '/api/admin/users', { token: adminAuth.access_token }), 'admin users')
    const allowedUser = users.find((entry) => entry.username === 'live_allowed')
    assert(allowedUser, 'allowed user missing')
    let settings = expectOk(await api(appBase, '/api/admin/live/settings', { token: adminAuth.access_token }), 'live settings')
    settings = expectOk(await api(appBase, '/api/admin/live/settings', {
      body: {
        access_mode: 'invite',
        cover_url: null,
        description: '浏览器验收直播',
        recording_enabled: true,
        revision: settings.revision,
        title: 'Blue Album 验收直播',
        viewing_enabled: true,
      },
      method: 'PUT',
      token: adminAuth.access_token,
    }), 'set invite mode')
    const invite = expectOk(await api(appBase, '/api/admin/live/invites', {
      body: { expires_in_hours: 24 },
      method: 'POST',
      token: adminAuth.access_token,
    }), 'create invite')

    const browserConfigs = [
      ['admin', adminDebugPort],
      ['allowed', allowedDebugPort],
      ['denied', deniedDebugPort],
      ['guest', guestDebugPort],
    ]
    for (const [label, debugPort] of browserConfigs) {
      processes.push(startProcess(chromeBinary, [
        '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
        '--no-first-run', '--no-default-browser-check', `--remote-debugging-port=${debugPort}`,
        `--user-data-dir=${path.join(temporaryRoot, `${label}-chrome`)}`, 'about:blank',
      ], { cwd: root, env: process.env, logPath: path.join(temporaryRoot, `${label}-chrome.log`) }))
    }
    const downloadRoot = path.join(temporaryRoot, 'downloads')
    fs.mkdirSync(downloadRoot, { recursive: true })
    const pages = {}
    for (const [label, debugPort] of browserConfigs) {
      pages[label] = new CdpClient(
        await chromeTarget(`http://127.0.0.1:${debugPort}`),
        label,
        downloadRoot,
      )
      clients.push(pages[label])
      await pages[label].connect()
    }
    await Promise.all([
      authenticatePage(pages.admin, appBase, adminAuth),
      authenticatePage(pages.allowed, appBase, allowedAuth),
      authenticatePage(pages.denied, appBase, deniedAuth),
    ])
    await pages.guest.send('Network.setExtraHTTPHeaders', {
      headers: { 'X-Real-IP': '8.8.8.8' },
    })

    await pages.admin.navigate(`${appBase}/account/admin/services/live`)
    await pages.admin.waitFor("document.body.innerText.includes('直播管理') && document.body.innerText.includes('OBS 推流')")
    await pages.admin.waitFor("document.body.innerText.includes('自动录制直播')")
    await clickText(pages.admin, '自动录制直播', 'label')
    await clickText(pages.admin, '保存设置')
    for (let attempt = 0; attempt < 30 && media.state.recording; attempt += 1) await sleep(100)
    assert.equal(media.state.recording, false, 'disabling automatic recording must update MediaMTX immediately')
    settings = expectOk(await api(appBase, '/api/admin/live/settings', {
      token: adminAuth.access_token,
    }), 'disabled recording settings')
    assert.equal(settings.recording_enabled, false)
    await clickText(pages.admin, '自动录制直播', 'label')
    await clickText(pages.admin, '保存设置')
    for (let attempt = 0; attempt < 30 && !media.state.recording; attempt += 1) await sleep(100)
    assert.equal(media.state.recording, true, 'enabling automatic recording must update MediaMTX immediately')
    settings = expectOk(await api(appBase, '/api/admin/live/settings', {
      token: adminAuth.access_token,
    }), 'enabled recording settings')
    assert.equal(settings.recording_enabled, true)
    await pages.guest.navigate(`${appBase}/live?invite=${encodeURIComponent(invite.invite_token)}`)
    await pages.guest.waitFor("document.body.innerText.includes('正在直播') && Boolean(document.querySelector('video[aria-label=\"直播播放器\"]'))")
    assert.equal(await pages.guest.evaluate('location.search'), '')
    assert.equal(await pages.guest.evaluate(`document.body.innerText.includes(${JSON.stringify(invite.invite_token)})`), false)
    pages.guest.requests.length = 0
    await sleep(1200)
    const heartbeatStatus = await pages.guest.evaluate(`fetch('/api/live/session/heartbeat', {
      method: 'POST',
      credentials: 'include',
    }).then((response) => response.status)`)
    assert.equal(heartbeatStatus, 200)

    const audience = expectOk(await api(appBase, '/api/admin/live/audience', {
      token: adminAuth.access_token,
    }), 'live audience')
    const guestViewer = audience.find((entry) => entry.ip_address === '8.8.8.8')
    assert(guestViewer, `guest IP missing: ${JSON.stringify(audience)}`)
    assert.equal(guestViewer.device_type, 'computer')
    assert.match(guestViewer.browser, /Chrome/)
    assert(guestViewer.watched_seconds >= 1)
    await clickAria(pages.admin, '刷新直播管理信息')
    await pages.admin.waitFor("document.body.innerText.includes('8.8.8.8') && document.body.innerText.includes('Chrome')")

    settings = expectOk(await api(appBase, '/api/admin/live/settings', {
      body: {
        access_mode: 'allowlist',
        cover_url: null,
        description: settings.description,
        recording_enabled: settings.recording_enabled,
        revision: settings.revision,
        title: settings.title,
        viewing_enabled: true,
      },
      method: 'PUT',
      token: adminAuth.access_token,
    }), 'set allowlist mode')
    expectOk(await api(appBase, '/api/admin/live/allowed-users', {
      body: { user_ids: [allowedUser.id] },
      method: 'PUT',
      token: adminAuth.access_token,
    }), 'set allowed users')
    await pages.allowed.navigate(`${appBase}/live`)
    await pages.allowed.waitFor("document.body.innerText.includes('正在直播')")
    await pages.denied.navigate(`${appBase}/live`)
    await pages.denied.waitFor("document.body.innerText.includes('你没有观看权限')")

    settings = expectOk(await api(appBase, '/api/admin/live/settings', {
      body: {
        access_mode: 'invite',
        cover_url: null,
        description: settings.description,
        recording_enabled: settings.recording_enabled,
        revision: settings.revision,
        title: settings.title,
        viewing_enabled: true,
      },
      method: 'PUT',
      token: adminAuth.access_token,
    }), 'restore invite mode')
    expectOk(await api(appBase, `/api/admin/live/invites/${invite.id}/revoke`, {
      method: 'POST',
      token: adminAuth.access_token,
    }), 'revoke invite')
    const revokedStatus = await pages.guest.evaluate(`fetch('/api/live/authorize-media', {
      credentials: 'include',
    }).then((response) => response.status)`)
    assert.equal(revokedStatus, 403)

    const recordingPath = path.join(recordingRoot, '2026-07-28', 'browser-recording.mp4')
    fs.mkdirSync(path.dirname(recordingPath), { recursive: true })
    fs.writeFileSync(recordingPath, Buffer.from('isolated browser recording'))
    expectOk(await api(backendBase, '/api/internal/live/recording-complete', {
      body: { absolute_path: recordingPath, duration_seconds: 42 },
      method: 'POST',
    }), 'index recording')
    await pages.admin.navigate(`${appBase}/account/admin/services/live`)
    await pages.admin.waitFor("document.body.innerText.includes('browser-recording.mp4')")
    await clickAria(pages.admin, '播放录像 browser-recording.mp4')
    await pages.admin.waitFor("Boolean(document.querySelector('video[aria-label=\"播放录像 browser-recording.mp4\"][src^=\"blob:\"]'))")
    await clickText(pages.admin, '关闭')
    await clickAria(pages.admin, '下载录像 browser-recording.mp4')
    await pages.admin.waitFor("!Array.from(document.querySelectorAll('button')).some((button) => button.disabled)")
    await clickAria(pages.admin, '改名录像 browser-recording.mp4')
    await setControl(pages.admin, '录像名称', '验收录像.mp4')
    await clickText(pages.admin, '保存名称')
    await pages.admin.waitFor("document.body.innerText.includes('验收录像.mp4')")

    await assertViewport(pages.admin, 1366, 768)
    await assertViewport(pages.admin, 360, 800)
    await assertViewport(pages.guest, 1366, 768)
    await assertViewport(pages.guest, 360, 800)
    const forbiddenText = [invite.invite_token, recordingRoot, `127.0.0.1:${mediaPort}`]
    for (const page of Object.values(pages)) {
      const snapshot = await page.evaluate(`({
        body: document.body.innerText,
        href: location.href,
        storage: JSON.stringify(localStorage),
      })`)
      for (const secret of forbiddenText) {
        assert(!JSON.stringify(snapshot).includes(secret), `${page.label} exposed private value`)
      }
    }

    await clickAria(pages.admin, '删除录像 验收录像.mp4')
    await clickText(pages.admin, '确认删除')
    await pages.admin.waitFor("!document.body.innerText.includes('验收录像.mp4')")
    assert.equal(fs.existsSync(recordingPath), false)

    media.state.online = false
    await run(python, ['-c', 'from live_reconcile_task import run_live_reconcile_once; run_live_reconcile_once()'], {
      cwd: path.join(root, 'backend'),
      env: environment,
    })
    await sleep(1100)
    await run(python, ['-c', 'from live_reconcile_task import run_live_reconcile_once; run_live_reconcile_once()'], {
      cwd: path.join(root, 'backend'),
      env: environment,
    })
    await pages.guest.navigate(`${appBase}/live`)
    await pages.guest.waitFor("document.body.innerText.includes('直播已结束') && !document.querySelector('video')")

    assertClean(pages.admin)
    assertClean(pages.allowed, [
      { path: '/api/live/messages', status: 403 },
      { path: '/api/live/messages', status: 409 },
    ])
    assertClean(pages.denied, [{ path: '/api/live/session', status: 403 }])
    assertClean(pages.guest, [
      { path: '/api/live/authorize-media', status: 403 },
      { path: '/api/live/messages', status: 403 },
      { path: '/api/live/messages', status: 409 },
    ])
    console.log(JSON.stringify({
      automaticRecording: 'disabled-enabled',
      audience: {
        browser: guestViewer.browser,
        device: guestViewer.device_type,
        ip: guestViewer.ip_address,
        watched_seconds: guestViewer.watched_seconds,
      },
      modes: ['public-ready', 'allowlist', 'invite'],
      recording: 'previewed-downloaded-renamed-deleted',
      viewports: ['1366x768', '360x800'],
    }, null, 2))
    console.log('Blue Album live streaming smoke passed')
  } finally {
    for (const client of clients) client.close()
    for (const child of processes.reverse()) await stopProcess(child)
    if (media?.server) await new Promise((resolve) => media.server.close(resolve))
    if (process.env.BLUE_ALBUM_KEEP_TEMP) {
      console.error(`Preserved live browser logs at ${temporaryRoot}`)
    } else {
      fs.rmSync(temporaryRoot, { recursive: true, force: true })
    }
  }
}


main().catch((error) => {
  console.error(error.stack || error)
  process.exitCode = 1
})
