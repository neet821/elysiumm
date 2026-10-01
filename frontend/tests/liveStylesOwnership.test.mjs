import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { LIVE_CSS_LAYERS, liveCssImports, liveCssLayerContents, resolveLiveCss } from './helpers/liveStyles.mjs'

const livePage = readFileSync(new URL('../src/pages/LivePage.jsx', import.meta.url), 'utf8')
const routes = readFileSync(new URL('../src/routes.jsx', import.meta.url), 'utf8')
const globalStyles = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
const featureStyles = resolveLiveCss()

test('live pages own their lazy-loaded presentation styles', () => {
  assert.match(livePage, /import ['"]\.\.\/features\/live\/live\.css['"]/, 'the live route must load its feature stylesheet')
  assert.match(routes, /const LivePage = lazy\(\(\) => import\('\.\/pages\/LivePage'\)\)/, 'live presentation must remain lazy-loaded')

  for (const selector of ['.live-watch-page {', '.live-player {', '.live-message-board {', '.admin-live {']) {
    assert.ok(featureStyles.includes(selector), `live feature stylesheet must own ${selector}`)
    assert.doesNotMatch(
      globalStyles,
      new RegExp(`(?:^|\\n)${selector.replaceAll('.', '\\.').replace(' {', '\\s*\\{')}`),
      `global stylesheet must not own the standalone ${selector.trim()} rule`,
    )
  }

  assert.match(featureStyles, /@media\s*\(max-width:\s*680px\)/, 'public live layout must retain its mobile breakpoint')
  assert.match(featureStyles, /@media\s*\(max-width:\s*800px\)/, 'admin live layout must retain its compact breakpoint')
})

test('unmounted legacy live landing styles are retired', () => {
  const allStyles = `${featureStyles}\n${globalStyles}`
  for (const selector of [
    /\.live-page(?:__[\w-]+)?(?![\w-])/,
    /\.live-hero(?:__[\w-]+)?(?![\w-])/,
    /\.live-presence(?:__[\w-]+)?(?![\w-])/,
    /\.live-state__pulse(?![\w-])/,
    /@keyframes\s+live-pulse\b/,
  ]) {
    assert.doesNotMatch(allStyles, selector, `legacy live styles must not remain: ${selector}`)
  }
})

test('live styles separate watch, admin, and page surfaces in cascade order', () => {
  assert.deepEqual(liveCssImports(), LIVE_CSS_LAYERS)
  const [watchStyles, adminStyles, surfaceStyles] = liveCssLayerContents()
  assert.match(watchStyles, /\.live-watch-page\s*\{/)
  assert.match(adminStyles, /\.admin-live\s*\{/)
  assert.match(surfaceStyles, /\.service-shell:has\(\.live-watch-page\)/)
})
