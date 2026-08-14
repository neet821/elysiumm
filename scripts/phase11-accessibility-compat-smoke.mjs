import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'


const root = path.resolve(import.meta.dirname, '..')
const python = path.join(root, 'backend', '.venv', 'bin', 'python')
const chromeBinary = process.env.CHROME_BINARY || '/usr/bin/google-chrome-stable'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-phase11-accessibility'
const widths = [360, 390, 430, 768, 1024, 1366, 1920, 2560]
const password = 'Phase11Browser2026!'
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))


class CdpClient {
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
    if (response.exceptionDetails) {
      throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text)
    }
    return response.result.value
  }

  async waitFor(expression, timeout = 15000) {
    const deadline = Date.now() + timeout
    while (Date.now() < deadline) {
      try {
        if (await this.evaluate(expression)) return
      } catch {
        // Route transitions may briefly replace the document tree.
      }
      await sleep(80)
    }
    const state = await this.evaluate(`({ url: location.href, text: document.body?.innerText?.slice(0, 1200) || '' })`)
    throw new Error(`Timed out waiting for ${expression}: ${JSON.stringify(state)}`)
  }

  async navigate(url) {
    this.errors.length = 0
    this.failedResponses.length = 0
    await this.send('Page.navigate', { url })
    await this.waitFor("document.readyState === 'complete' && Boolean(document.querySelector('#root > *'))", 20000)
    await this.waitFor("!document.querySelector('[aria-label=\"Loading page\"]')")
    await sleep(120)
  }

  async setViewport(width, height) {
    await this.send('Emulation.setDeviceMetricsOverride', {
      deviceScaleFactor: 1,
      height,
      mobile: width <= 430,
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

  async key(key, code, modifiers = 0) {
    const keyCode = key === 'Tab' ? 9 : key === 'Enter' ? 13 : key === 'Escape' ? 27 : 0
    const text = key === 'Enter' ? '\r' : ''
    await this.send('Input.dispatchKeyEvent', {
      code,
      key,
      modifiers,
      nativeVirtualKeyCode: keyCode,
      text,
      type: text ? 'keyDown' : 'rawKeyDown',
      unmodifiedText: text,
      windowsVirtualKeyCode: keyCode,
    })
    await this.send('Input.dispatchKeyEvent', {
      code,
      key,
      modifiers,
      nativeVirtualKeyCode: keyCode,
      type: 'keyUp',
      windowsVirtualKeyCode: keyCode,
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
    await sleep(120)
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

async function chromeTarget(debugBase) {
  await waitForUrl(`${debugBase}/json/version`)
  const targets = await fetch(`${debugBase}/json/list`).then((response) => response.json())
  const target = targets.find((candidate) => candidate.type === 'page')
  assert(target?.webSocketDebuggerUrl, 'Chrome page target is unavailable')
  return target
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
  assert(response.ok, `${method} ${pathname} failed (${response.status}): ${JSON.stringify(payload)}`)
  return payload
}

async function registerAndLogin(appBase) {
  const username = 'phase11_listener'
  await api(appBase, '/api/users/register', {
    body: { email: `${username}@example.com`, password, username },
    method: 'POST',
  })
  return api(appBase, '/api/auth/login', {
    form: new URLSearchParams({ password, username }),
    method: 'POST',
  })
}

async function inspectPage(client, label) {
  const report = await client.evaluate(`(() => {
    const visible = (element) => {
      const style = getComputedStyle(element)
      const rect = element.getBoundingClientRect()
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
    }
    const name = (element) => {
      const labelledBy = element.getAttribute('aria-labelledby')
      if (labelledBy) {
        const value = labelledBy.split(/\\s+/).map((id) => document.getElementById(id)?.textContent || '').join(' ').trim()
        if (value) return value
      }
      return (element.getAttribute('aria-label') || element.getAttribute('alt') ||
        element.getAttribute('title') || element.textContent || '').trim()
    }
    const interactive = [...document.querySelectorAll('button, a[href], [role="button"]')].filter(visible)
    const controls = [...document.querySelectorAll('input, select, textarea')].filter(visible)
    const ids = [...document.querySelectorAll('[id]')].map((element) => element.id).filter(Boolean)
    const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))]
    return {
      duplicateIds,
      headingCount: document.querySelectorAll('h1').length,
      imageFailures: [...document.images].filter((image) => !image.hasAttribute('alt') && image.getAttribute('aria-hidden') !== 'true' && image.getAttribute('role') !== 'presentation').map((image) => image.src),
      mainCount: document.querySelectorAll('main').length,
      unnamedControls: controls.filter((element) => !element.labels?.length && !name(element)).map((element) => element.outerHTML.slice(0, 180)),
      unnamedInteractive: interactive.filter((element) => !name(element)).map((element) => element.outerHTML.slice(0, 180)),
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      path: location.pathname,
      title: document.title,
    }
  })()`)
  assert.equal(report.mainCount, 1, `${label} must expose exactly one main region`)
  assert(report.headingCount >= 1, `${label} must expose a page heading`)
  assert(report.overflow <= 1, `${label} has horizontal overflow: ${report.overflow}px`)
  assert.deepEqual(report.duplicateIds, [], `${label} has duplicate ids`)
  assert.deepEqual(report.imageFailures, [], `${label} has images without alt text`)
  assert.deepEqual(report.unnamedControls, [], `${label} has unnamed form controls`)
  assert.deepEqual(report.unnamedInteractive, [], `${label} has unnamed interactive controls`)
  assert.deepEqual(client.errors, [], `${label} emitted browser errors`)
  assert.deepEqual(client.failedResponses, [], `${label} returned failed requests`)
  return report
}


async function main() {
  assert(fs.existsSync(python), 'backend/.venv is required')
  assert(fs.existsSync(chromeBinary), `Chrome is unavailable: ${chromeBinary}`)
  fs.rmSync(screenshotDir, { recursive: true, force: true })
  fs.mkdirSync(screenshotDir, { recursive: true })
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'blue-album-phase11-a11y-'))
  const processes = []
  let client

  try {
    const [backendPort, frontendPort, mineradioPort, debugPort] = await Promise.all([freePort(), freePort(), freePort(), freePort()])
    const appBase = `http://127.0.0.1:${frontendPort}`
    const backendBase = `http://127.0.0.1:${backendPort}`
    const environment = {
      ...process.env,
      ADMIN_FILES_STORAGE_DIR: path.join(temporaryRoot, 'admin-files'),
      BACKUP_OUTPUT_DIR: path.join(temporaryRoot, 'backups'),
      BOOKMARK_BACKUP_OUTPUT_DIR: path.join(temporaryRoot, 'bookmark-backups'),
      CORS_ORIGINS: appBase,
      DATABASE_URL: `sqlite:///${path.join(temporaryRoot, 'acceptance.sqlite')}`,
      FRP_DRY_RUN: '1',
      FRP_ROOT: path.join(temporaryRoot, 'frp'),
      PRIVATE_STORAGE_DIR: path.join(temporaryRoot, 'private-storage'),
      PUBLIC_SYNC_STORAGE: path.join(temporaryRoot, 'sync-storage'),
      SECRET_KEY: 'phase11-accessibility-isolated-secret',
    }

    await run(python, [path.join(root, 'backend', 'run_migrations.py')], { cwd: root, env: environment })
    processes.push(startProcess(python, [
      '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(backendPort), '--log-level', 'warning',
    ], { cwd: path.join(root, 'backend'), env: environment, logPath: path.join(temporaryRoot, 'backend.log') }))
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
      },
      logPath: path.join(temporaryRoot, 'frontend.log'),
    }))
    await waitForUrl(appBase)
    processes.push(startProcess(chromeBinary, [
      '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
      '--no-first-run', '--no-default-browser-check', `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${path.join(temporaryRoot, 'chrome')}`, 'about:blank',
    ], { cwd: root, env: process.env, logPath: path.join(temporaryRoot, 'chrome.log') }))
    client = new CdpClient(await chromeTarget(`http://127.0.0.1:${debugPort}`))
    await client.connect()
    await client.setMedia('light')

    const viewportResults = []
    const screenshots = []
    for (const width of widths) {
      await client.setViewport(width, width <= 430 ? 844 : 1000)
      for (const pathname of ['/', '/books', '/login', '/register']) {
        await client.navigate(`${appBase}${pathname}`)
        viewportResults.push({ width, ...await inspectPage(client, `${width}px ${pathname}`) })
      }
      await client.navigate(`${appBase}/`)
      await client.waitFor("document.querySelector('.home-masonry-item')?.dataset.revealed === 'false'")
      const homeInitial = await client.evaluate(`(() => {
        const hero = document.querySelector('.album-hero')
        const content = document.querySelector('.home-content')
        const firstCard = document.querySelector('.home-masonry-item')
        const intro = document.querySelector('.home-content__intro')
        const topbar = document.querySelector('.album-hero__topbar')
        const layoutLeft = (element) => {
          if (!element) return null
          const rect = element.getBoundingClientRect()
          return rect.left - ((element.offsetWidth - rect.width) / 2)
        }
        return {
          branch: Boolean(document.querySelector('.album-hero__branch-shadow')),
          cardLeft: layoutLeft(firstCard),
          cardOpacity: firstCard ? Number(getComputedStyle(firstCard).opacity) : null,
          cardRevealed: firstCard?.dataset.revealed,
          contentLeft: content?.getBoundingClientRect().left,
          contentPaddingLeft: content ? getComputedStyle(content).paddingLeft : null,
          contentTop: content?.getBoundingClientRect().top,
          contentWidth: content?.getBoundingClientRect().width,
          copyVisible: Boolean(document.querySelector('.album-hero__copy h1')),
          heroBottom: hero?.getBoundingClientRect().bottom,
          heroHeight: hero?.getBoundingClientRect().height,
          heroLabel: hero?.getAttribute('aria-label'),
          introLeft: layoutLeft(intro),
          photoCount: document.querySelectorAll('.album-hero__photo').length,
          scrollLink: Boolean(document.querySelector('.album-hero__scroll[href="#home-content"]')),
          topbarPosition: topbar ? getComputedStyle(topbar).position : null,
          viewportHeight: innerHeight,
        }
      })()`)
      assert.equal(homeInitial.branch, true, `${width}px home must render the branch decoration`)
      assert.equal(homeInitial.copyVisible, true, `${width}px home must render its title`)
      assert.equal(homeInitial.photoCount, 2, `${width}px home must render two layered photos`)
      assert.equal(homeInitial.scrollLink, true, `${width}px home must link the hero to its content`)
      assert.equal(homeInitial.topbarPosition, 'absolute', `${width}px home navigation must stay inside the hero`)
      assert.equal(homeInitial.heroLabel, 'Blue Album 首页首屏', `${width}px home must expose the album hero`)
      const minimumHeroHeight = width <= 900
        ? Math.min(homeInitial.viewportHeight * 0.98, 848)
        : homeInitial.viewportHeight * 0.98
      assert(
        homeInitial.heroHeight >= minimumHeroHeight,
        `${width}px album hero must fill the first viewport: ${JSON.stringify(homeInitial)}`,
      )
      assert(
        homeInitial.contentTop >= homeInitial.heroBottom - 1,
        `${width}px lower content must follow the hero without overlap: ${JSON.stringify(homeInitial)}`,
      )
      assert(Math.abs(homeInitial.introLeft - homeInitial.cardLeft) <= 1, `${width}px introduction and cards must share one rail: ${JSON.stringify(homeInitial)}`)
      assert.equal(homeInitial.cardRevealed, 'false', `${width}px cards must initially be unrevealed`)
      assert.equal(homeInitial.cardOpacity, 0, `${width}px cards must initially be invisible`)
      await client.evaluate("document.querySelector('.home-masonry-item')?.scrollIntoView({ block: 'center' })")
      await client.waitFor("document.querySelector('.home-masonry-item')?.dataset.revealed === 'true'")
      await client.waitFor("Number(getComputedStyle(document.querySelector('.home-masonry-item')).opacity) > 0.95")
      await client.waitFor("getComputedStyle(document.querySelector('.home-masonry-item')).filter === 'blur(0px)'")
      const homeRevealed = await client.evaluate(`(() => {
        const firstCard = document.querySelector('.home-masonry-item')
        const styles = getComputedStyle(firstCard)
        return {
          filter: styles.filter,
          opacity: Number(styles.opacity),
          revealed: firstCard.dataset.revealed,
          transform: styles.transform,
        }
      })()`)
      assert.equal(homeRevealed.revealed, 'true', `${width}px first card must reveal after scrolling`)
      assert(homeRevealed.opacity > 0.95, `${width}px revealed card must be visible`)
      assert.equal(homeRevealed.filter, 'blur(0px)', `${width}px revealed card must remove blur`)
      await client.evaluate('scrollTo(0, 0)')
      await client.waitFor("document.querySelector('.home-masonry-item')?.dataset.revealed === 'false'")
      await client.waitFor("Number(getComputedStyle(document.querySelector('.home-masonry-item')).opacity) < 0.05")
      await client.evaluate("document.querySelector('.home-masonry-item')?.scrollIntoView({ block: 'center' })")
      await client.waitFor("document.querySelector('.home-masonry-item')?.dataset.revealed === 'true'")
      await client.waitFor("Number(getComputedStyle(document.querySelector('.home-masonry-item')).opacity) > 0.95")
      await client.navigate(`${appBase}/tools`)
      viewportResults.push({ width, ...await inspectPage(client, `${width}px /tools`) })
      const toolbox = await client.evaluate(`(() => ({
        cardCount: document.querySelectorAll('.toolbox-portal').length,
        hasFooter: Boolean(document.querySelector('.app-footer')),
        horizontalOverflow: document.documentElement.scrollWidth - innerWidth,
        verticalOverflow: document.documentElement.scrollHeight - innerHeight,
      }))()`)
      assert.equal(toolbox.cardCount, 3, `${width}px toolbox must show three tools`)
      assert.equal(toolbox.hasFooter, false, `${width}px toolbox must hide the global footer`)
      assert(toolbox.horizontalOverflow <= 1, `${width}px toolbox has horizontal overflow`)
      assert(toolbox.verticalOverflow <= 1, `${width}px toolbox must fit one viewport`)
      if ([390, 1366].includes(width)) {
        let shot = await client.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
        let screenshot = path.join(screenshotDir, `tools-${width}.png`)
        fs.writeFileSync(screenshot, Buffer.from(shot.data, 'base64'))
        screenshots.push(screenshot)
        await client.navigate(`${appBase}/`)
        await new Promise((resolve) => setTimeout(resolve, 1100))
        shot = await client.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
        screenshot = path.join(screenshotDir, `home-${width}-initial.png`)
        fs.writeFileSync(screenshot, Buffer.from(shot.data, 'base64'))
        screenshots.push(screenshot)
        await client.evaluate("document.querySelector('.home-masonry-item')?.scrollIntoView({ block: 'center' })")
        await client.waitFor("document.querySelector('.home-masonry-item')?.dataset.revealed === 'true'")
        await new Promise((resolve) => setTimeout(resolve, 750))
        shot = await client.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
        screenshot = path.join(screenshotDir, `home-${width}-revealed.png`)
        fs.writeFileSync(screenshot, Buffer.from(shot.data, 'base64'))
        screenshots.push(screenshot)
      }
      if ([360, 768, 1366, 2560].includes(width)) {
        await client.navigate(`${appBase}/books`)
        const shot = await client.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
        const screenshot = path.join(screenshotDir, `books-${width}.png`)
        fs.writeFileSync(screenshot, Buffer.from(shot.data, 'base64'))
        screenshots.push(screenshot)
      }
    }

    const listenerAuth = await registerAndLogin(appBase)
    const musicRoom = await api(appBase, '/api/sync-rooms', {
      body: { mode: 'music', room_name: 'Mineradio 浏览器验收房' },
      method: 'POST',
      token: listenerAuth.access_token,
    })
    await client.navigate(`${appBase}/login`)
    await client.evaluate(`(() => {
      localStorage.setItem('token', ${JSON.stringify(listenerAuth.access_token)})
      localStorage.setItem('refresh_token', ${JSON.stringify(listenerAuth.refresh_token)})
      localStorage.setItem('user', ${JSON.stringify(JSON.stringify(listenerAuth.user))})
    })()`)
    await client.navigate(`${appBase}/account`)
    await client.waitFor("document.body.textContent.includes('个人信息')")
    const accountCollectionEntry = await client.evaluate(`(() => ({
      hasDescription: document.body.textContent.includes('管理私人文件夹、公开收藏、访问记录和个人起始页'),
      hasEntry: Array.from(document.querySelectorAll('button, a')).some((element) => element.textContent.includes('打开我的收藏')),
    }))()`)
    assert.equal(accountCollectionEntry.hasDescription, false, 'account page must remove the duplicate collection description')
    assert.equal(accountCollectionEntry.hasEntry, false, 'account page must remove the duplicate collection entry')
    for (const width of widths) {
      await client.setViewport(width, width <= 430 ? 844 : 1000)
      await client.navigate(`${appBase}/music/rooms/${musicRoom.id}`)
      await client.waitFor("Boolean(document.querySelector('iframe[title=\"Mineradio 原版房间播放器\"]'))")
      await client.waitFor("document.querySelector('iframe')?.contentDocument?.body.classList.contains('blue-album-room-mode')", 30000)
      await client.waitFor("document.querySelector('iframe')?.contentDocument?.querySelector('#blue-room-panel')?.classList.contains('show') && document.querySelector('iframe')?.contentDocument?.querySelector('#br-title')?.textContent === 'Mineradio 浏览器验收房'", 30000)
      await client.waitFor("document.querySelector('iframe')?.contentDocument?.querySelector('#splash')?.classList.contains('hide')", 5000)
      viewportResults.push({ width, ...await inspectPage(client, `${width}px Mineradio 听歌房`) })
      const immersive = await client.evaluate(`(() => ({
        hasFooter: Boolean(document.querySelector('.app-footer')),
        hasHeader: Boolean(document.querySelector('.app-header')),
        iframeCount: document.querySelectorAll('iframe[title="Mineradio 原版房间播放器"]').length,
        horizontalOverflow: document.documentElement.scrollWidth - innerWidth,
        verticalOverflow: document.documentElement.scrollHeight - innerHeight,
      }))()`)
      assert.equal(immersive.hasFooter, false, `${width}px Mineradio room must hide the global footer`)
      assert.equal(immersive.hasHeader, false, `${width}px Mineradio room must hide the global header`)
      assert.equal(immersive.iframeCount, 1, `${width}px Mineradio room must embed exactly one original player`)
      assert(immersive.horizontalOverflow <= 1, `${width}px Mineradio room has horizontal overflow`)
      assert(immersive.verticalOverflow <= 1, `${width}px Mineradio room must fill one viewport`)
      if ([390, 1366].includes(width)) {
        const shot = await client.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
        const screenshot = path.join(screenshotDir, `mineradio-${width}.png`)
        fs.writeFileSync(screenshot, Buffer.from(shot.data, 'base64'))
        screenshots.push(screenshot)
      }
    }

    await client.setViewport(1366, 900)
    for (const pathname of ['/archive', '/collection']) {
      await client.navigate(`${appBase}${pathname}`)
      viewportResults.push({ width: 1366, ...await inspectPage(client, `1366px ${pathname}`) })
    }

    await client.setViewport(390, 844)
    await client.navigate(`${appBase}/books`)
    await client.evaluate("document.querySelector('.skip-link').focus()")
    assert.equal(await client.evaluate("document.activeElement?.textContent?.trim()"), '跳到主要内容')
    await client.key('Enter', 'Enter')
    await client.waitFor("location.hash === '#main-content'")
    assert.equal(await client.evaluate("document.activeElement?.id"), 'main-content', 'skip link must focus the main region')

    await client.evaluate("document.querySelector('[aria-label=\"打开导航\"]').focus()")
    await client.key('Enter', 'Enter')
    await client.waitFor("Boolean(document.querySelector('[role=\"dialog\"]'))")
    const dialogState = await client.evaluate(`(() => {
      const dialog = document.querySelector('[role="dialog"]')
      const button = document.querySelector('[aria-label="打开导航"]')
      const rect = button.getBoundingClientRect()
      return { activeInside: dialog.contains(document.activeElement), height: rect.height, modal: dialog.getAttribute('aria-modal'), width: rect.width }
    })()`)
    assert.equal(dialogState.activeInside, true, 'mobile navigation must move focus into the dialog')
    assert.equal(dialogState.modal, 'true')
    assert(dialogState.width >= 44 && dialogState.height >= 44, 'mobile navigation control must be at least 44px')
    await client.key('Escape', 'Escape')
    await client.waitFor("!document.querySelector('[role=\"dialog\"]')")
    assert.equal(await client.evaluate("document.activeElement?.getAttribute('aria-label')"), '打开导航')

    await client.setViewport(1366, 900)
    await client.setMedia('light', 'reduce')
    await client.navigate(`${appBase}/`)
    const reducedMotion = await client.evaluate(`(() => ({
      matches: matchMedia('(prefers-reduced-motion: reduce)').matches,
      motionNormal: getComputedStyle(document.documentElement).getPropertyValue('--motion-normal').trim(),
      animated: [...document.querySelectorAll('body *')].filter((element) => {
        const style = getComputedStyle(element)
        return element.getClientRects().length && style.animationName !== 'none' &&
          style.animationPlayState !== 'paused' && parseFloat(style.animationDuration) > 0.01
      }).map((element) => ({ className: element.className, name: getComputedStyle(element).animationName })).slice(0, 10),
    }))()`)
    assert.equal(reducedMotion.matches, true)
    assert.equal(reducedMotion.motionNormal, '0ms')
    assert.deepEqual(reducedMotion.animated, [], 'reduced-motion mode must stop visible animations')

    await client.evaluate("localStorage.removeItem('blue-album-theme')")
    await client.setMedia('dark')
    await client.navigate(`${appBase}/books`)
    assert.equal(await client.evaluate("document.documentElement.classList.contains('dark')"), true, 'dark system fallback must be honored')
    await client.evaluate("localStorage.removeItem('blue-album-theme')")
    await client.setMedia('light')
    await client.navigate(`${appBase}/books`)
    assert.equal(await client.evaluate("document.documentElement.classList.contains('dark')"), false, 'light system fallback must be honored')
    await client.key('Tab', 'Tab')
    assert.equal(await client.evaluate("document.activeElement?.classList.contains('skip-link')"), true)
    const focusStyle = await client.evaluate(`(() => {
      const style = getComputedStyle(document.activeElement)
      return { style: style.outlineStyle, width: parseFloat(style.outlineWidth) }
    })()`)
    assert.notEqual(focusStyle.style, 'none', 'keyboard focus must remain visible')
    assert(focusStyle.width >= 1, 'keyboard focus outline must have visible width')

    const unexpectedRequests = client.requests.filter((url) => {
      if (url.startsWith(appBase) || url.startsWith('data:') || url.startsWith('blob:')) return false
      if (url.startsWith(`ws://127.0.0.1:${frontendPort}`)) return false
      if (url.startsWith('https://fonts.googleapis.com/') || url.startsWith('https://fonts.gstatic.com/')) return false
      return true
    })
    assert.deepEqual(unexpectedRequests, [], 'browser acceptance must not contact third parties')
    assert.deepEqual(client.errors, [], 'final browser page emitted errors')
    assert.deepEqual(client.failedResponses, [], 'final browser page returned failed requests')

    console.log(JSON.stringify({
      browser: await client.evaluate('navigator.userAgent'),
      realEngine: 'Chrome via CDP',
      screenshots,
      sourceOnlyCompatibility: ['Firefox', 'WebKit'],
      viewportChecks: viewportResults.length,
      widths,
    }, null, 2))
  } finally {
    client?.close()
    for (const process of processes.reverse()) await stopProcess(process)
    fs.rmSync(temporaryRoot, { recursive: true, force: true })
  }
}


main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
