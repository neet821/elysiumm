import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8')
const entry = readFileSync(new URL('../src/main.jsx', import.meta.url), 'utf8')
const appShell = readFileSync(new URL('../src/components/layout/AppShell.jsx', import.meta.url), 'utf8')
const stylesPath = new URL('../src/components/layout/homeNavigation.css', import.meta.url)
const styles = existsSync(stylesPath) ? readFileSync(stylesPath, 'utf8') : ''
const articleFlowStyles = readFileSync(new URL('../src/features/content/articleFlow.css', import.meta.url), 'utf8')

test('shared wide navigation styles load with the eager application shell', () => {
  assert.match(app, /import\s+\{\s*AppShell\s*\}\s+from\s+["']\.\/components\/layout\/AppShell["']/, 'the app must eagerly mount AppShell')
  assert.ok(entry.indexOf('import "./index.css"') < entry.indexOf('import App from "./App.jsx"'), 'base styles must load before eager component styles')
  assert.match(appShell, /import\s+["']\.\/homeNavigation\.css["']/, 'the shared shell must own navigation styles')
  assert.ok(styles, 'the shared navigation stylesheet must exist')

  for (const selector of [
    '.app-shell--wide-navigation .app-shell__main',
    '.home-nav--global {',
    '.home-nav--global .home-nav__identity',
    '.home-nav--global .home-nav__action',
  ]) {
    assert.ok(styles.includes(selector), `the shared stylesheet must include ${selector}`)
  }
  assert.match(styles, /@media\s*\(min-width:\s*1101px\)/, 'the wide rail breakpoint must remain')
  assert.match(styles, /@media\s*\(max-width:\s*1100px\)[\s\S]*?\.home-nav--global\s*\{\s*display:\s*none/s, 'the compact breakpoint must hide the global rail')
  assert.doesNotMatch(articleFlowStyles, /\.home-nav--global/, 'shared navigation rules must not depend on the lazy homepage stylesheet')
  assert.match(articleFlowStyles, /\.legacy-old-home--flat \.home-nav\s*\{/, 'homepage-local navigation presentation must remain page-owned')
})
