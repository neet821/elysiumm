import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const sourceDir = new URL('../src/', import.meta.url)
const globalStyles = readFileSync(new URL('index.css', sourceDir), 'utf8')
const uiEntry = readFileSync(new URL('components/ui/index.js', sourceDir), 'utf8')
const uiStylesPath = new URL('components/ui/ui.css', sourceDir)
const uiStyles = existsSync(uiStylesPath) ? readFileSync(uiStylesPath, 'utf8') : ''

test('shared UI primitives load their styles through the UI entrypoint', () => {
  assert.match(uiEntry, /import ['"]\.\/ui\.css['"]/, 'the shared UI entrypoint must load its stylesheet')
  assert.match(uiStyles, /^@tailwind components;/m, 'the UI stylesheet must include the Tailwind component layer directive it expands')
  assert.doesNotMatch(globalStyles, /^@tailwind components;/m, 'the Tailwind component layer must be expanded only once')

  for (const selector of [
    '.ui-button {',
    '.ui-input {',
    '.ui-card {',
    '.ui-avatar {',
    '.ui-room-status {',
    '.ui-empty-state {',
    '.ui-dialog {',
    '.ui-drawer {',
    '.ui-toast {',
    '.ui-command-palette {',
  ]) {
    assert.ok(uiStyles.includes(selector), `the UI stylesheet must own ${selector}`)
  }
  assert.match(uiStyles, /@layer components\s*\{/, 'component styles must preserve their cascade layer')
  assert.match(uiStyles, /@media \(hover: hover\)/, 'interactive hover states must stay with shared UI components')
  assert.match(uiStyles, /@media \(prefers-reduced-motion: reduce\)/, 'motion preferences must stay with shared UI components')
  assert.doesNotMatch(globalStyles, /^\s*\.ui-[\w-]+/m, 'the global entry must not own shared UI component selectors')
  assert.doesNotMatch(globalStyles, /@keyframes ui-/, 'UI component animations must not remain global')
})
