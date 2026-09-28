import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const source = new URL('../src/', import.meta.url)
const shell = readFileSync(new URL('components/admin/AdminShell.jsx', source), 'utf8')
const homepage = readFileSync(new URL('pages/AdminHomepagePage.jsx', source), 'utf8')
const routes = readFileSync(new URL('routes.jsx', source), 'utf8')
const globalStyles = readFileSync(new URL('index.css', source), 'utf8')
const consoleStylesPath = new URL('features/admin/adminConsole.css', source)
const consoleStyles = existsSync(consoleStylesPath)
  ? readFileSync(consoleStylesPath, 'utf8')
  : ''
const homepageStylesPath = new URL('features/admin/adminHomepage.css', source)
const homepageStyles = existsSync(homepageStylesPath)
  ? readFileSync(homepageStylesPath, 'utf8')
  : ''

test('admin styles load with their lazy page modules instead of the global stylesheet', () => {
  assert.match(shell, /import ['"]\.\.\/\.\.\/features\/admin\/adminConsole\.css['"]/, 'the admin shell must own its stylesheet')
  assert.match(routes, /const AdminShell = lazy\(\(\) => import\('\.\/components\/admin\/AdminShell'\)\)/, 'the admin styles must remain lazy-loaded with the route')
  assert.match(globalStyles, /@layer base, admin-components, components, utilities;/, 'global cascade order must keep Tailwind utilities above lazy admin component styles')
  assert.match(homepage, /import ['"]\.\.\/features\/admin\/adminHomepage\.css['"]/, 'the homepage page must own its stylesheet')
  assert.match(routes, /const AdminHomepagePage = lazy\(\(\) => import\('\.\/pages\/AdminHomepagePage'\)\)/, 'homepage styles must remain lazy-loaded with their page')
  assert.match(homepageStyles, /@layer admin-components\s*\{/, 'admin homepage rules must retain a component cascade layer')

  for (const selector of ['.admin-shell__rail {', '.admin-dashboard__recent {', '.admin-page-heading {', '.admin-empty {']) {
    assert.ok(consoleStyles.includes(selector), `the admin console stylesheet must own ${selector}`)
    assert.doesNotMatch(globalStyles, new RegExp(`(?:^|\\n)${selector.replaceAll('.', '\\.').replace(' {', '\\s*\\{')}`), `global styles must not own ${selector.trim()}`)
  }

  assert.ok(homepageStyles.includes('.admin-homepage__form {'), 'the homepage feature stylesheet must own the homepage form')
  assert.doesNotMatch(globalStyles, /\.admin-homepage__form\s*\{/, 'global styles must not own the homepage form')

  assert.match(globalStyles, /\.admin-inline-error\s*\{/, 'the shared transfer and admin error utility must remain globally available')
})
