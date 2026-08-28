import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'


const root = path.resolve(import.meta.dirname, '..')
const python = path.join(root, 'backend', '.venv', 'bin', 'python')
const chromeBinary = process.env.CHROME_BINARY || '/usr/bin/google-chrome-stable'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-phase10-books-admin-browser'
const password = 'Phase10Browser2026!'
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))


class CdpClient {
  constructor(target, label, downloadPath) {
    this.errors = []
    this.failedResponses = []
    this.downloadPath = downloadPath
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
    await this.send('DOM.enable')
    await this.send('Browser.setDownloadBehavior', {
      behavior: 'allow',
      downloadPath: this.downloadPath,
    })
    await this.send('Page.addScriptToEvaluateOnNewDocument', {
      source: `(() => {
        const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie')
        window.__phase10CookieReads = 0
        if (descriptor?.configurable) {
          Object.defineProperty(Document.prototype, 'cookie', {
            configurable: true,
            get() { window.__phase10CookieReads += 1; return descriptor.get.call(this) },
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
      pageState = await this.evaluate(`({ url: location.href, text: document.body?.innerText?.slice(0, 1600) || '' })`)
    } catch {
      // Keep the original timeout if the page itself is unavailable.
    }
    throw new Error(`${this.label} timed out: ${expression}${lastError ? ` (${lastError.message})` : ''}${pageState ? `\n${JSON.stringify(pageState)}` : ''}${this.failedResponses.length ? `\nfailed responses: ${JSON.stringify(this.failedResponses)}` : ''}`)
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
  const response = await fetch(`${appBase}${pathname}`, { body: requestBody, headers, method })
  const text = await response.text()
  let payload = text
  try { payload = text ? JSON.parse(text) : null } catch { /* Retain plain text. */ }
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

async function setControl(page, labelText, value) {
  const changed = await page.evaluate(`(async () => {
    const normalized = (value) => value.replace('*', '').trim()
    const label = Array.from(document.querySelectorAll('label')).find((candidate) => (
      normalized(candidate.textContent).startsWith(${JSON.stringify(labelText)})
    ))
    const control = (label?.htmlFor ? document.getElementById(label.htmlFor) : null)
      || label?.querySelector('input, select, textarea')
      || document.querySelector('[aria-label=${JSON.stringify(labelText)}]')
    if (!control) return false
    if (control instanceof HTMLInputElement && control.type === 'checkbox') {
      const desired = Boolean(${JSON.stringify(value)})
      if (control.checked !== desired) control.click()
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

async function selectOptionText(page, labelText, optionText) {
  const selected = await page.evaluate(`(async () => {
    const normalized = (value) => value.trim()
    const label = Array.from(document.querySelectorAll('label')).find((candidate) => normalized(candidate.textContent).startsWith(${JSON.stringify(labelText)}))
    const select = (label?.htmlFor ? document.getElementById(label.htmlFor) : null) || label?.querySelector('select')
    const option = Array.from(select?.options || []).find((candidate) => normalized(candidate.textContent) === ${JSON.stringify(optionText)})
    if (!select || !option) return false
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, option.value)
    select.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    return true
  })()`)
  assert(selected, `${page.label} missing ${optionText} in ${labelText}`)
}

async function setFileInput(page, selector, filePath) {
  const documentNode = await page.send('DOM.getDocument', { depth: 1 })
  const selected = await page.send('DOM.querySelector', {
    nodeId: documentNode.root.nodeId,
    selector,
  })
  assert(selected.nodeId, `${page.label} missing file input ${selector}`)
  await page.send('DOM.setFileInputFiles', { files: [filePath], nodeId: selected.nodeId })
}

async function capture(page, filename) {
  fs.mkdirSync(screenshotDir, { recursive: true })
  const shot = await page.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
  const output = path.join(screenshotDir, filename)
  fs.writeFileSync(output, Buffer.from(shot.data, 'base64'))
  return output
}

async function inspectPage(page, appBase, forbiddenValues = []) {
  const state = await page.evaluate(`(() => {
    const html = document.documentElement.innerHTML
    const duplicateIds = Array.from(document.querySelectorAll('[id]')).map((element) => element.id)
      .filter((id, index, ids) => ids.indexOf(id) !== index)
    return {
      cookieReads: window.__phase10CookieReads || 0,
      duplicateIds,
      hasIframe: Boolean(document.querySelector('iframe')),
      headingCount: document.querySelectorAll('h1, h2').length,
      leak: ['device_token_hash', 'storage_path', '/private_storage', '/sync-storage', '/home/frp', 'password_hash']
        .some((token) => html.toLowerCase().includes(token)),
      mainCount: document.querySelectorAll('main').length,
      overflow: document.documentElement.scrollWidth - innerWidth,
      pathname: location.pathname,
      staleNotice: /书籍已创建。|书籍已保存。|书单顺序已保存。|设备凭据已复制。/.test(document.body.innerText),
      text: document.body.innerText,
    }
  })()`)
  const websocketBase = appBase.replace(/^http/, 'ws')
  const forbiddenRequests = page.requests.filter((url) => (
    !url.startsWith(appBase)
    && !url.startsWith(websocketBase)
    && !url.startsWith('data:')
    && !url.startsWith('blob:')
    && !url.startsWith('chrome://')
  ))
  assert.equal(state.cookieReads, 0, `${page.label} read document.cookie`)
  assert.equal(state.hasIframe, false, `${page.label} rendered an iframe`)
  assert.equal(state.leak, false, `${page.label} exposed a private credential or path field`)
  assert.equal(state.mainCount, 1, `${page.label} should render exactly one main landmark`)
  assert(state.headingCount > 0, `${page.label} has no page heading`)
  assert.equal(state.staleNotice, false, `${page.label} kept a stale success notice after navigation`)
  assert.deepEqual(state.duplicateIds, [], `${page.label} rendered duplicate ids`)
  assert(state.overflow <= 1, `${page.label} overflows by ${state.overflow}px`)
  for (const value of forbiddenValues.filter(Boolean)) {
    assert(!state.text.includes(value), `${page.label} exposed secret ${value}`)
  }
  assert.deepEqual(forbiddenRequests, [], `${page.label} made forbidden requests`)
  assert.deepEqual(page.errors, [], `${page.label} emitted browser errors`)
  return state
}

async function uploadChunks(appBase, deviceToken, relativePath, content) {
  const digest = createHash('sha256').update(content).digest('hex')
  const midpoint = Math.ceil(content.length / 2)
  const chunks = [content.subarray(0, midpoint), content.subarray(midpoint)]
  const uploadId = 'phase10-browser-upload'
  let result
  for (let index = 0; index < chunks.length; index += 1) {
    const form = new FormData()
    form.append('relative_path', relativePath)
    form.append('upload_id', uploadId)
    form.append('chunk_index', String(index))
    form.append('total_chunks', String(chunks.length))
    form.append('expected_size', String(content.length))
    form.append('expected_sha256', digest)
    form.append('mtime', '2026-07-16T08:00:00')
    form.append('file', new Blob([chunks[index]], { type: 'text/plain' }), `chunk-${index}.part`)
    result = await api(appBase, '/api/sync/files/chunks', {
      form,
      headers: { 'X-Sync-Token': deviceToken },
      method: 'POST',
    })
    expectOk(result, `upload sync chunk ${index}`)
  }
  return result.payload
}


async function main() {
  assert(fs.existsSync(python), 'backend/.venv is required')
  assert(fs.existsSync(chromeBinary), `Chrome is unavailable: ${chromeBinary}`)
  fs.rmSync(screenshotDir, { recursive: true, force: true })
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'blue-album-phase10-'))
  const clients = []
  const processes = []
  let cleanupVerified = false

  try {
    const [backendPort, frontendPort, adminDebugPort, visitorDebugPort] = await Promise.all([
      freePort(), freePort(), freePort(), freePort(),
    ])
    const appBase = `http://127.0.0.1:${frontendPort}`
    const backendBase = `http://127.0.0.1:${backendPort}`
    const adminFilesRoot = path.join(temporaryRoot, 'admin-files')
    const syncRoot = path.join(temporaryRoot, 'sync-storage')
    const environment = {
      ...process.env,
      ACCESS_TOKEN_EXPIRE_MINUTES: '60',
      ADMIN_FILES_STORAGE_DIR: adminFilesRoot,
      BOOKMARK_BACKUP_OUTPUT_DIR: path.join(temporaryRoot, 'bookmark-backups'),
      CORS_ORIGINS: appBase,
      DATABASE_URL: `sqlite:///${path.join(temporaryRoot, 'phase10.sqlite')}`,
      PRIVATE_STORAGE_DIR: path.join(temporaryRoot, 'private-storage'),
      PUBLIC_SYNC_STORAGE: syncRoot,
      SECRET_KEY: 'phase10-browser-isolated-secret',
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

    await register(appBase, 'phase10_admin')
    await run(python, ['-c', [
      'import models',
      'from database import SessionLocal',
      'db = SessionLocal()',
      "user = db.query(models.User).filter(models.User.username == 'phase10_admin').one()",
      "user.role = 'admin'",
      'db.commit()',
      'db.close()',
    ].join('; ')], { cwd: path.join(root, 'backend'), env: environment })
    const adminAuth = await login(appBase, 'phase10_admin')
    await register(appBase, 'phase10_member')
    const memberAuth = await login(appBase, 'phase10_member')

    for (const [label, debugPort] of [['admin', adminDebugPort], ['visitor', visitorDebugPort]]) {
      processes.push(startProcess(chromeBinary, [
        '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
        '--no-first-run', '--no-default-browser-check', `--remote-debugging-port=${debugPort}`,
        `--user-data-dir=${path.join(temporaryRoot, `${label}-chrome`)}`, 'about:blank',
      ], { cwd: root, env: process.env, logPath: path.join(temporaryRoot, `${label}-chrome.log`) }))
    }
    const downloadRoot = path.join(temporaryRoot, 'downloads')
    const admin = new CdpClient(await chromeTarget(`http://127.0.0.1:${adminDebugPort}`), 'admin', downloadRoot)
    const visitor = new CdpClient(await chromeTarget(`http://127.0.0.1:${visitorDebugPort}`), 'visitor', downloadRoot)
    clients.push(admin, visitor)
    await Promise.all([admin.connect(), visitor.connect()])
    await Promise.all([
      authenticatePage(admin, appBase, adminAuth),
      authenticatePage(visitor, appBase, memberAuth),
    ])
    await Promise.all([admin.setViewport(1440, 1000), visitor.setViewport(1440, 1000)])

    // Curate a public book, edit it, create a public reading list, and order the book through the UI.
    await admin.navigate(`${appBase}/account/admin/content/books`)
    await admin.waitFor("document.querySelector('h1')?.textContent === '书籍内容' && document.body.textContent.includes('还没有书籍')")
    await clickText(admin, '添加书籍')
    await setControl(admin, '书名', 'Phase 10 Browser Book')
    await setControl(admin, '网址标识', 'phase-10-browser-book')
    await setControl(admin, '作者', 'Browser Curator')
    await setControl(admin, '分类', 'Acceptance')
    await setControl(admin, '书籍标签', 'browser, acceptance')
    await setControl(admin, '阅读状态', 'reading')
    await setControl(admin, '简介', 'A browser-created acceptance title.')
    await setControl(admin, '公开书籍', true)
    await setControl(admin, '设为精选', true)
    await clickText(admin, '创建书籍')
    await admin.waitFor("document.body.textContent.includes('书籍已创建。') && document.body.textContent.includes('Phase 10 Browser Book')")
    await clickAria(admin, '编辑 Phase 10 Browser Book')
    await setControl(admin, '书名', 'Phase 10 Browser Book Revised')
    await clickText(admin, '保存书籍')
    await admin.waitFor("document.body.textContent.includes('书籍已保存。') && document.body.textContent.includes('Phase 10 Browser Book Revised')")

    await clickText(admin, '书单', '[role="tab"]')
    await clickText(admin, '添加书单')
    await setControl(admin, '书单名称', 'Phase 10 Reading Path')
    await setControl(admin, '网址标识', 'phase-10-reading-path')
    await setControl(admin, '书单简介', 'Ordered during browser acceptance.')
    await setControl(admin, '公开书单', true)
    await clickText(admin, '创建书单')
    await admin.waitFor("document.body.textContent.includes('书单已创建。') && document.body.textContent.includes('添加书籍')")
    await selectOptionText(admin, '添加书籍', 'Phase 10 Browser Book Revised')
    await clickText(admin, '保存书单顺序')
    await admin.waitFor("document.body.textContent.includes('书单顺序已保存。') && document.body.textContent.includes('1. Phase 10 Browser Book Revised')")

    // Books are administrator-only after the toolbox redesign. A regular member is denied,
    // while an administrator can still review the published shelf.
    await visitor.navigate(`${appBase}/books`)
    await visitor.waitFor("document.body.textContent.includes('无权访问此页面') && !document.body.textContent.includes('Phase 10 Browser Book Revised')")
    await inspectPage(visitor, appBase)
    await capture(visitor, 'books-member-denied.png')

    await admin.navigate(`${appBase}/books`)
    await admin.waitFor("document.body.textContent.includes('Phase 10 Browser Book Revised') && document.body.textContent.includes('Phase 10 Reading Path')")
    assert.equal(await admin.evaluate("document.body.textContent.includes('Kavita')"), false)
    await setControl(admin, '搜索书籍', 'Browser Book Revised')
    await admin.waitFor("document.querySelectorAll('.books-card').length >= 1")
    await inspectPage(admin, appBase)
    await capture(admin, 'books-admin-desktop.png')
    await admin.setViewport(390, 844, true)
    await inspectPage(admin, appBase)
    await capture(admin, 'books-admin-mobile.png')
    await admin.setViewport(1440, 1000)

    // Manual upload, authenticated download, and delete all happen from the unified Files page.
    const manualPath = path.join(temporaryRoot, 'phase10-manual.txt')
    fs.writeFileSync(manualPath, 'phase 10 private manual handoff\n', 'utf8')
    await admin.navigate(`${appBase}/account/admin/files`)
    await admin.waitFor("document.querySelector('h1')?.textContent === '文件' && Boolean(document.querySelector('input[aria-label=\"上传手动文件\"]'))")
    await setFileInput(admin, 'input[aria-label="上传手动文件"]', manualPath)
    await admin.waitFor("document.body.textContent.includes('phase10-manual.txt 已上传。') && Boolean(document.querySelector('[aria-label=\"下载 phase10-manual.txt\"]'))")
    await clickAria(admin, '下载 phase10-manual.txt')
    await admin.waitFor("!document.querySelector('[aria-label=\"下载 phase10-manual.txt\"]')?.disabled")
    await admin.evaluate('window.confirm = () => true')
    await clickAria(admin, '删除 phase10-manual.txt')
    await admin.waitFor("document.body.textContent.includes('phase10-manual.txt 已删除。') && !document.querySelector('[aria-label=\"删除 phase10-manual.txt\"]')")

    // Issue a one-time device secret, use lifecycle controls, and upload an agent-style verified two-part file.
    await clickText(admin, '同步设备', '[role="tab"]')
    await clickText(admin, '添加设备')
    await setControl(admin, '设备名称', 'Phase 10 Browser Device')
    await clickText(admin, '创建设备')
    await admin.waitFor("document.body.textContent.includes('保存设备凭据') && Boolean(document.querySelector('.admin-files__secret code'))")
    const firstDeviceSecret = await admin.evaluate("document.querySelector('.admin-files__secret code').textContent")
    assert(firstDeviceSecret.length >= 32, 'device secret was not issued')
    await clickAria(admin, '关闭凭据窗口')
    await admin.waitFor("!document.querySelector('.admin-files__secret code') && document.body.textContent.includes('Phase 10 Browser Device')")
    await clickAria(admin, '暂停 Phase 10 Browser Device')
    await admin.waitFor("document.body.textContent.includes('Phase 10 Browser Device：暂停已完成。') && Boolean(document.querySelector('[aria-label=\"恢复 Phase 10 Browser Device\"]'))")
    await clickAria(admin, '恢复 Phase 10 Browser Device')
    await admin.waitFor("document.body.textContent.includes('Phase 10 Browser Device：恢复已完成。') && Boolean(document.querySelector('[aria-label=\"暂停 Phase 10 Browser Device\"]'))")
    await clickAria(admin, '扫描 Phase 10 Browser Device')
    await admin.waitFor("document.body.textContent.includes('Phase 10 Browser Device：扫描已完成。')")
    const heartbeat = expectOk(await api(appBase, '/api/sync/heartbeat', {
      headers: { 'X-Sync-Token': firstDeviceSecret }, method: 'POST',
    }), 'device heartbeat')
    assert.equal(heartbeat.scan_requested, true)

    const syncContent = Buffer.from('phase 10 verified agent chunk upload\n', 'utf8')
    const synced = await uploadChunks(appBase, firstDeviceSecret, 'reports/phase10-agent.txt', syncContent)
    assert.equal(synced.relative_path, 'reports/phase10-agent.txt')
    assert.equal(synced.sync_status, 'synced')
    await clickText(admin, '刷新')
    await admin.waitFor("!Array.from(document.querySelectorAll('button')).some((button) => button.textContent.includes('刷新') && button.disabled)")
    await clickText(admin, '同步文件', '[role="tab"]')
    await admin.waitFor("document.body.textContent.includes('reports/phase10-agent.txt') && document.body.textContent.includes('100%')")
    await capture(admin, 'files-synced-desktop.png')
    await clickText(admin, '同步动态', '[role="tab"]')
    await admin.waitFor("document.body.textContent.includes('更新文件') && document.body.textContent.includes('reports/phase10-agent.txt')")

    await clickText(admin, '同步设备', '[role="tab"]')
    await clickAria(admin, '更新 Phase 10 Browser Device 的凭据')
    await admin.waitFor("document.body.textContent.includes('保存设备凭据') && Boolean(document.querySelector('.admin-files__secret code'))")
    const rotatedDeviceSecret = await admin.evaluate("document.querySelector('.admin-files__secret code').textContent")
    assert.notEqual(rotatedDeviceSecret, firstDeviceSecret)
    await clickAria(admin, '关闭凭据窗口')
    const oldSecretResult = await api(appBase, '/api/sync/heartbeat', {
      headers: { 'X-Sync-Token': firstDeviceSecret }, method: 'POST',
    })
    assert.equal(oldSecretResult.status, 401, 'old rotated device secret remained valid')
    expectOk(await api(appBase, '/api/sync/heartbeat', {
      headers: { 'X-Sync-Token': rotatedDeviceSecret }, method: 'POST',
    }), 'rotated device heartbeat')
    await admin.evaluate('window.confirm = () => true')
    await clickAria(admin, '撤销 Phase 10 Browser Device')
    await admin.waitFor("document.body.textContent.includes('Phase 10 Browser Device：撤销已完成。') && document.body.textContent.includes('已撤销')")
    const revokedResult = await api(appBase, '/api/sync/heartbeat', {
      headers: { 'X-Sync-Token': rotatedDeviceSecret }, method: 'POST',
    })
    assert.equal(revokedResult.status, 401, 'revoked device secret remained valid')
    await inspectPage(admin, appBase, [firstDeviceSecret, rotatedDeviceSecret, temporaryRoot])

    // Visit every canonical administrator area that belongs to the website.
    const sections = [
      ['/account/admin', '管理总览'],
      ['/account/admin/content/homepage', '首页设置'],
      ['/account/admin/content/books', '书籍内容'],
      ['/account/admin/content/photos', '照片管理'],
      ['/account/admin/users', '用户管理'],
      ['/account/admin/rooms', '房间管理'],
      ['/account/admin/files', '文件'],
      ['/account/admin/services', '服务器状态'],
      ['/account/admin/security', '安全记录'],
    ]
    for (const [pathname, heading] of sections) {
      await admin.navigate(`${appBase}${pathname}`)
      await admin.waitFor(`document.body.textContent.includes(${JSON.stringify(heading)})`, 20000)
      await inspectPage(admin, appBase, [firstDeviceSecret, rotatedDeviceSecret, temporaryRoot])
    }
    await admin.navigate(`${appBase}/account/admin/security`)
    await admin.waitFor("document.body.textContent.includes('暂不提供网页会话清单') && document.body.textContent.includes('撤销设备')")
    await capture(admin, 'security-desktop.png')

    // Every old administrator path resolves to one canonical protected destination.
    const redirects = [
      ['/account/admin/homepage', '/account/admin/content/homepage'],
      ['/admin/users', '/account/admin/users'],
      ['/admin/rooms', '/account/admin/rooms'],
      ['/admin/photos', '/account/admin/content/photos'],
      ['/admin/files', '/account/admin/files'],
      ['/admin/agent-console', '/account/admin/services'],
      ['/tools/public-sync', '/account/admin/files'],
    ]
    for (const [legacy, canonical] of redirects) {
      await admin.navigate(`${appBase}${legacy}?phase10=legacy`)
      await admin.waitFor(`location.pathname === ${JSON.stringify(canonical)} && location.search === '?phase10=legacy'`)
    }

    // A regular member cannot enter the administrator shell and receives an explicit Chinese denial.
    await visitor.navigate(`${appBase}/account/admin/security?from=visitor`)
    await visitor.waitFor("location.pathname === '/account/admin/security' && document.body.textContent.includes('无权访问此页面')")
    assert.equal(await visitor.evaluate("document.body.textContent.includes('安全记录')"), false)

    // Mobile menu responds to keyboard activation and the two densest pages do not overflow.
    await admin.setViewport(390, 844, true)
    await admin.navigate(`${appBase}/account/admin`)
    await admin.waitFor("document.querySelector('h1')?.textContent === '管理总览'")
    await admin.evaluate("document.querySelector('[aria-label=\"打开管理导航\"]').focus()")
    await admin.send('Input.dispatchKeyEvent', { key: ' ', code: 'Space', type: 'keyDown' })
    await admin.send('Input.dispatchKeyEvent', { key: ' ', code: 'Space', type: 'keyUp' })
    await admin.waitFor("document.querySelector('[aria-label=\"关闭管理导航\"]')?.getAttribute('aria-expanded') === 'true'")
    await inspectPage(admin, appBase, [firstDeviceSecret, rotatedDeviceSecret, temporaryRoot])
    await capture(admin, 'overview-mobile.png')
    await admin.navigate(`${appBase}/account/admin/files`)
    await admin.waitFor("document.querySelector('h1')?.textContent === '文件'")
    await clickText(admin, '同步文件', '[role="tab"]')
    await admin.waitFor("document.body.textContent.includes('reports/phase10-agent.txt')")
    await inspectPage(admin, appBase, [firstDeviceSecret, rotatedDeviceSecret, temporaryRoot])
    await capture(admin, 'files-mobile.png')

    const dashboard = expectOk(await api(appBase, '/api/sync/dashboard', { token: adminAuth.access_token }), 'sync dashboard')
    assert.equal(dashboard.devices.length, 1)
    assert.equal(dashboard.files.some((item) => item.relative_path === 'reports/phase10-agent.txt'), true)
    assert.equal(dashboard.devices[0].revoked_at !== null, true)
    assert(!JSON.stringify(dashboard).includes('device_token_hash'))
    assert(!JSON.stringify(dashboard).includes(syncRoot))
    const publicCatalog = expectOk(await api(appBase, '/api/books'), 'public Books catalog')
    assert.equal(publicCatalog.books.length, 1)
    assert.equal(publicCatalog.lists[0].books.length, 1)
    assert(!JSON.stringify(publicCatalog).includes('reader_url'))
    assert(!JSON.stringify(publicCatalog).includes('reader_available'))
    assert(!JSON.stringify(publicCatalog).includes('reader_path'))

    console.log(JSON.stringify({
      books: { lists: publicCatalog.lists.length, published: publicCatalog.books.length },
      screenshots: fs.readdirSync(screenshotDir).sort(),
      sync: { devices: dashboard.devices.length, files: dashboard.files.length, revoked: true },
      viewports: ['1440x1000', '390x844'],
    }, null, 2))
  } finally {
    for (const client of clients) client.close()
    for (const process of processes.reverse()) await stopProcess(process)
    if (process.env.BLUE_ALBUM_KEEP_TEMP) {
      console.error(`Preserved browser logs at ${temporaryRoot}`)
    } else {
      fs.rmSync(temporaryRoot, { recursive: true, force: true })
      cleanupVerified = !fs.existsSync(temporaryRoot)
    }
    if (!process.env.BLUE_ALBUM_KEEP_TEMP) assert.equal(cleanupVerified, true, 'temporary profiles or storage were not removed')
  }
}


main().catch((error) => {
  console.error(error.stack || error)
  process.exitCode = 1
})
