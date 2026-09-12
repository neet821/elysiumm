import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import {
  CdpClient,
  api,
  capture,
  chromeTarget,
  expectOk,
  freePort,
  localOnlyRequests,
  run,
  startProcess,
  stopProcess,
  waitForUrl,
} from './native-browser-smoke-helpers.mjs'

const root = path.resolve(import.meta.dirname, '..')
const python = path.join(root, 'backend', '.venv', 'bin', 'python')
const chromeBinary = process.env.CHROME_BINARY || '/usr/bin/google-chrome-stable'
const screenshotDir = process.env.BLUE_ALBUM_SCREENSHOT_DIR || '/tmp/blue-album-phase11-accessibility'
const widths = [360, 390, 430, 768, 1024, 1366, 1920, 2560]

function environmentFor(rootPath, appBase) {
  const storage = path.join(rootPath, 'shared')
  return {
    ...process.env,
    ACCESS_TOKEN_EXPIRE_MINUTES: '60',
    ADMIN_FILES_STORAGE_DIR: path.join(storage, 'private-storage', 'admin_files'),
    BACKEND_LOG_FILE: path.join(rootPath, 'backend.log'),
    BACKUP_OUTPUT_DIR: path.join(storage, 'backups'),
    CORS_ORIGINS: appBase,
    DATABASE_URL: `sqlite:///${path.join(rootPath, 'acceptance.sqlite')}`,
    LIVE_RECORDING_ROOT: path.join(storage, 'uploads', 'live-recordings'),
    MEDIA_ROOT: path.join(storage, 'sync-storage', 'media'),
    MUSIC_PROVIDER_CREDENTIAL_DIR: path.join(storage, 'private-storage', 'music'),
    MUSIC_PROVIDER_LEGACY_COMPAT: '0',
    PRIVATE_STORAGE_DIR: path.join(storage, 'private-storage'),
    PUBLIC_SYNC_STORAGE: path.join(storage, 'sync-storage'),
    SECRET_KEY: 'phase11-accessibility-isolated-secret-for-tests',
    TRANSFER_STORAGE_DIR: path.join(storage, 'transfers'),
    UPLOAD_DIR: path.join(storage, 'uploads'),
    ARTICLE_ROOT: path.join(storage, 'sync-storage', 'articles'),
  }
}

async function inspectPage(page, appBase, label) {
  const report = await page.evaluate(`(() => {
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
    const controls = [...document.querySelectorAll('input, select, textarea')].filter(visible)
    const interactive = [...document.querySelectorAll('button, a[href], [role="button"]')].filter(visible)
    const ids = [...document.querySelectorAll('[id]')].map((element) => element.id).filter(Boolean)
    return {
      duplicateIds: [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))],
      headingCount: document.querySelectorAll('h1').length,
      iframeCount: document.querySelectorAll('iframe').length,
      mainCount: document.querySelectorAll('main').length,
      overflow: document.documentElement.scrollWidth - innerWidth,
      unnamedControls: controls.filter((element) => !element.labels?.length && !name(element)).map((element) => element.outerHTML.slice(0, 180)),
      unnamedInteractive: interactive.filter((element) => !name(element)).map((element) => element.outerHTML.slice(0, 180)),
      path: location.pathname,
    }
  })()`)
  assert.equal(report.mainCount, 1, `${label} must expose one main region`)
  assert(report.headingCount >= 1, `${label} must expose a page heading`)
  assert.equal(report.iframeCount, 0, `${label} rendered a legacy iframe`)
  assert(report.overflow <= 1, `${label} has horizontal overflow: ${report.overflow}px`)
  assert.deepEqual(report.duplicateIds, [], `${label} has duplicate ids`)
  assert.deepEqual(report.unnamedControls, [], `${label} has unnamed form controls`)
  assert.deepEqual(report.unnamedInteractive, [], `${label} has unnamed interactive controls`)
  assert.deepEqual(localOnlyRequests(page.requests, appBase), [], `${label} contacted an external origin`)
  assert.deepEqual(page.errors, [], `${label} emitted browser errors`)
  return report
}

async function main() {
  assert(fs.existsSync(python), 'backend/.venv is required for the browser gate')
  assert(fs.existsSync(chromeBinary), `Chrome is unavailable: ${chromeBinary}`)
  fs.rmSync(screenshotDir, { force: true, recursive: true })
  fs.mkdirSync(screenshotDir, { recursive: true })

  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'elysium-phase11-native-'))
  const processes = []
  let client
  try {
    const [backendPort, frontendPort, debugPort] = await Promise.all([freePort(), freePort(), freePort()])
    const appBase = `http://127.0.0.1:${frontendPort}`
    const backendBase = `http://127.0.0.1:${backendPort}`
    const environment = environmentFor(temporaryRoot, appBase)
    fs.mkdirSync(environment.ARTICLE_ROOT, { recursive: true })
    fs.mkdirSync(path.join(environment.ARTICLE_ROOT, '文章'), { recursive: true })
    fs.mkdirSync(environment.MEDIA_ROOT, { recursive: true })
    fs.writeFileSync(
      path.join(environment.ARTICLE_ROOT, '文章', '原生文章验收.md'),
      '---\ntype: article\ntitle: 原生文章验收\n同步到网站: 是\n---\n\n这是一篇 FastAPI 文章契约验收内容。\n',
      'utf8',
    )

    await run(python, [path.join(root, 'backend', 'run_migrations.py')], { cwd: root, env: environment })
    processes.push(startProcess(python, [
      '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(backendPort), '--log-level', 'warning',
    ], {
      cwd: path.join(root, 'backend'),
      env: environment,
      logPath: path.join(temporaryRoot, 'backend.log'),
    }))
    await waitForUrl(`${backendBase}/api/health`)
    processes.push(startProcess('npm', [
      'run', 'dev', '--', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort',
    ], {
      cwd: path.join(root, 'frontend'),
      env: { ...process.env, VITE_BACKEND_PROXY_TARGET: backendBase },
      logPath: path.join(temporaryRoot, 'frontend.log'),
    }))
    await waitForUrl(appBase)

    const articleList = expectOk(await api(appBase, '/api/articles'), 'FastAPI Articles list')
    assert(articleList.articles.some((article) => article.title === '原生文章验收'), 'FastAPI Articles data was not published')

    processes.push(startProcess(chromeBinary, [
      '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
      '--no-first-run', '--no-default-browser-check', `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${path.join(temporaryRoot, 'chrome')}`, 'about:blank',
    ], { cwd: root, env: process.env, logPath: path.join(temporaryRoot, 'chrome.log') }))
    client = new CdpClient(await chromeTarget(`http://127.0.0.1:${debugPort}`), 'phase11')
    await client.connect()
    await client.setMedia('light')

    const viewportChecks = []
    const screenshots = []
    for (const width of widths) {
      await client.setViewport(width, width <= 430 ? 844 : 1000, width <= 430)
      for (const pathname of ['/', '/content', '/login', '/register']) {
        await client.navigate(`${appBase}${pathname}`)
        await client.waitFor("Boolean(document.querySelector('main'))")
        if (pathname === '/') await client.waitFor("Boolean(document.querySelector('.articles-section'))", 20000)
        if (pathname === '/content') await client.waitFor("Boolean(document.querySelector('.content-intro h1'))", 20000)
        viewportChecks.push({ width, ...await inspectPage(client, appBase, `${width}px ${pathname}`) })
      }
      await client.navigate(`${appBase}/`)
      await client.waitFor("Boolean(document.querySelector('.articles-section'))", 20000)
      const home = await client.evaluate(`(() => ({
        articleFlow: Boolean(document.querySelector('.articles-section')),
        navigation: [...document.querySelectorAll('nav[aria-label="首页导航"] a')].map((item) => item.textContent.trim()),
        sidebar: Boolean(document.querySelector('.home-sidebar')),
        overflow: document.documentElement.scrollWidth - innerWidth,
      }))()`)
      assert.equal(home.articleFlow, true, `${width}px home did not render the article flow`)
      assert.equal(home.sidebar, true, `${width}px home did not render the records sidebar`)
      assert(home.navigation.includes('观影房'), `${width}px home is missing the watch-room entry`)
      assert(home.navigation.includes('听歌房'), `${width}px home is missing the music-room entry`)
      assert(home.overflow <= 1, `${width}px home has horizontal overflow`)
      if ([390, 1366].includes(width)) screenshots.push(await capture(client, screenshotDir, `home-${width}.png`))
      if ([360, 768, 1366, 2560].includes(width)) {
        await client.navigate(`${appBase}/content`)
        screenshots.push(await capture(client, screenshotDir, `content-${width}.png`))
      }
    }

    await client.setViewport(390, 844, true)
    await client.setMedia('light', 'no-preference')
    await client.navigate(`${appBase}/`)
    await client.evaluate("document.querySelector('.skip-link')?.focus()")
    assert.equal(await client.evaluate("document.activeElement?.textContent?.trim()"), '跳到主要内容')
    await client.key('Enter', 'Enter')
    await client.waitFor("location.hash === '#main-content'")
    assert.equal(await client.evaluate("document.activeElement?.id"), 'main-content', 'skip link must focus the main region')

    const menuButton = await client.evaluate(`(() => {
      const button = [...document.querySelectorAll('[aria-label="展开记录和随笔"]')].find((element) => {
        const rect = element.getBoundingClientRect()
        return getComputedStyle(element).display !== 'none' && rect.width > 0 && rect.height > 0
      })
      button?.focus()
      return Boolean(button)
    })()`)
    if (menuButton) {
      await client.key('Enter', 'Enter')
      await client.waitFor("Boolean(document.querySelector('[role=\\\"dialog\\\"]'))")
      const dialog = await client.evaluate(`(() => {
        const element = document.querySelector('[role="dialog"]')
        const close = element?.querySelector('[aria-label="收起记录和随笔"]')
        const rect = close?.getBoundingClientRect()
        return { activeInside: Boolean(element && element.contains(document.activeElement)), modal: element?.getAttribute('aria-modal'), width: rect?.width || 0, height: rect?.height || 0 }
      })()`)
      assert.equal(dialog.activeInside, true, 'mobile navigation must move focus into the dialog')
      assert.equal(dialog.modal, 'true')
      assert(dialog.width >= 44 && dialog.height >= 44, 'mobile navigation control must be at least 44px')
      await client.key('Escape', 'Escape')
      await client.waitFor("!document.querySelector('[role=\\\"dialog\\\"]')")
    }

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
      }).length,
    }))()`)
    assert.equal(reducedMotion.matches, true)
    assert.equal(reducedMotion.motionNormal, '0ms')
    assert.equal(reducedMotion.animated, 0, 'reduced-motion mode must stop visible CSS animations')
    await client.setMedia('light', 'no-preference')
    await client.navigate(`${appBase}/content`)
    const unexpected = localOnlyRequests(client.requests, appBase)
    assert.deepEqual(unexpected, [], 'browser acceptance must not contact third parties')
    assert.deepEqual(client.errors, [], 'final browser page emitted errors')

    console.log(JSON.stringify({
      articles: articleList.articles.length,
      browser: await client.evaluate('navigator.userAgent'),
      nativeTopology: { backend: true, frontend: true, standaloneArticles: false, standaloneMineradio: false },
      screenshots,
      viewportChecks: viewportChecks.length,
      widths,
    }, null, 2))
  } catch (error) {
    const logs = fs.existsSync(temporaryRoot)
      ? fs.readdirSync(temporaryRoot).filter((name) => name.endsWith('.log')).map((name) => (
        `\n--- ${name} ---\n${fs.readFileSync(path.join(temporaryRoot, name), 'utf8').slice(-5000)}`
      )).join('')
      : ''
    throw new Error(`${error.stack || error.message}${logs}`)
  } finally {
    client?.close()
    await Promise.all(processes.reverse().map(stopProcess))
    fs.rmSync(temporaryRoot, { force: true, recursive: true })
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
