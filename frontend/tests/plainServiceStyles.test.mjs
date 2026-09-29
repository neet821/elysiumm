import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const sourceDir = new URL('../src/', import.meta.url)
const plainServicePath = new URL('components/layout/plainService.css', sourceDir)
const globalStyles = readFileSync(new URL('index.css', sourceDir), 'utf8')
const appShell = readFileSync(new URL('components/layout/AppShell.jsx', sourceDir), 'utf8')

test('the shared plain-service presentation belongs to the eager application shell', () => {
  assert.ok(existsSync(plainServicePath), 'AppShell has a dedicated plain-service stylesheet')
  const plainServiceStyles = readFileSync(plainServicePath, 'utf8')

  assert.match(plainServiceStyles, /Plain service presentation/)
  assert.match(plainServiceStyles, /--surface-page:\s*#fff/)
  assert.match(plainServiceStyles, /\.service-shell:not\(\.service-shell--legacy-review\):not\(\.app-shell--home\)/)
  assert.match(plainServiceStyles, /@media\s*\(prefers-reduced-motion:\s*reduce\)/)
  assert.doesNotMatch(globalStyles, /Plain service presentation/)

  const plainServiceImport = appShell.indexOf("import './plainService.css'")
  const navigationImport = appShell.indexOf("import './homeNavigation.css'")
  assert.ok(plainServiceImport >= 0, 'AppShell imports the plain-service presentation')
  assert.ok(navigationImport > plainServiceImport, 'plain-service styles load before the shell navigation overrides')
})
