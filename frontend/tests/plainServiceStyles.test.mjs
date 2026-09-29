import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const sourceDir = new URL('../src/', import.meta.url)
const plainServicePath = new URL('components/layout/plainService.css', sourceDir)
const adminWorkspacePath = new URL('features/admin/adminConsoleWorkspace.css', sourceDir)
const globalStyles = readFileSync(new URL('index.css', sourceDir), 'utf8')
const appShell = readFileSync(new URL('components/layout/AppShell.jsx', sourceDir), 'utf8')

test('active shell styles keep the eager plain-service presentation without retired review skin', () => {
  assert.ok(existsSync(plainServicePath), 'AppShell has a dedicated plain-service stylesheet')
  const plainServiceStyles = readFileSync(plainServicePath, 'utf8')
  const adminWorkspaceStyles = readFileSync(adminWorkspacePath, 'utf8')

  assert.match(plainServiceStyles, /Plain service presentation/)
  assert.match(plainServiceStyles, /--surface-page:\s*#fff/)
  assert.match(plainServiceStyles, /\.service-shell:not\(\.app-shell--home\)/)
  assert.doesNotMatch(
    plainServiceStyles,
    /service-shell--legacy-review|temporary-review-page|legacy-review-surface/,
  )
  assert.doesNotMatch(
    adminWorkspaceStyles,
    /service-shell--legacy-review|temporary-review-page|legacy-review-surface/,
  )
  assert.match(plainServiceStyles, /@media\s*\(prefers-reduced-motion:\s*reduce\)/)
  assert.doesNotMatch(globalStyles, /Plain service presentation/)

  const plainServiceImport = appShell.indexOf("import './plainService.css'")
  const navigationImport = appShell.indexOf("import './homeNavigation.css'")
  assert.ok(plainServiceImport >= 0, 'AppShell imports the plain-service presentation')
  assert.ok(navigationImport > plainServiceImport, 'plain-service styles load before the shell navigation overrides')
})
