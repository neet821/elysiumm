import assert from 'node:assert/strict'
import test from 'node:test'
import postcss from 'postcss'
import {
  ARTICLE_FLOW_CSS_LAYERS,
  articleFlowCssImports,
  resolveArticleFlowCss,
} from './helpers/articleFlowStyles.mjs'

function enclosingMedia(rule) {
  let parent = rule.parent
  while (parent && parent.type !== 'root') {
    if (parent.type === 'atrule' && parent.name === 'media') return parent.params
    parent = parent.parent
  }
  return null
}

test('homepage stylesheet keeps its cascade layers explicit and ordered', () => {
  assert.deepEqual(articleFlowCssImports(), ARTICLE_FLOW_CSS_LAYERS)

  const resolved = postcss.parse(resolveArticleFlowCss())
  const layoutRules = []
  const sidebarRules = []

  resolved.walkRules((rule) => {
    if (rule.selector === '.legacy-old-home--flat .home-layout') layoutRules.push(rule)
    if (rule.selector === '.legacy-old-home--flat .home-sidebar') sidebarRules.push(rule)
  })

  assert.ok(layoutRules.some((rule) => enclosingMedia(rule) === null && rule.nodes.some((node) => node.prop === 'grid-template-areas' && node.value === '"articles sidebar" "photos photos"')))
  assert.ok(layoutRules.some((rule) => enclosingMedia(rule) === '(max-width: 800px)' && rule.nodes.some((node) => node.prop === 'grid-template-areas' && node.value === '"articles" "sidebar" "photos"')))
  assert.ok(sidebarRules.some((rule) => enclosingMedia(rule) === null && rule.nodes.some((node) => node.prop === 'grid-area' && node.value === 'sidebar')))
  assert.doesNotMatch(resolveArticleFlowCss(), /sidebar-scroll-viewport|sidebar-scroll-cue|home-nav-rail-width/)
})
