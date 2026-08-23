import assert from 'node:assert/strict'
import fs from 'node:fs'

const debugBase = process.env.CHROME_DEBUG_URL || 'http://127.0.0.1:9224'
const appBase = process.env.BLUE_ALBUM_URL || 'http://127.0.0.1:5173'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp'

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

  async waitFor(expression, timeout = 10000) {
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
  }

  close() {
    this.socket.close()
  }
}

let activeClient

async function setViewport(client, width, height, mobile) {
  await client.send('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
  })
}

async function loadHomepage(client, theme) {
  await client.evaluate(`localStorage.setItem('theme', ${JSON.stringify(theme)})`)
  await client.navigate('/')
  await client.waitFor("Boolean(document.querySelector('.home-masonry-grid'))")
  await sleep(1100)
}

async function inspectHomepage(client) {
  return client.evaluate(`(() => {
    const rect = (selector) => {
      const value = document.querySelector(selector)?.getBoundingClientRect()
      return value ? { top: value.top, left: value.left, right: value.right, bottom: value.bottom, width: value.width, height: value.height } : null
    }
    const hero = document.querySelector('.home-hero--classic')
    const stage = document.querySelector('.home-stage')
    const stageBefore = getComputedStyle(stage, '::before')
    const stageAfter = getComputedStyle(stage, '::after')
    return {
      width: innerWidth,
      height: innerHeight,
      theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
      hero: rect('.home-hero--classic'),
      intro: rect('.home-content__intro'),
      grid: rect('.home-editorial-grid'),
      prefix: document.querySelector('.text-line-one')?.textContent?.trim(),
      title: document.querySelector('.blue-mark')?.textContent?.trim(),
      german: document.querySelector('.hero-subtitle')?.textContent?.trim(),
      originalGeometry: Boolean(document.querySelector('.hero-geometry .album-widget .album-disc')),
      contentItems: Array.from(document.querySelectorAll('.home-masonry-item')).map((node) => ({
        width: node.getBoundingClientRect().width,
        height: node.getBoundingClientRect().height,
      })),
      backgroundImage: getComputedStyle(stage).backgroundImage,
      backgroundLinesHidden: stageBefore.content === 'none' && stageAfter.content === 'none',
      overflow: document.documentElement.scrollWidth - innerWidth,
      oldCopyPresent: /Explore Archive|Selected Moments/.test(document.body.innerText),
      heroState: hero?.dataset.scrollState,
    }
  })()`)
}

async function verifyScrollReversal(client) {
  await client.evaluate('scrollTo({ top: 0, behavior: "instant" })')
  await sleep(120)
  const initial = await client.evaluate(`(() => ({
    opacity: Number(getComputedStyle(document.querySelector('.text-line-one')).opacity),
    germanOpacity: Number(getComputedStyle(document.querySelector('.hero-subtitle')).opacity),
    y: scrollY,
  }))()`)

  await client.evaluate('scrollTo({ top: 280, behavior: "instant" })')
  await sleep(800)
  const progressed = await client.evaluate(`(() => ({
    opacity: Number(getComputedStyle(document.querySelector('.text-line-one')).opacity),
    germanOpacity: Number(getComputedStyle(document.querySelector('.hero-subtitle')).opacity),
    y: scrollY,
  }))()`)

  await client.evaluate('scrollTo({ top: 0, behavior: "instant" })')
  await sleep(800)
  const restored = await client.evaluate(`(() => ({
    opacity: Number(getComputedStyle(document.querySelector('.text-line-one')).opacity),
    germanOpacity: Number(getComputedStyle(document.querySelector('.hero-subtitle')).opacity),
    y: scrollY,
  }))()`)

  assert(initial.opacity > 0.95, `Hero prefix is not initially visible: ${initial.opacity}`)
  assert(progressed.y >= 260, `Homepage did not scroll to the test position: ${progressed.y}`)
  assert(progressed.opacity < 0.1, `Hero prefix did not leave while scrolling down: ${progressed.opacity}`)
  assert(restored.y === 0, `Homepage did not return to the top: ${restored.y}`)
  assert(restored.opacity > 0.95, `Hero prefix did not return while scrolling up: ${restored.opacity}`)
  assert(progressed.germanOpacity > 0.9, `German line did not appear while scrolling: ${progressed.germanOpacity}`)
  assert(restored.germanOpacity < 0.1, `German line did not hide after returning: ${restored.germanOpacity}`)

  return { initial, progressed, restored }
}

async function capture(client, filename) {
  const shot = await client.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
  const path = `${screenshotDir}/${filename}`
  fs.writeFileSync(path, Buffer.from(shot.data, 'base64'))
  return path
}

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
  await client.navigate('/')
  await client.send('Storage.clearDataForOrigin', { origin: appBase, storageTypes: 'local_storage' })

  const results = []
  const screenshots = []
  const backgrounds = new Map()
  for (const width of [1366, 1920, 2560]) {
    await setViewport(client, width, 900, false)
    for (const theme of ['light', 'dark']) {
      pageErrors.length = 0
      await loadHomepage(client, theme)
      const state = await inspectHomepage(client)

      assert.equal(state.theme, theme)
      assert.equal(state.prefix, 'Hello, this is')
      assert.equal(state.title, 'Blue Album.')
      assert.equal(state.german, 'Wovon man nicht sprechen kann, darüber muss man schweigen.')
      assert(state.hero.height >= 600, `${width}px restored Hero is too short: ${state.hero.height}px`)
      assert(state.intro.top >= state.hero.bottom - 1, `${width}px introduction overlaps the restored Hero`)
      assert.equal(state.oldCopyPresent, false)
      assert(state.overflow <= 1, `${width}px ${theme} homepage overflows horizontally by ${state.overflow}px`)
      assert(state.backgroundImage && state.backgroundImage !== 'none', `${width}px ${theme} background art is missing`)
      assert.equal(state.backgroundLinesHidden, true, `${width}px ${theme} background lines are still rendered`)
      assert.equal(state.originalGeometry, true, `${width}px ${theme} original record geometry is missing`)
      assert.deepEqual(pageErrors, [], `${width}px ${theme} homepage emitted browser errors`)

      backgrounds.set(`${width}-${theme}`, state.backgroundImage)
      const scroll = width === 1920 && theme === 'light' ? await verifyScrollReversal(client) : undefined
      results.push({ ...state, scroll })

      if (width === 1920) {
        screenshots.push(await capture(client, `blue-album-phase3-desktop-${theme}.png`))
        await client.evaluate("scrollTo({ top: Math.max(0, document.querySelector('.home-content__intro').offsetTop - 80), behavior: 'instant' })")
        await sleep(120)
        screenshots.push(await capture(client, `blue-album-phase3-desktop-content-${theme}.png`))
        await client.evaluate('scrollTo({ top: 0, behavior: "instant" })')
      }
    }
    assert.notEqual(
      backgrounds.get(`${width}-light`),
      backgrounds.get(`${width}-dark`),
      `${width}px light and dark background art are identical`,
    )
  }

  await setViewport(client, 390, 844, true)
  for (const theme of ['light', 'dark']) {
    pageErrors.length = 0
    await loadHomepage(client, theme)
    const state = await inspectHomepage(client)
    assert.equal(state.theme, theme)
    assert(state.hero.height >= 500, `390px restored Hero is too short: ${state.hero.height}px`)
    assert(state.intro.top >= state.hero.bottom - 1, '390px introduction overlaps the restored Hero')
    assert(state.contentItems.every((card) => card.width >= 340), 'Mobile homepage cards are not full-width')
    assert(state.overflow <= 1, `390px ${theme} homepage overflows horizontally by ${state.overflow}px`)
    assert.equal(state.backgroundLinesHidden, true, `390px ${theme} background lines are still rendered`)
    assert.equal(state.originalGeometry, true, `390px ${theme} original record geometry is missing`)
    assert.deepEqual(pageErrors, [], `390px ${theme} homepage emitted browser errors`)

    backgrounds.set(`390-${theme}`, state.backgroundImage)
    results.push(state)
    screenshots.push(await capture(client, `blue-album-phase3-mobile-${theme}.png`))
    await client.evaluate("scrollTo({ top: Math.max(0, document.querySelector('.home-content__intro').offsetTop - 80), behavior: 'instant' })")
    await sleep(120)
    screenshots.push(await capture(client, `blue-album-phase3-mobile-content-${theme}.png`))
    await client.evaluate('scrollTo({ top: 0, behavior: "instant" })')
  }
  assert.notEqual(backgrounds.get('390-light'), backgrounds.get('390-dark'), 'Mobile light and dark background art are identical')

  client.close()
  activeClient = null
  console.log(JSON.stringify({ results, screenshots }, null, 2))
}

main().catch((error) => {
  activeClient?.close()
  console.error(error)
  process.exitCode = 1
})
