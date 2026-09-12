import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import fs from 'node:fs'
import net from 'node:net'
import path from 'node:path'

const require = createRequire(path.join(path.resolve(import.meta.dirname, '..'), 'frontend', 'package.json'))
const { WebSocket: NodeWebSocket } = require('ws')
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

export class CdpClient {
  constructor(target, label) {
    this.label = label
    this.target = target
    this.nextId = 1
    this.pending = new Map()
    this.errors = []
    this.requests = []
    this.failedResponses = []
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
        this.errors.push(message.params.args.map((argument) => argument.value ?? argument.description ?? '').join(' '))
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
    if (response.exceptionDetails) {
      throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text)
    }
    return response.result.value
  }

  async waitFor(expression, timeout = 15000) {
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
    const state = await this.evaluate(`({ url: location.href, text: document.body?.innerText?.slice(0, 1200) || '' })`)
    throw new Error(`${this.label} timed out: ${expression}; state=${JSON.stringify(state)}${lastError ? `; last=${lastError.message}` : ''}`)
  }

  async navigate(url) {
    this.errors.length = 0
    this.requests.length = 0
    this.failedResponses.length = 0
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

  async setMedia(colorScheme, reducedMotion = 'no-preference') {
    await this.send('Emulation.setEmulatedMedia', {
      features: [
        { name: 'prefers-color-scheme', value: colorScheme },
        { name: 'prefers-reduced-motion', value: reducedMotion },
      ],
    })
  }

  async key(key, code = key) {
    const keyCode = key === 'Tab' ? 9 : key === 'Enter' ? 13 : key === 'Escape' ? 27 : 0
    const text = key === 'Enter' ? '\r' : ''
    await this.send('Input.dispatchKeyEvent', {
      code,
      key,
      nativeVirtualKeyCode: keyCode,
      text,
      type: text ? 'keyDown' : 'rawKeyDown',
      unmodifiedText: text,
      windowsVirtualKeyCode: keyCode,
    })
    await this.send('Input.dispatchKeyEvent', {
      code,
      key,
      nativeVirtualKeyCode: keyCode,
      type: 'keyUp',
      windowsVirtualKeyCode: keyCode,
    })
  }

  close() {
    this.socket?.close()
  }
}

export async function freePort() {
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

export async function waitForUrl(url, timeout = 30000) {
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
    await sleep(120)
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError?.message || 'unknown error'}`)
}

export function run(command, args, options = {}) {
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

export function startProcess(command, args, { cwd, env, logPath }) {
  const log = fs.openSync(logPath, 'a')
  const child = spawn(command, args, { cwd, env, stdio: ['ignore', log, log] })
  child.once('exit', () => fs.closeSync(log))
  return child
}

export async function stopProcess(child) {
  if (!child || child.exitCode !== null) return
  child.kill('SIGTERM')
  await Promise.race([
    new Promise((resolve) => child.once('exit', resolve)),
    sleep(3000),
  ])
  if (child.exitCode === null) child.kill('SIGKILL')
}

export async function api(base, pathname, { body, form, method = 'GET', token } = {}) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  const requestBody = form || (body === undefined ? undefined : (() => {
    headers['Content-Type'] = 'application/json'
    return JSON.stringify(body)
  })())
  const response = await fetch(`${base}${pathname}`, { body: requestBody, headers, method })
  const text = await response.text()
  let payload = text
  try { payload = text ? JSON.parse(text) : null } catch { /* Keep plain text for diagnostics. */ }
  return { ok: response.ok, payload, status: response.status }
}

export function expectOk(result, label) {
  if (!result.ok) throw new Error(`${label} failed (${result.status}): ${JSON.stringify(result.payload)}`)
  return result.payload
}

export async function registerAndLogin(base, username, password) {
  expectOk(await api(base, '/api/users/register', {
    body: { email: `${username}@example.com`, password, username },
    method: 'POST',
  }), `register ${username}`)
  return expectOk(await api(base, '/api/auth/login', {
    form: new URLSearchParams({ password, username }),
    method: 'POST',
  }), `login ${username}`)
}

export async function authenticatePage(page, base, auth) {
  await page.navigate(`${base}/login`)
  await page.evaluate(`(() => {
    localStorage.setItem('token', ${JSON.stringify(auth.access_token)})
    localStorage.setItem('refresh_token', ${JSON.stringify(auth.refresh_token)})
    localStorage.setItem('user', ${JSON.stringify(JSON.stringify(auth.user))})
  })()`)
}

export async function chromeTarget(debugBase) {
  await waitForUrl(`${debugBase}/json/version`)
  const targets = await fetch(`${debugBase}/json/list`).then((response) => response.json())
  const target = targets.find((candidate) => candidate.type === 'page')
  if (!target?.webSocketDebuggerUrl) throw new Error(`No Chrome page target at ${debugBase}`)
  return target
}

export async function clickText(page, text, selector = 'button') {
  const result = await page.evaluate(`(() => {
    const element = [...document.querySelectorAll(${JSON.stringify(selector)})]
      .find((candidate) => candidate.textContent.trim().includes(${JSON.stringify(text)}))
    if (!element) return { found: false }
    if (element.disabled) return { disabled: true, found: true }
    element.click()
    return { disabled: false, found: true }
  })()`)
  if (!result.found) throw new Error(`${page.label} is missing ${selector} containing ${text}`)
  if (result.disabled) throw new Error(`${page.label} has disabled ${selector} containing ${text}`)
}

export async function fillInput(page, selector, value) {
  const found = await page.evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)})
    if (!element) return false
    const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, ${JSON.stringify(value)})
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  })()`)
  if (!found) throw new Error(`${page.label} is missing input ${selector}`)
}

export async function capture(page, screenshotDir, filename) {
  fs.mkdirSync(screenshotDir, { recursive: true })
  const shot = await page.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
  const output = path.join(screenshotDir, filename)
  fs.writeFileSync(output, Buffer.from(shot.data, 'base64'))
  return output
}

export function localOnlyRequests(requests, appBase) {
  return requests.filter((url) => (
    !url.startsWith(appBase)
    && !url.startsWith('data:')
    && !url.startsWith('blob:')
    && !url.startsWith('ws://127.0.0.1:')
    && !url.startsWith('wss://127.0.0.1:')
    && !url.startsWith('https://fonts.googleapis.com/')
    && !url.startsWith('https://fonts.gstatic.com/')
  ))
}
