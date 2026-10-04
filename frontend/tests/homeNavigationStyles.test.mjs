import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { resolveArticleFlowCss } from './helpers/articleFlowStyles.mjs'

const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')
const entry = readFileSync(new URL('../src/main.jsx', import.meta.url), 'utf8')
const appShell = readFileSync(new URL('../src/components/layout/AppShell.jsx', import.meta.url), 'utf8')
const stylesPath = new URL('../src/components/layout/homeNavigation.css', import.meta.url)
const styles = existsSync(stylesPath) ? readFileSync(stylesPath, 'utf8') : ''
const articleFlowNavigationStyles = resolveArticleFlowCss()

test('shared labelled navigation styles load with the eager application shell', () => {
  assert.match(app, /import\s+\{\s*AppShell\s*\}\s+from\s+["']\.\/components\/layout\/AppShell["']/, 'the app must eagerly mount AppShell')
  assert.ok(entry.indexOf('import "./index.css"') < entry.indexOf('import App from "./App.jsx"'), 'base styles must load before eager component styles')
  assert.match(appShell, /import\s+["']\.\/homeNavigation\.css["']/, 'the shared shell must own navigation styles')
  assert.ok(styles, 'the shared navigation stylesheet must exist')

  for (const selector of [
    '.app-shell--wide-navigation .app-shell__main',
    '.home-nav--global {',
    '.home-nav__action-label',
    '.home-nav__action',
  ]) {
    assert.ok(styles.includes(selector), `the shared stylesheet must include ${selector}`)
  }
  assert.match(styles, /max-width:\s*1200px/, 'navigation should share the 1200px content canvas')
  assert.match(styles, /min-height:\s*44px/, 'navigation controls must remain touch-sized')
  assert.doesNotMatch(styles, /home-nav-rail-width|position:\s*fixed/, 'shared navigation must not recreate the fixed rail')
  assert.doesNotMatch(articleFlowNavigationStyles, /\.home-nav--global/, 'shared navigation rules must not depend on the lazy homepage stylesheet')
  assert.match(articleFlowNavigationStyles, /\.legacy-old-home--flat \.home-nav\s*\{/, 'homepage-local navigation width must remain page-owned')
})
