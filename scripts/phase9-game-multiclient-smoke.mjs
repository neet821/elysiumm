import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'


const root = path.resolve(import.meta.dirname, '..')
const python = path.join(root, 'backend', '.venv', 'bin', 'python')
const chromeBinary = process.env.CHROME_BINARY || '/usr/bin/google-chrome-stable'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-phase9-game-browser'
const password = 'Phase9Browser2026!'
const privatePassword = 'PrivateGame2026!'
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))


class CdpClient {
  constructor(target, label) {
    this.errors = []
    this.failedResponses = []
    this.label = label
    this.nextId = 1
    this.pending = new Map()
    this.requests = []
    this.target = target
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
      if (message.method === 'Network.responseReceived' && message.params.response.status >= 400) {
        this.failedResponses.push({ status: message.params.response.status, url: message.params.response.url })
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
        window.__phase9CookieReads = 0
        if (descriptor?.configurable) {
          Object.defineProperty(Document.prototype, 'cookie', {
            configurable: true,
            get() { window.__phase9CookieReads += 1; return descriptor.get.call(this) },
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
    let pageState = null
    try {
      pageState = await this.evaluate(`({ url: location.href, text: document.body?.innerText?.slice(0, 1200) || '' })`)
    } catch {
      // The original timeout remains the useful error when the page itself is unavailable.
    }
    throw new Error(`${this.label} timed out: ${expression}${lastError ? ` (${lastError.message})` : ''}${pageState ? `\n${JSON.stringify(pageState)}` : ''}${this.failedResponses.length ? `\nfailed responses: ${JSON.stringify(this.failedResponses)}` : ''}`)
  }

  async navigate(url) {
    await this.send('Page.navigate', { url })
    await this.waitFor("document.readyState === 'complete' && Boolean(document.querySelector('#root > *'))", 20000)
  }

  async reload() {
    await this.send('Page.reload', { ignoreCache: true })
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
  try { payload = text ? JSON.parse(text) : null } catch { /* Keep plain text. */ }
  return { ok: response.ok, payload, status: response.status }
}

function expectOk(result, label) {
  assert(result.ok, `${label} failed (${result.status}): ${JSON.stringify(result.payload)}`)
  return result.payload
}

async function waitForApi(check, label, timeout = 15000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const value = await check()
    if (value) return value
    await sleep(120)
  }
  throw new Error(`Timed out waiting for ${label}`)
}

async function registerAndLogin(appBase, username) {
  expectOk(await api(appBase, '/api/users/register', {
    body: { email: `${username}@example.com`, password, username },
    method: 'POST',
  }), `register ${username}`)
  const form = new URLSearchParams({ password, username })
  return expectOk(await api(appBase, '/api/auth/login', { form, method: 'POST' }), `login ${username}`)
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

async function clickAria(page, label) {
  const state = await page.evaluate(`(() => {
    const element = document.querySelector('[aria-label=${JSON.stringify(label)}]')
    if (!element) return { found: false }
    if (element.disabled) return { disabled: true, found: true }
    element.click()
    return { disabled: false, found: true }
  })()`)
  assert(state.found, `${page.label} missing aria label ${label}`)
  assert.equal(state.disabled, false, `${page.label} disabled aria label ${label}`)
}

async function assertAriaDisabled(page, label) {
  const disabled = await page.evaluate(`document.querySelector('[aria-label=${JSON.stringify(label)}]')?.disabled`)
  assert.equal(disabled, true, `${page.label} should disable ${label}`)
}

async function setControl(page, labelText, value) {
  const changed = await page.evaluate(`(async () => {
    const label = Array.from(document.querySelectorAll('label')).find((candidate) => {
      const ownText = Array.from(candidate.childNodes)
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => node.textContent.trim()).join(' ')
      return ownText === ${JSON.stringify(labelText)}
    })
    const control = label?.querySelector('input, select, textarea')
      || (label?.htmlFor ? document.getElementById(label.htmlFor) : null)
    if (!control) return false
    if (control instanceof HTMLInputElement && control.type === 'checkbox') {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'checked').set.call(control, Boolean(${JSON.stringify(value)}))
    } else {
      const prototype = control instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : control instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(prototype, 'value').set.call(control, ${JSON.stringify(String(value))})
    }
    control.dispatchEvent(new Event('input', { bubbles: true }))
    control.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    return true
  })()`)
  assert(changed, `${page.label} missing control ${labelText}`)
}

async function capture(page, filename) {
  fs.mkdirSync(screenshotDir, { recursive: true })
  const shot = await page.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
  const output = path.join(screenshotDir, filename)
  fs.writeFileSync(output, Buffer.from(shot.data, 'base64'))
  return output
}

async function roomDetail(appBase, roomId, token) {
  return expectOk(await api(appBase, `/api/games/rooms/${roomId}`, { token }), `room ${roomId}`)
}

async function waitRoomVersion(appBase, roomId, token, version) {
  return waitForApi(async () => {
    const room = await roomDetail(appBase, roomId, token)
    return room.version >= version ? room : null
  }, `room ${roomId} version ${version}`)
}

async function readyAndStart(appBase, room, hostAuth, guestAuth) {
  const hostReady = expectOk(await api(appBase, `/api/games/rooms/${room.id}/ready`, {
    body: { expected_room_version: room.room_version, ready: true },
    method: 'POST', token: hostAuth.access_token,
  }), 'host ready')
  const guestReady = expectOk(await api(appBase, `/api/games/rooms/${room.id}/ready`, {
    body: { expected_room_version: hostReady.room_version, ready: true },
    method: 'POST', token: guestAuth.access_token,
  }), 'guest ready')
  return expectOk(await api(appBase, `/api/games/rooms/${room.id}/start`, {
    body: { expected_room_version: guestReady.room_version },
    method: 'POST', token: hostAuth.access_token,
  }), 'start room')
}

async function createStartedRoom(appBase, hostAuth, guestAuth, name, timeout = 90) {
  let room = expectOk(await api(appBase, '/api/games/rooms', {
    body: {
      allow_spectators: true,
      game_slug: 'tic-tac-toe',
      name,
      password: null,
      settings: { turn_timeout_seconds: timeout },
      visibility: 'public',
    },
    method: 'POST', token: hostAuth.access_token,
  }), `create ${name}`)
  room = expectOk(await api(appBase, `/api/games/rooms/${room.id}/join`, {
    body: { role: 'player' }, method: 'POST', token: guestAuth.access_token,
  }), `join ${name}`)
  return readyAndStart(appBase, room, hostAuth, guestAuth)
}

async function enterByCode(page, appBase, roomCode, { invite = '', joinPassword = '', role }) {
  await page.navigate(`${appBase}/games`)
  await page.waitFor("document.body.textContent.includes('桌游大厅') && Boolean(document.querySelector('option[value=\"tic-tac-toe\"]'))")
  await setControl(page, '房间号', roomCode)
  await setControl(page, '密码（如有）', joinPassword)
  await setControl(page, '邀请码（如有）', invite)
  await setControl(page, '加入身份', role)
  const values = await page.evaluate(`Array.from(document.querySelector('.game-code-form').elements).map((element) => element.value)`)
  assert.deepEqual(values.slice(0, 4), [roomCode, joinPassword, invite, role], `${page.label} code entry did not settle`)
  await clickText(page, '按房间号加入')
}

async function loadReplay(page) {
  await page.waitFor("Array.from(document.querySelectorAll('button')).some((button) => button.textContent.includes('载入回放') && !button.disabled)")
  await clickText(page, '载入回放')
  await page.waitFor("document.body.textContent.includes('完整性已验证')", 15000)
  const last = await page.evaluate(`Array.from(document.querySelectorAll('button')).some((button) => button.getAttribute('aria-label') === '最后一步')`)
  if (last) await clickAria(page, '最后一步')
}

async function inspectPage(page, appBase, forbiddenValues = []) {
  const state = await page.evaluate(`(() => ({
    cookieReads: window.__phase9CookieReads || 0,
    hasIframe: Boolean(document.querySelector('iframe')),
    leak: /password_hash|state_hash|state_json|frame_hash|private_by_user|game_state/i.test(document.documentElement.innerHTML),
    overflow: document.documentElement.scrollWidth - innerWidth,
    pathname: location.pathname,
    text: document.body.innerText,
  }))()`)
  const websocketBase = appBase.replace(/^http/, 'ws')
  const forbiddenRequests = page.requests.filter((url) => (
    !url.startsWith(appBase)
    && !url.startsWith(websocketBase)
    && !url.startsWith('data:')
    && !url.startsWith('blob:')
  ))
  assert.equal(state.cookieReads, 0, `${page.label} read document.cookie`)
  assert.equal(state.hasIframe, false, `${page.label} rendered an iframe`)
  assert.equal(state.leak, false, `${page.label} exposed an internal game field`)
  assert(!state.text.includes('操作过于频繁'), `${page.label} hit the realtime rate limit`)
  assert(state.overflow <= 1, `${page.label} overflows by ${state.overflow}px`)
  for (const value of forbiddenValues.filter(Boolean)) {
    assert(!state.text.includes(value), `${page.label} exposed secret ${value}`)
  }
  assert.deepEqual(forbiddenRequests, [], `${page.label} made forbidden requests`)
  assert.deepEqual(page.errors, [], `${page.label} emitted browser errors`)
  return state
}


async function main() {
  assert(fs.existsSync(python), 'backend/.venv is required')
  assert(fs.existsSync(chromeBinary), `Chrome is unavailable: ${chromeBinary}`)
  fs.rmSync(screenshotDir, { recursive: true, force: true })
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'blue-album-phase9-'))
  const clients = []
  const processes = []

  try {
    const [backendPort, frontendPort, hostDebugPort, guestDebugPort, watcherDebugPort] = await Promise.all([
      freePort(), freePort(), freePort(), freePort(), freePort(),
    ])
    const appBase = `http://127.0.0.1:${frontendPort}`
    const backendBase = `http://127.0.0.1:${backendPort}`
    const debug = {
      guest: `http://127.0.0.1:${guestDebugPort}`,
      host: `http://127.0.0.1:${hostDebugPort}`,
      watcher: `http://127.0.0.1:${watcherDebugPort}`,
    }
    const environment = {
      ...process.env,
      ACCESS_TOKEN_EXPIRE_MINUTES: '60',
      CORS_ORIGINS: appBase,
      DATABASE_URL: `sqlite:///${path.join(temporaryRoot, 'phase9.sqlite')}`,
      SECRET_KEY: 'phase9-browser-isolated-secret',
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

    const hostAuth = await registerAndLogin(appBase, 'phase9_host')
    const guestAuth = await registerAndLogin(appBase, 'phase9_guest')
    const watcherAuth = await registerAndLogin(appBase, 'phase9_watcher')

    for (const [label, debugPort] of [
      ['host', hostDebugPort], ['guest', guestDebugPort], ['watcher', watcherDebugPort],
    ]) {
      processes.push(startProcess(chromeBinary, [
        '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
        '--no-first-run', '--no-default-browser-check', `--remote-debugging-port=${debugPort}`,
        `--user-data-dir=${path.join(temporaryRoot, `${label}-chrome`)}`, 'about:blank',
      ], { cwd: root, env: process.env, logPath: path.join(temporaryRoot, `${label}-chrome.log`) }))
    }
    const host = new CdpClient(await chromeTarget(debug.host), 'host')
    const guest = new CdpClient(await chromeTarget(debug.guest), 'guest')
    const watcher = new CdpClient(await chromeTarget(debug.watcher), 'watcher')
    clients.push(host, guest, watcher)
    await Promise.all([host.connect(), guest.connect(), watcher.connect()])
    await Promise.all([
      authenticatePage(host, appBase, hostAuth),
      authenticatePage(guest, appBase, guestAuth),
      authenticatePage(watcher, appBase, watcherAuth),
    ])
    await Promise.all([
      host.setViewport(1440, 1000),
      guest.setViewport(390, 844, true),
      watcher.setViewport(1100, 820),
    ])

    // Private tic-tac-toe: create through the UI, enter by password/invite, and prove a win.
    await host.navigate(`${appBase}/games`)
    await host.waitFor("document.body.textContent.includes('桌游大厅') && Boolean(document.querySelector('option[value=\"tic-tac-toe\"]'))")
    await setControl(host, '游戏', 'tic-tac-toe')
    await setControl(host, '房间名称', 'Phase 9 Private Tic Tac Toe')
    await setControl(host, '可见性', 'private')
    await host.waitFor("Array.from(document.querySelectorAll('label')).some((label) => label.textContent.includes('房间密码'))")
    await setControl(host, '房间密码', privatePassword)
    await setControl(host, '每回合时限', 45)
    await clickText(host, '创建房间')
    await host.waitFor("location.pathname.startsWith('/games/rooms/') && document.querySelector('h1')?.textContent.includes('Phase 9 Private')")
    const privateRoomId = await host.evaluate("Number(location.pathname.split('/').pop())")
    let privateRoom = await roomDetail(appBase, privateRoomId, hostAuth.access_token)
    const invite = expectOk(await api(appBase, `/api/games/rooms/${privateRoomId}/invites`, {
      body: { ttl_minutes: 60 }, method: 'POST', token: hostAuth.access_token,
    }), 'create private invite')
    const hiddenFromPublic = expectOk(await api(appBase, '/api/games/rooms', { token: guestAuth.access_token }), 'public rooms')
    assert(!hiddenFromPublic.some((room) => room.id === privateRoomId), 'private room appeared publicly')

    await enterByCode(guest, appBase, privateRoom.room_code, { joinPassword: privatePassword, role: 'player' })
    await guest.waitFor("document.querySelector('h1')?.textContent === 'Phase 9 Private Tic Tac Toe'")
    await enterByCode(watcher, appBase, privateRoom.room_code, { invite: invite.token, role: 'spectator' })
    await watcher.waitFor("document.body.textContent.includes('观战模式') && document.querySelector('h1')?.textContent.includes('Phase 9 Private')")

    await clickText(host, '准备')
    await guest.waitFor("Array.from(document.querySelectorAll('li')).some((item) => item.textContent.includes('phase9_host') && item.textContent.includes('已准备'))")
    await clickText(guest, '准备')
    await host.waitFor("Array.from(document.querySelectorAll('button')).some((button) => button.textContent.includes('开始棋局') && !button.disabled)")
    await clickText(host, '开始棋局')
    await Promise.all([
      host.waitFor("document.querySelector('[aria-label=\"第 1 格，空位\"]') && document.body.textContent.includes('轮到 X')"),
      guest.waitFor("Boolean(document.querySelector('[aria-label=\"第 1 格，空位\"]'))"),
      watcher.waitFor("Boolean(document.querySelector('[aria-label=\"第 1 格，空位\"]'))"),
    ])
    await assertAriaDisabled(watcher, '第 1 格，空位')

    await setControl(guest, '聊天消息', 'Phase 9 private hello')
    await clickAria(guest, '发送消息')
    await Promise.all([
      host.waitFor("document.body.textContent.includes('Phase 9 private hello')"),
      watcher.waitFor("document.body.textContent.includes('Phase 9 private hello')"),
    ])

    await clickText(host, '请求和棋')
    await guest.waitFor("document.body.textContent.includes('拒绝和棋')")
    await clickText(guest, '拒绝和棋')
    privateRoom = await waitRoomVersion(appBase, privateRoomId, hostAuth.access_token, 2)
    await clickAria(host, '第 1 格，空位')
    privateRoom = await waitRoomVersion(appBase, privateRoomId, hostAuth.access_token, 3)
    await assertAriaDisabled(guest, '第 1 格，X')
    const stale = await api(appBase, `/api/games/rooms/${privateRoomId}/actions`, {
      body: { action: { cell: 3, type: 'place' }, expected_version: 2 },
      method: 'POST', token: guestAuth.access_token,
    })
    assert.equal(stale.status, 409)
    const spectatorDenied = await api(appBase, `/api/games/rooms/${privateRoomId}/actions`, {
      body: { action: { cell: 8, type: 'place' }, expected_version: 3 },
      method: 'POST', token: watcherAuth.access_token,
    })
    assert.equal(spectatorDenied.status, 403)
    await clickAria(guest, '第 4 格，空位')
    await waitRoomVersion(appBase, privateRoomId, hostAuth.access_token, 4)
    await clickAria(host, '第 2 格，空位')
    await waitRoomVersion(appBase, privateRoomId, hostAuth.access_token, 5)
    await clickAria(guest, '第 5 格，空位')
    await waitRoomVersion(appBase, privateRoomId, hostAuth.access_token, 6)
    await clickAria(host, '第 3 格，空位')
    privateRoom = await waitForApi(async () => {
      const room = await roomDetail(appBase, privateRoomId, hostAuth.access_token)
      return room.status === 'finished' ? room : null
    }, 'tic-tac-toe win')
    assert.equal(privateRoom.result.reason, 'line')
    await Promise.all([
      host.waitFor("document.body.textContent.includes('phase9_host 获胜')"),
      guest.waitFor("document.body.textContent.includes('phase9_host 获胜')"),
      watcher.waitFor("document.body.textContent.includes('phase9_host 获胜')"),
    ])
    const privateReplay = expectOk(await api(appBase, `/api/games/rooms/${privateRoomId}/replay?skip=0&limit=100`, {
      token: watcherAuth.access_token,
    }), 'private replay')
    assert.equal(privateReplay.verified, true)
    assert.equal(privateReplay.complete, true)
    assert.equal(privateReplay.result.reason, 'line')
    assert.equal(privateReplay.total, 8)
    await Promise.all([loadReplay(host), loadReplay(guest), loadReplay(watcher)])
    await Promise.all([
      capture(host, 'tic-tac-toe-host-desktop.png'),
      capture(guest, 'tic-tac-toe-guest-mobile.png'),
      capture(watcher, 'tic-tac-toe-spectator.png'),
    ])
    await Promise.all([
      inspectPage(host, appBase, [privatePassword, invite.token]),
      inspectPage(guest, appBase, [privatePassword, invite.token]),
      inspectPage(watcher, appBase, [privatePassword, invite.token]),
    ])

    // Public Gomoku: join from the listing, prove 225 safe cells, multi-tab presence, recovery, draw and replay.
    await host.navigate(`${appBase}/games`)
    await host.waitFor("document.body.textContent.includes('桌游大厅') && Boolean(document.querySelector('option[value=\"gomoku\"]'))")
    await setControl(host, '游戏', 'gomoku')
    await setControl(host, '房间名称', 'Phase 9 Public Gomoku')
    await setControl(host, '可见性', 'public')
    await clickText(host, '创建房间')
    await host.waitFor("document.querySelector('h1')?.textContent === 'Phase 9 Public Gomoku'")
    const gomokuRoomId = await host.evaluate("Number(location.pathname.split('/').pop())")
    let gomokuRoom = await roomDetail(appBase, gomokuRoomId, hostAuth.access_token)
    await Promise.all([guest.navigate(`${appBase}/games`), watcher.navigate(`${appBase}/games`)])
    await Promise.all([
      guest.waitFor("document.body.textContent.includes('Phase 9 Public Gomoku')"),
      watcher.waitFor("document.body.textContent.includes('Phase 9 Public Gomoku')"),
    ])
    await clickText(guest, '加入Phase 9 Public Gomoku')
    await clickText(watcher, '观战Phase 9 Public Gomoku')
    await Promise.all([
      guest.waitFor("document.querySelector('h1')?.textContent === 'Phase 9 Public Gomoku'"),
      watcher.waitFor("document.body.textContent.includes('观战模式') && document.querySelector('h1')?.textContent.includes('Gomoku')"),
    ])
    await clickText(host, '准备')
    await guest.waitFor("Array.from(document.querySelectorAll('li')).some((item) => item.textContent.includes('phase9_host') && item.textContent.includes('已准备'))")
    await clickText(guest, '准备')
    await host.waitFor("Array.from(document.querySelectorAll('button')).some((button) => button.textContent.includes('开始棋局') && !button.disabled)")
    await clickText(host, '开始棋局')
    await Promise.all([
      host.waitFor("document.querySelectorAll('[aria-label^=\"第 \"].game-board__cell--gomoku').length === 225"),
      guest.waitFor("document.querySelectorAll('.game-board__cell--gomoku').length === 225"),
      watcher.waitFor("document.querySelectorAll('.game-board__cell--gomoku').length === 225"),
    ])
    await assertAriaDisabled(watcher, '第 8 行第 8 列，空位')

    await setControl(guest, '聊天消息', 'Phase 9 gomoku hello')
    await clickAria(guest, '发送消息')
    await watcher.waitFor("document.body.textContent.includes('Phase 9 gomoku hello')")

    const gomokuUrl = `${appBase}/games/rooms/${gomokuRoomId}`
    const extraTarget = await newTab(debug.guest, gomokuUrl)
    const guestTab = new CdpClient(extraTarget, 'guest-tab')
    clients.push(guestTab)
    await guestTab.connect()
    await guestTab.setViewport(1000, 760)
    await guestTab.waitFor("document.querySelector('h1')?.textContent === 'Phase 9 Public Gomoku' && document.body.textContent.includes('已与服务器同步')", 20000)
    await closeTab(debug.guest, extraTarget.id)
    guestTab.close()
    await sleep(700)
    gomokuRoom = await roomDetail(appBase, gomokuRoomId, hostAuth.access_token)
    assert(gomokuRoom.members.some((member) => member.user_id === guestAuth.user.id && member.is_online), 'closing one tab marked guest offline')

    await clickAria(host, '第 8 行第 8 列，空位')
    await waitRoomVersion(appBase, gomokuRoomId, hostAuth.access_token, 1)
    await clickAria(guest, '第 8 行第 9 列，空位')
    await waitRoomVersion(appBase, gomokuRoomId, hostAuth.access_token, 2)
    await guest.send('Network.emulateNetworkConditions', {
      connectionType: 'none', downloadThroughput: 0, latency: 0, offline: true, uploadThroughput: 0,
    })
    await guest.waitFor("document.body.textContent.includes('连接中断')", 10000)
    await clickText(host, '请求和棋')
    await waitRoomVersion(appBase, gomokuRoomId, hostAuth.access_token, 3)
    await guest.send('Network.emulateNetworkConditions', {
      connectionType: 'cellular3g', downloadThroughput: 256000, latency: 200, offline: false, uploadThroughput: 128000,
    })
    await guest.waitFor("document.body.textContent.includes('接受和棋') && document.body.textContent.includes('已与服务器同步')", 20000)
    await guest.reload()
    await guest.waitFor("document.body.textContent.includes('接受和棋') && document.body.textContent.includes('已与服务器同步')", 20000)
    await clickText(guest, '接受和棋')
    gomokuRoom = await waitForApi(async () => {
      const room = await roomDetail(appBase, gomokuRoomId, hostAuth.access_token)
      return room.status === 'finished' ? room : null
    }, 'gomoku accepted draw')
    assert.equal(gomokuRoom.result.reason, 'draw_agreement')
    await Promise.all([
      host.waitFor("document.body.textContent.includes('和棋（双方同意和棋）')"),
      guest.waitFor("document.body.textContent.includes('和棋（双方同意和棋）')"),
      watcher.waitFor("document.body.textContent.includes('和棋（双方同意和棋）')"),
    ])
    const gomokuReplay = expectOk(await api(appBase, `/api/games/rooms/${gomokuRoomId}/replay?skip=0&limit=100`, {
      token: watcherAuth.access_token,
    }), 'gomoku replay')
    assert.equal(gomokuReplay.verified, true)
    assert.equal(gomokuReplay.result.reason, 'draw_agreement')
    await Promise.all([loadReplay(host), loadReplay(guest), loadReplay(watcher)])
    await Promise.all([
      capture(host, 'gomoku-host-desktop.png'),
      capture(guest, 'gomoku-guest-mobile.png'),
      capture(watcher, 'gomoku-spectator.png'),
    ])

    // Surrender and timeout results use the same UI and safe result summary.
    const surrenderRoom = await createStartedRoom(appBase, hostAuth, guestAuth, 'Phase 9 Surrender Proof')
    await Promise.all([
      host.navigate(`${appBase}/games/rooms/${surrenderRoom.id}`),
      guest.navigate(`${appBase}/games/rooms/${surrenderRoom.id}`),
    ])
    await guest.waitFor("document.body.textContent.includes('认输') && document.body.textContent.includes('已与服务器同步')")
    await clickText(guest, '认输')
    await host.waitFor("document.body.textContent.includes('phase9_host 获胜（对手认输）')", 15000)
    const surrenderResult = await roomDetail(appBase, surrenderRoom.id, hostAuth.access_token)
    assert.equal(surrenderResult.result.reason, 'surrender')

    const timeoutRoom = await createStartedRoom(appBase, hostAuth, guestAuth, 'Phase 9 Timeout Proof', 15)
    await Promise.all([
      host.navigate(`${appBase}/games/rooms/${timeoutRoom.id}`),
      guest.navigate(`${appBase}/games/rooms/${timeoutRoom.id}`),
    ])
    await guest.waitFor("document.body.textContent.includes('判定超时') && document.body.textContent.includes('已与服务器同步')")
    await sleep(16_000)
    await clickText(guest, '判定超时')
    await host.waitFor("document.body.textContent.includes('phase9_guest 获胜（对手超时）')", 15000)
    const timeoutResult = await roomDetail(appBase, timeoutRoom.id, hostAuth.access_token)
    assert.equal(timeoutResult.result.reason, 'timeout')

    const finalInspections = await Promise.all([
      inspectPage(host, appBase), inspectPage(guest, appBase), inspectPage(watcher, appBase),
    ])
    console.log(JSON.stringify({
      finalInspections,
      gomoku: { replayFrames: gomokuReplay.total, result: gomokuReplay.result.reason },
      screenshots: fs.readdirSync(screenshotDir).sort(),
      ticTacToe: { replayFrames: privateReplay.total, result: privateReplay.result.reason },
      timeout: timeoutResult.result.reason,
    }, null, 2))
  } finally {
    for (const client of clients) client.close()
    for (const process of processes.reverse()) await stopProcess(process)
    if (process.env.BLUE_ALBUM_KEEP_TEMP) {
      console.error(`Preserved browser logs at ${temporaryRoot}`)
    } else {
      fs.rmSync(temporaryRoot, { recursive: true, force: true })
    }
  }
}


main().catch((error) => {
  console.error(error.stack || error)
  process.exitCode = 1
})
