import assert from 'node:assert/strict'
import fs from 'node:fs'

const debugBase = process.env.CHROME_DEBUG_URL || 'http://127.0.0.1:9225'
const appBase = process.env.BLUE_ALBUM_URL || 'http://127.0.0.1:15175'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-phase5-browser'

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
      waiters.forEach((resolve) => resolve(message.params))
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
      this.pending.set(id, { reject, resolve })
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

  async evaluate(expression, options = {}) {
    const response = await this.send('Runtime.evaluate', {
      awaitPromise: true,
      expression,
      returnByValue: true,
      userGesture: Boolean(options.userGesture),
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

async function setViewport(client, width, height, mobile) {
  await client.send('Emulation.setDeviceMetricsOverride', {
    deviceScaleFactor: 1,
    height,
    mobile,
    width,
  })
}

async function setReducedMotion(client, enabled) {
  await client.send('Emulation.setEmulatedMedia', {
    features: [{ name: 'prefers-reduced-motion', value: enabled ? 'reduce' : 'no-preference' }],
  })
}

async function capture(client, filename) {
  fs.mkdirSync(screenshotDir, { recursive: true })
  const shot = await client.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
  const outputPath = `${screenshotDir}/${filename}`
  fs.writeFileSync(outputPath, Buffer.from(shot.data, 'base64'))
  return outputPath
}

async function clickSelector(client, selector) {
  const point = await client.evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)})
    if (!element) return null
    element.scrollIntoView({ block: 'center', inline: 'center' })
    const rect = element.getBoundingClientRect()
    const x = rect.left + rect.width / 2
    const y = rect.top + rect.height / 2
    const hit = document.elementFromPoint(x, y)
    return {
      disabled: Boolean(element.disabled),
      height: rect.height,
      hitClass: hit?.className || null,
      hitTag: hit?.tagName || null,
      width: rect.width,
      x,
      y,
    }
  })()`)
  assert(point, `Cannot click missing selector: ${selector}`)
  await client.send('Input.dispatchMouseEvent', { button: 'left', clickCount: 1, type: 'mousePressed', x: point.x, y: point.y })
  await client.send('Input.dispatchMouseEvent', { button: 'left', clickCount: 1, type: 'mouseReleased', x: point.x, y: point.y })
  return point
}

async function inspectPlayer(client) {
  return client.evaluate(`(() => {
    const root = document.querySelector('.standalone-player-route')
    const stage = document.querySelector('.player-stage')
    const audio = stage?.querySelector('audio')
    const play = stage?.querySelector('.player-stage__play')
    const ranges = Array.from(stage?.querySelectorAll('input[type="range"]') || [])
    const particle = stage?.querySelector('.player-particle')
    const orbit = stage?.querySelector('.player-stage__orbit')
    const lyric = stage?.querySelector('.player-stage__lyrics p')
    return {
      audioIsLocal: Boolean(audio?.src.startsWith('data:audio/wav;base64,')),
      hasIframe: Boolean(document.querySelector('iframe')),
      height: innerHeight,
      lyricTransition: lyric ? getComputedStyle(lyric).transitionDuration : null,
      orbitAnimation: orbit ? getComputedStyle(orbit).animationName : null,
      overflow: document.documentElement.scrollWidth - innerWidth,
      particleAnimation: particle ? getComputedStyle(particle).animationName : null,
      particles: stage?.querySelectorAll('.player-particle').length || 0,
      pathname: location.pathname,
      playTarget: play?.getBoundingClientRect().height || 0,
      rangesFit: ranges.every((range) => range.getBoundingClientRect().height >= 44),
      state: stage?.dataset.playerState,
      theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
      width: innerWidth,
      rootPresent: Boolean(root),
    }
  })()`)
}

async function exercisePlayback(client) {
  await client.evaluate(`(() => {
    const audio = document.querySelector('.player-stage audio')
    window.__phase5AudioEvents = []
    for (const eventName of ['play', 'pause', 'seeked', 'timeupdate', 'ended', 'error']) {
      audio.addEventListener(eventName, () => window.__phase5AudioEvents.push(eventName))
    }
  })()`)

  const playClick = await clickSelector(client, '.player-stage__play')
  await sleep(800)
  const afterPlay = await client.evaluate(`(() => {
    const audio = document.querySelector('.player-stage audio')
    return {
      alert: document.querySelector('.player-stage__error')?.textContent || null,
      events: window.__phase5AudioEvents,
      paused: audio?.paused,
      readyState: audio?.readyState,
      stageState: document.querySelector('.player-stage')?.dataset.playerState,
      status: document.querySelector('.player-stage__status')?.textContent || null,
    }
  })()`)
  assert.equal(afterPlay.stageState, 'playing', `Play click failed: ${JSON.stringify({ afterPlay, playClick })}`)
  await client.waitFor("window.__phase5AudioEvents.includes('timeupdate')", 5000)

  await clickSelector(client, '.player-stage__play')
  await client.waitFor("document.querySelector('.player-stage')?.dataset.playerState === 'paused'", 5000)

  await client.evaluate(`(() => {
    const audio = document.querySelector('.player-stage audio')
    audio.currentTime = 2.4
    audio.dispatchEvent(new Event('seeked'))
    audio.dispatchEvent(new Event('timeupdate'))
    audio.dispatchEvent(new Event('ended'))
  })()`)
  await client.waitFor("document.querySelector('.player-stage__status')?.textContent.includes('finished')")

  await client.evaluate(`document.querySelector('.player-stage audio').dispatchEvent(new Event('error'))`)
  await client.waitFor("Boolean(document.querySelector('.player-stage__error[role=\"alert\"]'))")

  const result = await client.evaluate(`({
    alert: document.querySelector('.player-stage__error')?.textContent,
    events: [...new Set(window.__phase5AudioEvents)],
    time: document.querySelector('.player-stage audio')?.currentTime,
  })`)
  for (const eventName of ['play', 'pause', 'seeked', 'timeupdate', 'ended', 'error']) {
    assert(result.events.includes(eventName), `Browser playback did not observe ${eventName}`)
  }
  assert(result.time >= 2, 'Browser seek did not update the native audio time')
  assert(result.alert, 'Browser audio error did not produce a visible alert')
  return result
}

let activeClient

async function main() {
  const targets = await fetch(`${debugBase}/json/list`).then((response) => response.json())
  const target = targets.find((candidate) => candidate.type === 'page')
  assert(target?.webSocketDebuggerUrl, 'Chrome page target is unavailable')

  const client = new CdpClient(target.webSocketDebuggerUrl)
  activeClient = client
  const pageErrors = []
  const requests = []
  const authPayload = JSON.stringify({ id: 905, role: 'user', username: 'phase5-browser' })
  const authBody = Buffer.from(authPayload).toString('base64')

  client.onEvent = (method, params) => {
    if (method === 'Runtime.exceptionThrown') {
      pageErrors.push(params.exceptionDetails.exception?.description || params.exceptionDetails.text)
    }
    if (method === 'Runtime.consoleAPICalled' && params.type === 'error') {
      pageErrors.push(params.args.map((argument) => argument.value || argument.description).join(' '))
    }
    if (method === 'Network.requestWillBeSent') requests.push(params.request.url)
    if (method === 'Fetch.requestPaused') {
      const isAuthMe = new URL(params.request.url).pathname === '/api/auth/me'
      const response = isAuthMe
        ? client.send('Fetch.fulfillRequest', {
          body: authBody,
          requestId: params.requestId,
          responseCode: 200,
          responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
        })
        : client.send('Fetch.continueRequest', { requestId: params.requestId })
      response.catch((error) => pageErrors.push(error.message))
    }
  }

  await client.connect()
  await client.send('Page.enable')
  await client.send('Runtime.enable')
  await client.send('Network.enable')
  await client.send('Fetch.enable', { patterns: [{ requestStage: 'Request', urlPattern: '*://*/api/auth/me*' }] })
  await client.navigate('/login')
  await client.evaluate(`(() => {
    localStorage.setItem('token', 'phase5-browser-token')
    localStorage.setItem('refresh_token', 'phase5-browser-refresh')
    localStorage.setItem('user', ${JSON.stringify(authPayload)})
  })()`)

  const results = []
  const screenshots = []
  const viewports = [
    { height: 1000, label: 'desktop', mobile: false, width: 1440 },
    { height: 844, label: 'mobile', mobile: true, width: 390 },
  ]

  for (const viewport of viewports) {
    await setViewport(client, viewport.width, viewport.height, viewport.mobile)
    for (const theme of ['light', 'dark']) {
      pageErrors.length = 0
      requests.length = 0
      await setReducedMotion(client, false)
      await client.evaluate(`localStorage.setItem('theme', ${JSON.stringify(theme)})`)
      await client.navigate('/music')
      await client.waitFor("Boolean(document.querySelector('.standalone-player-route .player-stage audio'))")
      await client.waitFor("document.querySelector('.player-stage audio').readyState >= 1", 10000)
      await sleep(180)

      const state = await inspectPlayer(client)
      assert.equal(state.pathname, '/music')
      assert.equal(state.theme, theme)
      assert.equal(state.rootPresent, true)
      assert.equal(state.audioIsLocal, true)
      assert.equal(state.hasIframe, false)
      assert.equal(state.particles, 18)
      assert(state.overflow <= 1, `${viewport.label} ${theme} player overflows by ${state.overflow}px`)
      if (viewport.mobile) {
        assert(state.playTarget >= 44, 'Mobile play control is smaller than 44px')
        assert.equal(state.rangesFit, true, 'Mobile range control is smaller than 44px')
      }

      screenshots.push(await capture(client, `phase5-${viewport.label}-${theme}-player.png`))

      await setReducedMotion(client, true)
      const reduced = await inspectPlayer(client)
      assert.equal(reduced.particleAnimation, 'none')
      assert.equal(reduced.orbitAnimation, 'none')
      assert(reduced.lyricTransition === '0s' || reduced.lyricTransition === '0s, 0s, 0s')

      const forbiddenRequests = requests.filter((url) => (
        /\/mineradio-api\/|\/socket\.io\/|\/ws\/socket\.io\//.test(url)
        || (!url.startsWith(appBase) && !url.startsWith('data:'))
      ))
      assert.deepEqual(forbiddenRequests, [], `${viewport.label} ${theme} made provider/socket requests`)
      assert.deepEqual(pageErrors, [], `${viewport.label} ${theme} emitted browser errors`)
      results.push({ reduced, state, theme, viewport })
    }
  }

  await setViewport(client, 1440, 1000, false)
  await setReducedMotion(client, false)
  pageErrors.length = 0
  requests.length = 0
  await client.evaluate("localStorage.setItem('theme', 'dark')")
  await client.navigate('/music')
  await client.waitFor("document.querySelector('.player-stage audio')?.readyState >= 1", 10000)
  const playback = await exercisePlayback(client)
  assert.deepEqual(pageErrors, [], 'Playback exercise emitted browser errors')
  const playbackForbidden = requests.filter((url) => /\/mineradio-api\/|\/socket\.io\/|\/ws\/socket\.io\//.test(url))
  assert.deepEqual(playbackForbidden, [], 'Local playback contacted a provider or room socket')

  client.close()
  activeClient = null
  console.log(JSON.stringify({ playback, results, screenshots }, null, 2))
}

main().catch((error) => {
  activeClient?.close()
  console.error(error)
  process.exitCode = 1
})
