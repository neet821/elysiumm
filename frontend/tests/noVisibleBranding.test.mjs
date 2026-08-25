import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const root = new URL('../', import.meta.url)
const read = (relativePath) => readFileSync(new URL(relativePath, root), 'utf8')

const visibleSources = [
  'index.html',
  'src/components/Footer.jsx',
  'src/components/brand/BrandLogo.jsx',
  'src/components/auth/LoginCard.jsx',
  'src/components/collection/CollectionTransferPanel.jsx',
  'src/navigation.js',
  'src/pages/BooksPage.jsx',
  'src/pages/ContentHomePage.jsx',
  'src/pages/HomePage.jsx',
  'src/pages/RegisterPage.jsx',
  'src/pages/TransferPage.jsx',
  '../src/ui/createHud.js',
  '../src/routes/routeConfig.js',
  'public/brand/elysium-mark.svg',
]

test('public-facing sources contain no Elysium branding text', () => {
  for (const relativePath of visibleSources) {
    const source = read(relativePath).replaceAll('elysium-mark.svg', '')
    assert.doesNotMatch(source, /elysium/i, relativePath)
  }
})
