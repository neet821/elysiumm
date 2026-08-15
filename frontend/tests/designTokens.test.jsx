import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function readRule(source, selector) {
  const ruleStart = source.indexOf(`${selector} {`)
  if (ruleStart === -1) return ''

  const bodyStart = source.indexOf('{', ruleStart)
  let depth = 0
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1
    if (source[index] === '}') depth -= 1
    if (depth === 0) return source.slice(ruleStart, index + 1)
  }

  return ''
}

describe('Blue Album brand foundation', () => {
  afterEach(() => {
    document.documentElement.classList.remove('dark')
  })

  it('exposes the required semantic tokens to the document', () => {
    const css = fs.readFileSync(path.join(frontendRoot, 'src', 'index.css'), 'utf8')
    const style = document.createElement('style')
    style.dataset.testStyle = 'tokens'
    style.textContent = readRule(css, ':root')
    document.head.append(style)
    const styles = getComputedStyle(document.documentElement)
    const tokens = [
      '--surface-page',
      '--surface-card',
      '--text-primary',
      '--accent-blue',
      '--radius-control',
      '--radius-dialog',
      '--motion-fast',
      '--motion-slow',
      '--ease-standard',
      '--ease-emphasized',
    ]

    for (const token of tokens) {
      expect(styles.getPropertyValue(token).trim(), `${token} should be defined`).not.toBe('')
    }
  })

  it('ships exactly the approved color and monochrome icon-only logo assets', () => {
    const brandDirectory = path.join(frontendRoot, 'public', 'brand')
    const filenames = fs.readdirSync(brandDirectory).sort()

    expect(filenames).toEqual(['blue-album-logo-color.svg', 'blue-album-logo-mono.svg', 'elysium-mark.svg'])
    for (const filename of filenames) {
      const svg = fs.readFileSync(path.join(brandDirectory, filename), 'utf8')
      expect(svg).toContain('<svg')
      expect(svg).not.toMatch(/<text\b/i)
      expect(svg).not.toMatch(/<image\b/i)
      expect(svg).not.toContain('Blue Album')
    }
  })

  it('uses the Elysium mark as the favicon without remote font dependencies', () => {
    const html = fs.readFileSync(path.join(frontendRoot, 'index.html'), 'utf8')
    expect(html).toMatch(/rel=["']icon["'][^>]+href=["']\/brand\/elysium-mark\.svg["']/)
    expect(html).not.toContain('fonts.googleapis.com')
    expect(html).not.toContain('fonts.gstatic.com')
  })
})
