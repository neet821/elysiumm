import assert from 'node:assert/strict'
import fs from 'node:fs'

const debugBase = process.env.CHROME_DEBUG_URL || 'http://127.0.0.1:9225'
const appBase = process.env.BLUE_ALBUM_URL || 'http://127.0.0.1:15175'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-phase4-browser'
const username = 'phase4admin'
const password = 'BlueAlbum2026!'

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

async function api(pathname, { body, form, method = 'GET', token } = {}) {
  const headers = {}
  let requestBody
  if (token) headers.Authorization = `Bearer ${token}`
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    requestBody = new URLSearchParams(form)
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(body)
  }
  const response = await fetch(`${appBase}${pathname}`, { body: requestBody, headers, method })
  const text = await response.text()
  let payload = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = text
    }
  }
  return { ok: response.ok, payload, status: response.status }
}

function expectOk(result, label) {
  assert(result.ok, `${label} failed (${result.status}): ${JSON.stringify(result.payload)}`)
  return result.payload
}

async function seedData() {
  const registration = await api('/api/users/register', {
    body: { email: 'phase4admin@example.com', password, username },
    method: 'POST',
  })
  assert(registration.ok || registration.status === 400, `Test user setup failed: ${JSON.stringify(registration.payload)}`)

  const auth = expectOk(await api('/api/auth/login', {
    form: { password, username },
    method: 'POST',
  }), 'Test login')
  const token = auth.access_token

  const posts = expectOk(await api('/api/posts?limit=100'), 'Read posts')
  const postSeeds = [
    {
      category: 'Engineering',
      content: 'A technical field note about normalized timelines and careful archive systems.',
      slug: 'phase4-quiet-archive-systems',
      tags: ['technology'],
      title: 'Systems for a quiet archive',
    },
    {
      category: 'Journal',
      content: 'Notes from a slow evening walk beneath the blue hour.',
      slug: 'phase4-blue-hour-walk',
      tags: ['travel'],
      title: 'Walking beneath blue hour',
    },
  ]
  for (const post of postSeeds) {
    if (!posts.some((item) => item.slug === post.slug)) {
      expectOk(await api('/api/posts', { body: post, method: 'POST', token }), `Create post ${post.slug}`)
    }
  }

  const photos = expectOk(await api('/api/photos?limit=100'), 'Read photos')
  if (!photos.some((item) => item.caption === 'Blue hour camera walk')) {
    const image = encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#09162c"/><stop offset="1" stop-color="#3b72a8"/></linearGradient></defs><rect width="1200" height="800" fill="url(#g)"/><circle cx="880" cy="230" r="88" fill="#e7d7a8" opacity=".82"/><path d="M0 650L250 420 430 610 700 350 1200 690V800H0Z" fill="#07101f" opacity=".75"/></svg>')
    expectOk(await api('/api/photos', {
      body: {
        caption: 'Blue hour camera walk',
        is_featured: true,
        location: 'Shanghai',
        tags: ['travel'],
        url: `data:image/svg+xml,${image}`,
      },
      method: 'POST',
      token,
    }), 'Create archive photo')
  }

  let folders = expectOk(await api('/api/bookmark-folders', { token }), 'Read bookmark folders')
  let publicFolder = folders.find((item) => item.name === 'Public research')
  if (!publicFolder) {
    publicFolder = expectOk(await api('/api/bookmark-folders', {
      body: { color: '#2A5C8D', is_public: true, name: 'Public research' },
      method: 'POST',
      token,
    }), 'Create public folder')
  }
  let privateFolder = folders.find((item) => item.name === 'Private plans')
  if (!privateFolder) {
    privateFolder = expectOk(await api('/api/bookmark-folders', {
      body: { is_public: false, name: 'Private plans' },
      method: 'POST',
      token,
    }), 'Create private folder')
  }

  const bookmarks = expectOk(await api('/api/bookmarks', { token }), 'Read bookmarks')
  const bookmarkSeeds = [
    {
      description: 'Public product and safety reference for Phase 4.',
      folder_id: publicFolder.id,
      is_pinned: true,
      is_public: true,
      show_description: true,
      show_visit_count: true,
      tags: ['phase4', 'reference'],
      title: 'Phase 4 reference',
      url: 'https://example.com/phase4-reference',
    },
    {
      description: 'A second public place for the responsive card grid.',
      folder_id: publicFolder.id,
      is_public: true,
      show_description: true,
      tags: ['design'],
      title: 'Editorial design notes',
      url: 'https://example.com/editorial-design',
    },
    {
      description: 'This owner-only item must never appear on the public page.',
      folder_id: privateFolder.id,
      is_pinned: true,
      is_public: false,
      tags: ['private'],
      title: 'Private release checklist',
      url: 'https://example.com/private-release',
    },
  ]
  for (const bookmark of bookmarkSeeds) {
    if (!bookmarks.some((item) => item.title === bookmark.title)) {
      expectOk(await api('/api/bookmarks', { body: bookmark, method: 'POST', token }), `Create bookmark ${bookmark.title}`)
    }
  }

  const engines = expectOk(await api('/api/search-engines', { token }), 'Read search engines')
  if (!engines.some((item) => item.name === 'Reference search')) {
    expectOk(await api('/api/search-engines', {
      body: {
        category: 'research',
        category_label: 'Research',
        name: 'Reference search',
        url_template: 'https://example.com/search?q={query}',
      },
      method: 'POST',
      token,
    }), 'Create search engine')
  }

  const backups = expectOk(await api('/api/bookmarks/backups', { token }), 'Read bookmark backups')
  if (backups.length === 0) {
    expectOk(await api('/api/bookmarks/backups', { method: 'POST', token }), 'Create bookmark backup')
  }

  folders = expectOk(await api('/api/bookmark-folders', { token }), 'Refresh bookmark folders')
  return {
    auth,
    publicFolderId: folders.find((item) => item.name === 'Public research').id,
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

async function applyTheme(client, theme) {
  await client.evaluate(`localStorage.setItem('theme', ${JSON.stringify(theme)})`)
}

async function setAuth(client, auth) {
  await client.evaluate(`(() => {
    localStorage.setItem('token', ${JSON.stringify(auth.access_token)})
    localStorage.setItem('refresh_token', ${JSON.stringify(auth.refresh_token)})
    localStorage.setItem('user', ${JSON.stringify(JSON.stringify(auth.user))})
  })()`)
}

async function clearAuth(client) {
  await client.evaluate(`(() => {
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
  })()`)
}

async function capture(client, filename) {
  fs.mkdirSync(screenshotDir, { recursive: true })
  const shot = await client.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
  const path = `${screenshotDir}/${filename}`
  fs.writeFileSync(path, Buffer.from(shot.data, 'base64'))
  return path
}

async function inspectPage(client, kind) {
  return client.evaluate(`(() => {
    const kind = ${JSON.stringify(kind)}
    const text = document.body.innerText
    const theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light'
    const base = {
      height: innerHeight,
      kind,
      overflow: document.documentElement.scrollWidth - innerWidth,
      pathname: location.pathname,
      search: location.search,
      theme,
      width: innerWidth,
    }
    if (kind === 'archive') {
      const items = Array.from(document.querySelectorAll('[data-testid="archive-item"]'))
      return {
        ...base,
        entries: items.length,
        hasPhoto: items.some((item) => item.classList.contains('archive-entry--photo')),
        hasWriting: items.some((item) => item.classList.contains('archive-entry--writing')),
        titles: items.map((item) => item.querySelector('h2')?.textContent?.trim()),
        typeControls: Array.from(document.querySelectorAll('.archive-page__types button')).map((button) => ({
          height: button.getBoundingClientRect().height,
          label: button.textContent.trim(),
        })),
      }
    }
    if (kind === 'public') {
      return {
        ...base,
        cards: document.querySelectorAll('.public-bookmark-card').length,
        folders: Array.from(document.querySelectorAll('.public-collection__folders button')).map((button) => button.textContent.trim()),
        manageLink: document.querySelector('.public-collection__manage')?.getAttribute('href'),
        privateLeak: text.includes('Private release checklist'),
        titles: Array.from(document.querySelectorAll('.public-bookmark-card h2')).map((node) => node.textContent.trim()),
      }
    }
    return {
      ...base,
      cards: document.querySelectorAll('.private-bookmark-card').length,
      folders: document.querySelectorAll('.collection-folder-tree__item').length,
      privateItemPresent: text.includes('Private release checklist'),
      tabs: Array.from(document.querySelectorAll('[role="tab"]')).map((button) => button.textContent.trim()),
      tabsFit: Array.from(document.querySelectorAll('[role="tab"]')).every((button) => {
        const rect = button.getBoundingClientRect()
        return rect.left >= 0 && rect.right <= innerWidth
      }),
      transferVisible: Boolean(document.querySelector('.collection-transfer')),
    }
  })()`)
}

async function loadAndInspect(client, pathname, selector, kind, theme) {
  await applyTheme(client, theme)
  await client.navigate(pathname)
  await client.waitFor(`Boolean(document.querySelector(${JSON.stringify(selector)}))`)
  await sleep(180)
  const state = await inspectPage(client, kind)
  assert.equal(state.pathname, pathname.split('?')[0])
  assert.equal(state.theme, theme)
  assert(state.overflow <= 1, `${state.width}px ${theme} ${kind} page overflows by ${state.overflow}px`)
  return state
}

async function openTransferTab(client) {
  const clicked = await client.evaluate(`(() => {
    const tab = Array.from(document.querySelectorAll('[role="tab"]')).find((item) => item.textContent.trim() === 'Transfer & backups')
    tab?.click()
    return Boolean(tab)
  })()`)
  assert(clicked, 'Transfer & backups tab is missing')
  await client.waitFor("Boolean(document.querySelector('.collection-transfer'))")
  await sleep(180)
}

async function main() {
  const seed = await seedData()
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
  await client.navigate('/')
  await clearAuth(client)

  await client.navigate('/account/collection?from=phase4')
  await client.waitFor("location.pathname === '/login'")
  const redirectState = await client.evaluate(`({ pathname: location.pathname, search: location.search })`)
  assert.equal(redirectState.pathname, '/login')
  assert(redirectState.search.includes('redirect='), 'Protected route did not preserve its destination')
  assert(redirectState.search.includes('account%2Fcollection'), `Protected redirect is incomplete: ${redirectState.search}`)

  await setAuth(client, seed.auth)

  await setViewport(client, 1440, 1000, false)
  pageErrors.length = 0
  let filtered = await loadAndInspect(client, '/archive?type=photo', '.archive-timeline', 'archive', 'light')
  assert.equal(filtered.entries, 1)
  assert.equal(filtered.hasPhoto, true)
  assert.equal(filtered.hasWriting, false)
  filtered = await loadAndInspect(client, '/archive?q=systems', '.archive-timeline', 'archive', 'light')
  assert.deepEqual(filtered.titles, ['Systems for a quiet archive'])
  filtered = await loadAndInspect(client, '/archive?tag=technology', '.archive-timeline', 'archive', 'light')
  assert.deepEqual(filtered.titles, ['Systems for a quiet archive'])
  filtered = await loadAndInspect(client, '/collection?q=Phase%204', '.public-collection__grid', 'public', 'light')
  assert.deepEqual(filtered.titles, ['Phase 4 reference'])
  filtered = await loadAndInspect(client, `/collection?folder=${seed.publicFolderId}`, '.public-collection__grid', 'public', 'light')
  assert.equal(filtered.cards, 2)
  assert.deepEqual(pageErrors, [], 'URL filter checks emitted browser errors')

  const screenshots = []
  const results = []
  const viewports = [
    { height: 1000, label: 'desktop', mobile: false, width: 1440 },
    { height: 844, label: 'mobile', mobile: true, width: 390 },
  ]

  for (const viewport of viewports) {
    await setViewport(client, viewport.width, viewport.height, viewport.mobile)
    for (const theme of ['light', 'dark']) {
      pageErrors.length = 0

      const archive = await loadAndInspect(client, '/archive', '.archive-timeline', 'archive', theme)
      assert(archive.entries >= 3, `${viewport.label} ${theme} archive lost seeded entries`)
      assert(archive.hasPhoto && archive.hasWriting, `${viewport.label} ${theme} archive is not a mixed timeline`)
      assert.deepEqual(archive.typeControls.map((item) => item.label), ['All', 'Writings', 'Photos'])
      if (viewport.mobile) {
        assert(archive.typeControls.every((item) => item.height >= 44), 'Mobile archive type control is smaller than 44px')
      }
      screenshots.push(await capture(client, `phase4-${viewport.label}-${theme}-archive.png`))

      const publicCollection = await loadAndInspect(client, '/collection', '.public-collection__grid', 'public', theme)
      assert(publicCollection.cards >= 2, `${viewport.label} ${theme} public collection lost seeded cards`)
      assert(publicCollection.folders.includes('Public research'), 'Public folder selector is missing')
      assert.equal(publicCollection.manageLink, '/account/collection')
      assert.equal(publicCollection.privateLeak, false, 'Private bookmark leaked into the public page')
      screenshots.push(await capture(client, `phase4-${viewport.label}-${theme}-public-collection.png`))

      const privateCollection = await loadAndInspect(client, '/account/collection', '.private-collection__grid', 'private', theme)
      assert(privateCollection.cards >= 3, `${viewport.label} ${theme} private workspace lost seeded cards`)
      assert.equal(privateCollection.privateItemPresent, true)
      assert.deepEqual(privateCollection.tabs, ['Workspace', 'Start page', 'Search engines', 'Transfer & backups'])
      if (viewport.mobile) {
        assert.equal(privateCollection.tabsFit, true, 'Mobile private collection hides a view tab off-screen')
      }
      screenshots.push(await capture(client, `phase4-${viewport.label}-${theme}-private-collection.png`))

      await openTransferTab(client)
      const transfer = await inspectPage(client, 'private')
      assert.equal(transfer.transferVisible, true)
      const transferDetails = await client.evaluate(`(() => ({
        backupCards: document.querySelectorAll('.collection-backup-card').length,
        exportButtons: Array.from(document.querySelectorAll('.collection-transfer__exports button')).map((button) => button.textContent.trim()),
        importCards: document.querySelectorAll('.collection-import-card').length,
        overflow: document.documentElement.scrollWidth - innerWidth,
      }))()`)
      assert.equal(transferDetails.importCards, 2)
      assert.deepEqual(transferDetails.exportButtons, ['Export JSON', 'Export HTML'])
      assert(transferDetails.backupCards >= 1, 'Safe backup listing is empty')
      assert(transferDetails.overflow <= 1, `${viewport.label} ${theme} transfer page overflows horizontally`)
      screenshots.push(await capture(client, `phase4-${viewport.label}-${theme}-transfer.png`))

      assert.deepEqual(pageErrors, [], `${viewport.label} ${theme} Phase 4 pages emitted browser errors`)
      results.push({ archive, privateCollection, publicCollection, transfer: transferDetails, viewport, theme })
    }
  }

  client.close()
  activeClient = null
  console.log(JSON.stringify({ redirectState, results, screenshots }, null, 2))
}

main().catch((error) => {
  activeClient?.close()
  console.error(error)
  process.exitCode = 1
})
