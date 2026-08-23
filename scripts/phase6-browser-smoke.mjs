import assert from 'node:assert/strict'
import fs from 'node:fs'

const debugBase = process.env.CHROME_DEBUG_URL || 'http://127.0.0.1:9226'
const appBase = process.env.BLUE_ALBUM_URL || 'http://127.0.0.1:15176'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-phase6-browser'

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

const catalogPayload = {
  items: [
    {
      album: 'Open Sky', artist: 'Alice', artwork_url: null, availability: 'playable', duration_seconds: 180, id: 101,
      providers: [
        { availability: 'playable', media_mid: null, provider: 'netease', provider_track_id: 'ne-101' },
        { availability: 'preview', media_mid: 'media-101', provider: 'qq', provider_track_id: 'qq-101' },
      ],
      title: 'Playable Song',
    },
    {
      album: null, artist: 'Bob', artwork_url: null, availability: 'preview', duration_seconds: 90, id: 102,
      providers: [{ availability: 'preview', media_mid: 'media-102', provider: 'qq', provider_track_id: 'qq-102' }],
      title: 'Preview Song',
    },
    {
      album: null, artist: 'Carol', artwork_url: null, availability: 'unavailable', duration_seconds: 200, id: 103,
      providers: [{ availability: 'unavailable', media_mid: null, provider: 'audius', provider_track_id: 'au-103' }],
      title: 'Unavailable Song',
    },
  ],
  providers: [
    { count: 0, provider: 'netease', status: 'error' },
    { count: 2, provider: 'qq', status: 'ok' },
    { count: 1, provider: 'audius', status: 'ok' },
  ],
  query: 'blue',
}

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
  await client.send('Emulation.setDeviceMetricsOverride', { deviceScaleFactor: 1, height, mobile, width })
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
    return { disabled: Boolean(element.disabled), x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
  })()`)
  assert(point, `Missing clickable selector: ${selector}`)
  assert.equal(point.disabled, false, `Selector is disabled: ${selector}`)
  await client.send('Input.dispatchMouseEvent', { button: 'left', clickCount: 1, type: 'mousePressed', x: point.x, y: point.y })
  await client.send('Input.dispatchMouseEvent', { button: 'left', clickCount: 1, type: 'mouseReleased', x: point.x, y: point.y })
}

function bodyBase64(payload) {
  return Buffer.from(JSON.stringify(payload)).toString('base64')
}

function responseFor(request, proposalBodies) {
  const url = new URL(request.url)
  const path = url.pathname
  if (path === '/api/auth/me') return { id: 906, is_active: true, role: 'user', username: 'phase6-browser' }
  if (path === '/api/sync-rooms') return [{ id: 9, member_count: 1, mode: 'music', room_name: 'Canonical room' }]
  if (path === '/api/sync-rooms/9/messages') return []
  if (path === '/api/sync-rooms/9') {
    return {
      control_mode: 'host_only', current_time: 0, host_user_id: 906, id: 9, is_playing: false,
      members: [{ is_online: true, user_id: 906, username: 'phase6-browser' }], mode: 'music', room_name: 'Canonical room',
    }
  }
  if (path === '/api/music/rooms/9/queue') return { current_time: 0, is_playing: false, playback_version: 1, queue: [] }
  if (path === '/api/music/search') return catalogPayload
  if (path === '/api/music/rooms/9/proposals' && request.method === 'POST') {
    proposalBodies.push(JSON.parse(request.postData || '{}'))
    return { approved: false, item_id: 77, queue: [], required: 2, votes: 1 }
  }
  if (path === '/api/music/tracks/101/audio') {
    if (url.searchParams.get('refresh') === 'true') {
      return {
        availability: 'playable', expires_at: '2026-07-16T04:30:00', playback_url: '/api/music/local/refreshed.wav',
        provider: 'local', source_type: 'local',
      }
    }
    return {
      availability: 'playable', expires_at: null, playback_url: '/api/music/local/original.wav',
      provider: 'local', source_type: 'local',
    }
  }
  if (path === '/api/music/tracks/101/lyrics') {
    return {
      cached: true, language: 'original', lines: [{ text: 'Blue hour', time: 1 }], provider: 'qq', track_id: 101, translation: [],
    }
  }
  return null
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
  const proposalBodies = []

  client.onEvent = (method, params) => {
    if (method === 'Runtime.exceptionThrown') {
      pageErrors.push(params.exceptionDetails.exception?.description || params.exceptionDetails.text)
    }
    if (method === 'Runtime.consoleAPICalled' && params.type === 'error') {
      pageErrors.push(params.args.map((argument) => argument.value || argument.description).join(' '))
    }
    if (method === 'Network.requestWillBeSent') requests.push(params.request.url)
    if (method === 'Fetch.requestPaused') {
      const url = new URL(params.request.url)
      const isApi = url.origin === appBase && url.pathname.startsWith('/api/')
      const payload = isApi ? responseFor(params.request, proposalBodies) : null
      const response = payload === null
        ? client.send('Fetch.continueRequest', { requestId: params.requestId })
        : client.send('Fetch.fulfillRequest', {
          body: bodyBase64(payload),
          requestId: params.requestId,
          responseCode: 200,
          responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
        })
      response.catch((error) => pageErrors.push(error.message))
    }
  }

  await client.connect()
  await client.send('Page.enable')
  await client.send('Runtime.enable')
  await client.send('Network.enable')
  await client.send('Fetch.enable', { patterns: [{ requestStage: 'Request', urlPattern: '*://*/api/*' }] })
  await client.send('Page.addScriptToEvaluateOnNewDocument', {
    source: `(() => {
      const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie')
      window.__phase6CookieReads = 0
      if (descriptor?.configurable) {
        Object.defineProperty(Document.prototype, 'cookie', {
          configurable: true,
          get() { window.__phase6CookieReads += 1; return descriptor.get.call(this) },
          set(value) { return descriptor.set.call(this, value) },
        })
      }
    })()`,
  })

  await client.navigate('/login')
  await client.evaluate(`(() => {
    localStorage.setItem('token', 'phase6-browser-token')
    localStorage.setItem('refresh_token', 'phase6-browser-refresh')
    localStorage.setItem('user', ${JSON.stringify(JSON.stringify({ id: 906, role: 'user', username: 'phase6-browser' }))})
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
      await client.evaluate(`localStorage.setItem('theme', ${JSON.stringify(theme)})`)
      await client.navigate('/music/rooms/9')
      await client.waitFor("document.querySelector('h1')?.textContent === 'Canonical room'")
      await client.evaluate(`(() => {
        const input = document.querySelector('input[aria-label="歌曲或音乐人"]')
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
        setter.call(input, 'blue')
        input.dispatchEvent(new Event('input', { bubbles: true }))
      })()`)
      await clickSelector(client, '.room-player-search button[type="submit"]')
      await client.waitFor("document.body.textContent.includes('Playable Song') && document.body.textContent.includes('Unavailable Song')")

      const state = await client.evaluate(`(() => {
        const unavailable = document.querySelector('button[aria-label="点歌 Unavailable Song"]')
        const labels = Array.from(document.querySelectorAll('.room-player-availability')).map((item) => item.textContent.trim())
        const providers = Array.from(document.querySelectorAll('.room-player-providers span')).map((item) => item.textContent.trim())
        return {
          cookieReads: window.__phase6CookieReads || 0,
          hasIframe: Boolean(document.querySelector('iframe')),
          labels,
          overflow: document.documentElement.scrollWidth - innerWidth,
          pathname: location.pathname,
          providers,
          theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
          unavailableDisabled: Boolean(unavailable?.disabled),
          width: innerWidth,
        }
      })()`)
      assert.equal(state.pathname, '/music/rooms/9')
      assert.equal(state.theme, theme)
      assert.deepEqual(state.labels, ['可播放', '试听', '不可用'])
      assert(state.providers.includes('netease') && state.providers.includes('qq') && state.providers.includes('audius'))
      assert.equal(state.unavailableDisabled, true)
      assert.equal(state.hasIframe, false)
      assert.equal(state.cookieReads, 0)
      assert(state.overflow <= 1, `${viewport.label} ${theme} overflows by ${state.overflow}px`)

      await client.evaluate(`(() => {
        document.querySelector('.room-player-catalog')?.closest('section')?.scrollIntoView({ block: 'start' })
        window.scrollBy(0, -72)
      })()`)
      await sleep(100)
      screenshots.push(await capture(client, `phase6-${viewport.label}-${theme}-catalog.png`))

      const forbidden = requests.filter((url) => (
        /\/mineradio-api\/|music\.163\.com|y\.qq\.com|api\.audius\.co/i.test(url)
        || (!url.startsWith(appBase) && !url.startsWith('data:') && !url.startsWith('blob:'))
      ))
      assert.deepEqual(forbidden, [], `${viewport.label} ${theme} made direct provider requests`)
      assert.deepEqual(pageErrors, [], `${viewport.label} ${theme} emitted browser errors`)
      results.push({ state, theme, viewport })
    }
  }

  await clickSelector(client, 'button[aria-label="点歌 Preview Song"]')
  await client.waitFor('document.body.textContent.includes("已发起《Preview Song》点歌投票")')
  assert.equal(proposalBodies.length, 1)
  assert.deepEqual(
    {
      media_mid: proposalBodies[0].media_mid,
      provider: proposalBodies[0].provider,
      provider_track_id: proposalBodies[0].provider_track_id,
    },
    { media_mid: 'media-102', provider: 'qq', provider_track_id: 'qq-102' },
  )

  const apiProof = await client.evaluate(`(async () => {
    const search = await fetch('/api/music/search?q=blue&providers=netease,qq,audius&limit=30').then((response) => response.json())
    const local = await fetch('/api/music/tracks/101/audio').then((response) => response.json())
    const refreshed = await fetch('/api/music/tracks/101/audio?refresh=true').then((response) => response.json())
    const lyrics = await fetch('/api/music/tracks/101/lyrics?language=original').then((response) => response.json())
    return { local, lyrics, refreshed, search }
  })()`)
  assert.equal(apiProof.search.providers.find((item) => item.provider === 'netease').status, 'error')
  assert.equal(apiProof.search.items.length, 3)
  assert.equal(apiProof.local.source_type, 'local')
  assert.equal(apiProof.local.expires_at, null)
  assert.equal(apiProof.refreshed.playback_url, '/api/music/local/refreshed.wav')
  assert.deepEqual(apiProof.lyrics.lines, [{ text: 'Blue hour', time: 1 }])

  client.close()
  activeClient = null
  console.log(JSON.stringify({ apiProof, proposalBodies, results, screenshots }, null, 2))
}

main().catch((error) => {
  activeClient?.close()
  console.error(error)
  process.exitCode = 1
})
