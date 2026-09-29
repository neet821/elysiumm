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
  const compactEssayRules = []
  const mobileDrawerRules = []
  const desktopRailRules = []

  resolved.walkRules((rule) => {
    if (rule.selector === '.legacy-old-home--flat .essay-card--compact') {
      compactEssayRules.push({
        media: enclosingMedia(rule),
        padding: rule.nodes.find((node) => node.type === 'decl' && node.prop === 'padding')?.value,
      })
    }
    if (rule.selector.includes('.home-sidebar.home-sidebar--drawer-open > .sidebar-section--records')) {
      mobileDrawerRules.push({
        media: enclosingMedia(rule),
        order: rule.nodes.find((node) => node.type === 'decl' && node.prop === 'order')?.value,
      })
    }
    if (rule.selector === '.legacy-old-home--flat .home-nav') {
      desktopRailRules.push({
        media: enclosingMedia(rule),
        position: rule.nodes.find((node) => node.type === 'decl' && node.prop === 'position')?.value,
        width: rule.nodes.find((node) => node.type === 'decl' && node.prop === 'width')?.value,
      })
    }
  })

  assert.ok(compactEssayRules.some((rule) => rule.media === null && rule.padding === '10px 0 16px'))
  assert.ok(mobileDrawerRules.some((rule) => rule.media === '(max-width: 800px)' && rule.order === '0'))
  assert.ok(desktopRailRules.some((rule) => rule.media === '(min-width: 1101px)' && rule.position === 'fixed' && rule.width === 'var(--home-nav-rail-width)'))
})
