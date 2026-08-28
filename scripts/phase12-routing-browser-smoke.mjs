import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const python = path.join(root, 'backend', '.venv', 'bin', 'python')
const chromeBinary = process.env.CHROME_BINARY || '/usr/bin/google-chrome-stable'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-phase12-routing'
const password = 'Phase12Browser2026!'
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

class BrowserPage {
  constructor(target) {
    this.errors = []
    this.failedResponses = []
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
      if (message.method === 'Network.requestWillBeSent') this.requests.push(message.params.request.url)
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
  }

  send(method, params = {}) {
    const id = this.nextId++
    return new Promise((resolve, reject) => {
      this.pending.set(id, { reject, resolve })
      this.socket.send(JSON.stringify({ id, method, params }))
    })
  }

  async evaluate(expression) {
    const response = await this.send('Runtime.evaluate', {
      awaitPromise: true,
      expression,
      returnByValue: true,
      userGesture: true,
    })
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text)
    return response.result.value
  }

  async waitFor(expression, timeout = 20000) {
    const deadline = Date.now() + timeout
    while (Date.now() < deadline) {
      try {
        if (await this.evaluate(expression)) return
      } catch {
        // A hard navigation may briefly replace the execution context.
      }
      await sleep(100)
    }
    const state = await this.evaluate(`({ url: location.href, text: document.body?.innerText?.slice(0, 1600) || '' })`)
    throw new Error(`Timed out: ${expression}\n${JSON.stringify(state)}`)
  }

  async navigate(url) {
    this.errors.length = 0
    this.failedResponses.length = 0
    this.requests.length = 0
    await this.send('Page.navigate', { url })
    await this.waitFor("document.readyState === 'complete' && Boolean(document.querySelector('#root > *'))")
    await this.waitFor("!document.querySelector('[aria-label=\"正在载入页面\"]')")
    await sleep(150)
  }

  async capture(filename) {
    fs.mkdirSync(screenshotDir, { recursive: true })
    const shot = await this.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
    const output = path.join(screenshotDir, filename)
    fs.writeFileSync(output, Buffer.from(shot.data, 'base64'))
    return output
  }

  close() { this.socket?.close() }
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
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch { /* Process is still starting. */ }
    await sleep(150)
  }
  throw new Error(`Timed out waiting for ${url}`)
}

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, stdio: ['ignore', 'pipe', 'pipe'] })
    let output = ''
    child.stdout.on('data', (chunk) => { output += chunk })
    child.stderr.on('data', (chunk) => { output += chunk })
    child.on('error', reject)
    child.on('exit', (code) => code === 0 ? resolve(output) : reject(new Error(`${command} exited ${code}\n${output}`)))
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

async function api(appBase, pathname, { body, form, method = 'GET' } = {}) {
  const headers = {}
  let requestBody
  if (form) requestBody = form
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(body)
  }
  const response = await fetch(`${appBase}${pathname}`, { body: requestBody, headers, method })
  const text = await response.text()
  let payload = text
  try { payload = text ? JSON.parse(text) : null } catch { /* Keep plain text. */ }
  assert(response.ok, `${method} ${pathname} failed (${response.status}): ${JSON.stringify(payload)}`)
  return payload
}

async function register(appBase, username) {
  return api(appBase, '/api/users/register', {
    body: { email: `${username}@example.com`, password, username },
    method: 'POST',
  })
}

async function login(appBase, username) {
  return api(appBase, '/api/auth/login', {
    form: new URLSearchParams({ password, username }),
    method: 'POST',
  })
}

async function chromeTarget(debugBase) {
  await waitForUrl(`${debugBase}/json/version`)
  const targets = await fetch(`${debugBase}/json/list`).then((response) => response.json())
  const target = targets.find((candidate) => candidate.type === 'page')
  assert(target?.webSocketDebuggerUrl, `No Chrome page target at ${debugBase}`)
  return target
}

async function setAuth(page, appBase, auth) {
  await page.navigate(`${appBase}/login`)
  await page.evaluate(`(() => {
    localStorage.setItem('token', ${JSON.stringify(auth.access_token)})
    localStorage.setItem('refresh_token', ${JSON.stringify(auth.refresh_token)})
    localStorage.setItem('user', ${JSON.stringify(JSON.stringify(auth.user))})
  })()`)
}

async function main() {
  assert(fs.existsSync(python), 'backend/.venv is required')
  assert(fs.existsSync(chromeBinary), `Chrome is unavailable: ${chromeBinary}`)
  fs.rmSync(screenshotDir, { recursive: true, force: true })
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'blue-album-phase12-'))
  const processes = []
  let page
  let secondPage

  try {
    const [backendPort, frontendPort, debugPort] = await Promise.all([freePort(), freePort(), freePort()])
    const appBase = `http://127.0.0.1:${frontendPort}`
    const backendBase = `http://127.0.0.1:${backendPort}`
    const environment = {
      ...process.env,
      CORS_ORIGINS: appBase,
      DATABASE_URL: `sqlite:///${path.join(temporaryRoot, 'phase12.sqlite')}`,
      PRIVATE_STORAGE_DIR: path.join(temporaryRoot, 'private-storage'),
      PUBLIC_SYNC_STORAGE: path.join(temporaryRoot, 'sync-storage'),
      SECRET_KEY: 'phase12-browser-isolated-secret',
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
      env: { ...process.env, VITE_BACKEND_PROXY_TARGET: backendBase },
      logPath: path.join(temporaryRoot, 'frontend.log'),
    }))
    await waitForUrl(appBase)

    await register(appBase, 'phase12_admin')
    await register(appBase, 'phase12_reader')
    await run(python, ['-c', [
      'import models',
      'from database import SessionLocal',
      'db = SessionLocal()',
      "user = db.query(models.User).filter(models.User.username == 'phase12_admin').one()",
      "user.role = 'admin'",
      'db.commit()',
      'db.close()',
    ].join('; ')], { cwd: path.join(root, 'backend'), env: environment })
    const readerAuth = await login(appBase, 'phase12_reader')
    const adminAuth = await login(appBase, 'phase12_admin')

    processes.push(startProcess(chromeBinary, [
      '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--no-first-run',
      `--remote-debugging-port=${debugPort}`, `--user-data-dir=${path.join(temporaryRoot, 'chrome')}`, 'about:blank',
    ], { cwd: root, env: process.env, logPath: path.join(temporaryRoot, 'chrome.log') }))
    page = new BrowserPage(await chromeTarget(`http://127.0.0.1:${debugPort}`))
    await page.connect()
    await page.send('Emulation.setDeviceMetricsOverride', { deviceScaleFactor: 1, height: 1000, mobile: false, width: 1440 })

    await page.navigate(`${appBase}/tools`)
    const visitor = await page.evaluate(`(() => ({
      links: Array.from(document.querySelectorAll('nav[aria-label="主导航"] a')).map((item) => item.textContent.trim()),
      text: document.body.innerText,
    }))()`)
    assert.deepEqual(visitor.links, ['首页', '归档', '工具箱', '登录'])
    for (const label of ['我的收藏', '同步观影', '同步听歌', '书籍', '登录后继续']) assert(visitor.text.includes(label))
    assert(!page.requests.some((url) => /\/api\/(bookmarks|sync-rooms|users\/me)/.test(url)), 'public toolbox requested private data')
    const visitorShot = await page.capture('visitor-tools.png')

    await page.evaluate(`(() => {
      const set = (selector, value) => {
        const input = document.querySelector(selector)
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value)
        input.dispatchEvent(new Event('input', { bubbles: true }))
      }
      set('#login-identifier', 'phase12_reader')
      set('#login-password', ${JSON.stringify(password)})
      document.querySelector('#login-identifier').form.requestSubmit()
    })()`)
    await page.waitFor("document.querySelector('nav[aria-label=\"主导航\"]')?.innerText.includes('账户') && !document.body.innerText.includes('登录后继续')")
    assert.equal(await page.evaluate('location.pathname'), '/tools')
    const reader = await page.evaluate(`(() => ({
      links: Array.from(document.querySelectorAll('nav[aria-label="主导航"] a')).map((item) => item.textContent.trim()),
      tools: Array.from(document.querySelectorAll('a[aria-label^="打开"]')).map((item) => ({ label: item.ariaLabel, href: new URL(item.href).pathname })),
      text: document.body.innerText,
    }))()`)
    assert.deepEqual(reader.links, ['首页', '归档', '工具箱', '账户'])
    assert.deepEqual(reader.tools, [
      { label: '打开我的收藏', href: '/account/collection' },
      { label: '打开同步观影', href: '/tools/sync-room' },
      { label: '打开同步听歌', href: '/music' },
      { label: '打开书籍', href: '/books' },
    ])
    assert(!reader.text.includes('管理员控制台'))
    await sleep(1000)
    const readerShot = await page.capture('reader-tools.png')

    const secondTarget = await fetch(
      `http://127.0.0.1:${debugPort}/json/new?${encodeURIComponent(`${appBase}/books`)}`,
      { method: 'PUT' },
    ).then((response) => response.json())
    secondPage = new BrowserPage(secondTarget)
    await secondPage.connect()
    await secondPage.waitFor("document.readyState === 'complete' && location.pathname === '/books' && Boolean(document.querySelector('h1'))")
    assert((await secondPage.evaluate("document.querySelector('nav[aria-label=\"主导航\"]')?.innerText")).includes('账户'))

    await page.navigate(`${appBase}/music`)
    await page.waitFor("document.querySelector('h1')?.textContent === '音乐大厅'")
    await page.navigate(`${appBase}/tools/links?view=all#folders`)
    await page.waitFor("location.pathname === '/account/collection'")
    assert.equal(await page.evaluate('location.search + location.hash'), '?view=all#folders')
    await page.navigate(`${appBase}/account/admin/security`)
    await page.waitFor("document.querySelector('h1')?.textContent === '无权访问此页面'")
    assert.equal(await page.evaluate('location.pathname'), '/account/admin/security')

    await setAuth(page, appBase, adminAuth)
    await page.navigate(`${appBase}/account`)
    await page.waitFor("document.body.innerText.includes('管理员控制台')")
    await sleep(500)
    const adminShot = await page.capture('admin-account.png')
    await page.navigate(`${appBase}/tools`)
    assert(!(await page.evaluate('document.body.innerText')).includes('管理员控制台'))
    await page.navigate(`${appBase}/tools/frp?tab=logs#latest`)
    await page.waitFor("location.pathname === '/account/admin/services/frp'")
    assert.equal(await page.evaluate('location.search + location.hash'), '?tab=logs#latest')

    await setAuth(page, appBase, readerAuth)
    await page.navigate(`${appBase}/tools/sync-room/room-direct?autoplay=1#player`)
    assert.equal(await page.evaluate('location.pathname + location.search + location.hash'), '/tools/sync-room/room-direct?autoplay=1#player')
    await page.navigate(`${appBase}/this-route-does-not-exist`)
    await page.waitFor("document.body.innerText.includes('这个页面不存在')")
    assert.deepEqual(page.errors, [], `browser console errors: ${JSON.stringify(page.errors)}`)

    console.log(JSON.stringify({ adminShot, readerShot, visitorShot }, null, 2))
    console.log('phase 12 routing browser smoke passed')
  } finally {
    secondPage?.close()
    page?.close()
    for (const process of processes.reverse()) await stopProcess(process)
    fs.rmSync(temporaryRoot, { recursive: true, force: true })
  }
}

main().catch((error) => {
  console.error(error.stack || error)
  process.exitCode = 1
})
