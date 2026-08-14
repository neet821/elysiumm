import assert from 'node:assert/strict'
import fs from 'node:fs'

const debugBase = process.env.CHROME_DEBUG_URL || 'http://127.0.0.1:9223'
const appBase = process.env.BLUE_ALBUM_URL || 'http://127.0.0.1:5173'

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

class CdpClient {
  constructor(url) {
    this.url = url
    this.nextId = 1
    this.pending = new Map()
    this.waiters = new Map()
  }

  async connect() {
    this.socket = new WebSocket(this.url)
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

      const waiters = this.waiters.get(message.method) || []
      this.waiters.delete(message.method)
      for (const resolve of waiters) resolve(message.params)
      this.onEvent?.(message.method, message.params)
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
      this.pending.set(id, { resolve, reject })
      this.socket.send(JSON.stringify({ id, method, params }))
    })
  }

  once(method, timeout = 10000) {
    return Promise.race([
      new Promise((resolve) => {
        const waiters = this.waiters.get(method) || []
        waiters.push(resolve)
        this.waiters.set(method, waiters)
      }),
      new Promise((_, reject) => setTimeout(() => reject(new Error(`Timed out waiting for ${method}`)), timeout)),
    ])
  }

  async evaluate(expression) {
    const response = await this.send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    })
    if (response.exceptionDetails) {
      throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text)
    }
    return response.result.value
  }

  async waitFor(expression, timeout = 7000) {
    const deadline = Date.now() + timeout
    while (Date.now() < deadline) {
      if (await this.evaluate(expression)) return
      await sleep(80)
    }
    throw new Error(`Timed out waiting for expression: ${expression}`)
  }

  async navigate(pathname) {
    const loaded = this.once('Page.loadEventFired')
    await this.send('Page.navigate', { url: `${appBase}${pathname}` })
    await loaded
    await this.waitFor("document.readyState === 'complete' && Boolean(document.querySelector('#root > *'))")
    await sleep(450)
  }

  async click(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y })
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', button: 'left', clickCount: 1, x, y })
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', button: 'left', clickCount: 1, x, y })
  }

  async key(key, code, windowsVirtualKeyCode) {
    const params = { key, code, windowsVirtualKeyCode, nativeVirtualKeyCode: windowsVirtualKeyCode }
    const text = key === 'Enter' ? '\r' : ''
    await this.send('Input.dispatchKeyEvent', {
      type: text ? 'keyDown' : 'rawKeyDown',
      text,
      unmodifiedText: text,
      ...params,
    })
    await this.send('Input.dispatchKeyEvent', { type: 'keyUp', ...params })
  }

  close() {
    this.socket.close()
  }
}

let activeClient

async function main() {
  const targets = await fetch(`${debugBase}/json/list`).then((response) => response.json())
  const target = targets.find((candidate) => candidate.type === 'page')
  assert(target?.webSocketDebuggerUrl, 'Chrome page target is unavailable')

  const client = new CdpClient(target.webSocketDebuggerUrl)
  activeClient = client
  const pageErrors = []
  client.onEvent = (method, params) => {
    if (method === 'Runtime.exceptionThrown') {
      pageErrors.push(params.exceptionDetails.exception?.description || params.exceptionDetails.text)
    }
    if (method === 'Runtime.consoleAPICalled' && params.type === 'error') {
      pageErrors.push(params.args.map((argument) => argument.value || argument.description).join(' '))
    }
  }

  await client.connect()
  await client.send('Page.enable')
  await client.send('Runtime.enable')
  await client.send('Network.enable')
  await client.send('Storage.clearDataForOrigin', { origin: appBase, storageTypes: 'local_storage' })

  await client.send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await client.send('Emulation.setEmulatedMedia', {
    features: [
      { name: 'prefers-color-scheme', value: 'light' },
      { name: 'prefers-reduced-motion', value: 'no-preference' },
    ],
  })

  const desktop = []
  for (const pathname of ['/', '/archive', '/collection', '/books', '/account', '/music']) {
    pageErrors.length = 0
    await client.navigate(pathname)
    const state = await client.evaluate(`(() => ({
      requested: ${JSON.stringify(pathname)},
      pathname: location.pathname,
      heading: document.querySelector('h1')?.textContent?.trim() || '',
      logo: document.querySelector('.brand-logo img')?.getAttribute('alt') || '',
      nav: Array.from(document.querySelectorAll('[aria-label="Primary navigation"] a')).map((node) => node.textContent.trim()),
      overflow: document.documentElement.scrollWidth - window.innerWidth
    }))()`)
    assert.equal(state.logo, 'Blue Album')
    assert.deepEqual(state.nav, ['Archive', 'Collection', 'Music', 'Books', 'Account'])
    assert(state.overflow <= 1, `${pathname} has horizontal overflow: ${state.overflow}px`)
    if (pathname === '/account' || pathname === '/music') assert.equal(state.pathname, '/login')
    else assert.equal(state.pathname, pathname)
    assert.deepEqual(pageErrors, [], `${pathname} emitted browser errors`)
    desktop.push(state)
  }

  await client.navigate('/books')
  const themeButton = await client.evaluate(`(() => {
    const button = document.querySelector('[aria-label="Switch to dark theme"]')
    const rect = button.getBoundingClientRect()
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
  })()`)
  await client.click(themeButton.x, themeButton.y)
  await client.waitFor("document.documentElement.classList.contains('dark')")
  const themeState = await client.evaluate(`(() => ({
    dark: document.documentElement.classList.contains('dark'),
    x: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--theme-origin-x')),
    y: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--theme-origin-y'))
  }))()`)
  assert.equal(themeState.dark, true)
  assert(Math.abs(themeState.x - themeButton.x) < 1)
  assert(Math.abs(themeState.y - themeButton.y) < 1)
  await sleep(850)

  const desktopShot = await client.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
  fs.writeFileSync('/tmp/blue-album-phase2-desktop.png', Buffer.from(desktopShot.data, 'base64'))

  await client.send('Emulation.setDeviceMetricsOverride', {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: true,
  })
  await client.navigate('/books')
  const mobileButton = await client.evaluate(`(() => {
    const button = document.querySelector('[aria-label="Open navigation"]')
    const rect = button.getBoundingClientRect()
    window.__blueAlbumMenuEvents = []
    for (const type of ['keydown', 'keyup', 'click']) {
      button.addEventListener(type, (event) => window.__blueAlbumMenuEvents.push({ type, key: event.key, trusted: event.isTrusted }))
    }
    button.focus()
    return { active: document.activeElement === button, height: rect.height, width: rect.width }
  })()`)
  assert(mobileButton.width >= 44 && mobileButton.height >= 44, 'mobile menu control is smaller than 44px')
  await client.key('Enter', 'Enter', 13)
  await sleep(200)
  const menuDiagnostic = await client.evaluate(`(() => ({
    active: document.activeElement?.getAttribute('aria-label'),
    events: window.__blueAlbumMenuEvents,
    open: Boolean(document.querySelector('.ui-drawer[role="dialog"]'))
  }))()`)
  if (!menuDiagnostic.open) throw new Error(`Keyboard menu diagnostic: ${JSON.stringify(menuDiagnostic)}`)
  await client.waitFor(`Boolean(document.querySelector('.ui-drawer[role="dialog"]'))`)
  const drawerState = await client.evaluate(`(() => {
    const drawer = document.querySelector('.ui-drawer[role="dialog"]')
    return {
      modal: drawer?.getAttribute('aria-modal'),
      overflow: document.documentElement.scrollWidth - window.innerWidth
    }
  })()`)
  assert.equal(drawerState.modal, 'true')
  assert(drawerState.overflow <= 1, `mobile drawer has horizontal overflow: ${drawerState.overflow}px`)
  await client.key('Escape', 'Escape', 27)
  await client.waitFor(`!document.querySelector('.ui-drawer[role="dialog"]')`)
  assert.equal(await client.evaluate("document.activeElement?.getAttribute('aria-label')"), 'Open navigation')

  const mobileShot = await client.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
  fs.writeFileSync('/tmp/blue-album-phase2-mobile.png', Buffer.from(mobileShot.data, 'base64'))
  assert.deepEqual(pageErrors, [], 'mobile smoke emitted browser errors')

  client.close()
  activeClient = null
  console.log(JSON.stringify({ desktop, themeState, mobile: mobileButton, screenshots: [
    '/tmp/blue-album-phase2-desktop.png',
    '/tmp/blue-album-phase2-mobile.png',
  ] }, null, 2))
}

main().catch((error) => {
  activeClient?.close()
  console.error(error)
  process.exitCode = 1
})
