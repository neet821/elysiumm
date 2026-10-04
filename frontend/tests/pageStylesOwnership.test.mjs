import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { resolveArticleFlowCss } from './helpers/articleFlowStyles.mjs'

const source = new URL('../src/', import.meta.url)
const routes = readFileSync(new URL('routes.jsx', source), 'utf8')
const globalStyles = readFileSync(new URL('index.css', source), 'utf8')
const transferPage = readFileSync(new URL('pages/TransferPage.jsx', source), 'utf8')
const syncRoomList = readFileSync(new URL('pages/SyncRoomList.jsx', source), 'utf8')
const adminFilesPage = readFileSync(new URL('pages/AdminFilesPage.jsx', source), 'utf8')
const loginPage = readFileSync(new URL('pages/LoginPage.jsx', source), 'utf8')
const registerPage = readFileSync(new URL('pages/RegisterPage.jsx', source), 'utf8')
const contentCatalogPage = readFileSync(new URL('pages/ContentHomePage.jsx', source), 'utf8')
const articleFlowPage = readFileSync(new URL('pages/ArticleFlowHome.jsx', source), 'utf8')
const legacyArticlePage = readFileSync(new URL('pages/LegacyArticlePage.jsx', source), 'utf8')
const transferStylesPath = new URL('features/transfer/transfer.css', source)
const transferStyles = existsSync(transferStylesPath) ? readFileSync(transferStylesPath, 'utf8') : ''
const playerStylesPath = new URL('features/player/player.css', source)
const playerStyles = existsSync(playerStylesPath) ? readFileSync(playerStylesPath, 'utf8') : ''
const authStylesPath = new URL('features/auth/auth.css', source)
const authStyles = existsSync(authStylesPath) ? readFileSync(authStylesPath, 'utf8') : ''
const adminFilesStyles = readFileSync(new URL('features/admin-files/adminFiles.css', source), 'utf8')
const legacyArticleStylesPath = new URL('features/content/legacyArticle.css', source)
const legacyArticleStyles = existsSync(legacyArticleStylesPath) ? readFileSync(legacyArticleStylesPath, 'utf8') : ''
const articleFlowBaseStylesPath = new URL('features/content/articleFlowBase.css', source)
const articleFlowBaseStyles = existsSync(articleFlowBaseStylesPath) ? readFileSync(articleFlowBaseStylesPath, 'utf8') : ''
const articleFlowStyles = resolveArticleFlowCss()
const contentCatalogStyles = readFileSync(new URL('pages/contentHome.css', source), 'utf8')

test('public transfer styles load with the lazy transfer page', () => {
  assert.match(transferPage, /import ['"]\.\.\/features\/transfer\/transfer\.css['"]/, 'the transfer page must own its stylesheet')
  assert.match(routes, /const TransferPage = lazy\(\(\) => import\('\.\/pages\/TransferPage'\)\)/, 'transfer styles must remain lazy-loaded')

  for (const selector of ['.transfer-page {', '.transfer-page__meta {', '.transfer-page__files {']) {
    assert.ok(transferStyles.includes(selector), `the transfer stylesheet must own ${selector}`)
  }
  assert.doesNotMatch(globalStyles, /\.transfer-page(?:__[\w-]+)?/, 'transfer page selectors must not remain global')

  assert.match(transferStyles, /@media\s*\(max-width:\s*760px\)/, 'transfer page responsive rules must stay with the page')
  assert.match(globalStyles, /\.admin-inline-error\s*\{/, 'the shared error presentation must remain global')
})

test('sync room share controls load from their lazy page and legacy room-player styles are retired', () => {
  assert.match(syncRoomList, /import ['"]\.\.\/features\/player\/player\.css['"]/, 'the sync room page must own its feature stylesheet')
  assert.match(routes, /const SyncRoomList = lazy\(\(\) => import\('\.\/pages\/SyncRoomList'\)\)/, 'sync room styles must remain lazy-loaded')
  assert.match(playerStyles, /\.room-share-button\s*\{/, 'the player feature stylesheet must own the room share control')
  assert.match(playerStyles, /\.room-share-button:hover,\s*\.room-share-button:focus-visible\s*\{/, 'share hover and keyboard-focus states must be retained')
  assert.doesNotMatch(globalStyles, /\.room-share-button(?:__[\w-]+)?/, 'the global stylesheet must not own the page-specific share control')
  assert.doesNotMatch(globalStyles, /\.room-player-[\w-]+\s*\{/, 'unmounted legacy room-player presentation rules must not inflate global CSS')
})

test('admin transfer-link controls stay within the lazy admin files feature', () => {
  assert.match(adminFilesPage, /import ['"]\.\.\/features\/admin-files\/adminFiles\.css['"]/, 'the admin files page must load its feature stylesheet')
  assert.match(routes, /const AdminFilesPage = lazy\(\(\) => import\('\.\/pages\/AdminFilesPage'\)\)/, 'admin Files styles must remain lazy-loaded')
  assert.match(adminFilesStyles, /\.transfer-share-row\s*\{/, 'admin files must own the share-row layout')
  assert.match(adminFilesStyles, /\.transfer-share-row input\s*\{/, 'admin files must own the share-link input')
  assert.doesNotMatch(globalStyles, /\.transfer-share-row\b/, 'transfer-link controls must not remain global')
})

test('authentication layout styles load only with the lazy login and registration routes', () => {
  assert.match(routes, /const LoginPage = lazy\(\(\) => import\('\.\/pages\/LoginPage'\)\)/, 'login should not force auth page code into the initial bundle')
  assert.match(routes, /const RegisterPage = lazy\(\(\) => import\('\.\/pages\/RegisterPage'\)\)/, 'registration should not force auth page code into the initial bundle')
  assert.match(loginPage, /import ['"]\.\.\/features\/auth\/auth\.css['"]/, 'login must load auth styles with its route')
  assert.match(registerPage, /import ['"]\.\.\/features\/auth\/auth\.css['"]/, 'registration must load auth styles with its route')
  assert.match(authStyles, /\.auth-form-field__input--leading\s*\{/, 'auth feature must own input adornment spacing')
  assert.match(authStyles, /\.service-shell:has\(\.auth-page\)/, 'auth feature must own its viewport shell rules')
  assert.doesNotMatch(globalStyles, /\.auth-form-field|\.auth-page/, 'auth-only selectors must not remain global')
})

test('legacy article reader overrides load with the legacy article page', () => {
  const sharedStylesIndex = legacyArticlePage.indexOf("import '../features/content/articleFlowBase.css'")
  const legacyStylesIndex = legacyArticlePage.indexOf("import '../features/content/legacyArticle.css'")

  assert.ok(legacyStylesIndex >= 0, 'the legacy reader must own its route-specific stylesheet')
  assert.ok(sharedStylesIndex >= 0 && sharedStylesIndex < legacyStylesIndex, 'reader overrides must load after the shared article-flow base')
  assert.match(legacyArticleStyles, /\.reader\s*\{[^}]*max-width:\s*720px/)
  assert.match(legacyArticleStyles, /\.legacy-old-home:not\(\.legacy-old-home--flat\) \.reader--article/)
  assert.match(legacyArticleStyles, /@media\s*\(max-width:\s*600px\)/)
  assert.doesNotMatch(
    readFileSync(new URL('pages/contentHome.css', source), 'utf8'),
    /\.service-shell:has\(\.reader--article\)|\.reader--article \.reader-header h1/,
    'reader-only outer-shell rules must not stay in shared content styles',
  )
})

test('content catalog, article flow, and legacy reader own separate stylesheets', () => {
  assert.match(contentCatalogPage, /import ['"]\.\/contentHome\.css['"]/, 'the content catalog must load its own styles')
  assert.match(articleFlowPage, /import ['"]\.\.\/features\/content\/articleFlowBase\.css['"]/, 'the article flow must load its shared base')
  assert.match(articleFlowPage, /import ['"]\.\.\/features\/content\/articleFlow\.css['"]/, 'the article flow must load its page presentation')
  assert.ok(
    articleFlowPage.indexOf("articleFlowBase.css'") < articleFlowPage.indexOf("articleFlow.css'"),
    'base presentation must load before article-flow overrides',
  )
  assert.match(legacyArticlePage, /articleFlowBase\.css/)
  assert.doesNotMatch(legacyArticlePage, /articleFlow\.css/, 'the legacy reader must not download homepage-only presentation')
  assert.match(articleFlowBaseStyles, /\.legacy-old-home \.reader-body/)
  assert.match(articleFlowStyles, /\.legacy-old-home--flat \.article-card--featured/)
  assert.doesNotMatch(contentCatalogStyles, /\.legacy-old-home/, 'catalog styles must not include article stream rules')
})
