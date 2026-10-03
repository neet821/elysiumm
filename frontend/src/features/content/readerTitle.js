const normalizeTitle = (value) => String(value || '').replace(/\s+/g, ' ').trim()

const headingText = (node) => node.value || node.alt || (node.children || []).map(headingText).join('')

// Display-only: never change the original note or remove later headings.
export function omitDuplicateMarkdownTitle(title) {
  return () => (tree) => {
    const first = tree.children[0]
    if (first?.type === 'heading' && first.depth === 1 && normalizeTitle(headingText(first)) === normalizeTitle(title)) {
      tree.children.shift()
    }
  }
}

export function omitDuplicateHtmlTitle(html, title) {
  if (!title) return html
  const document = new DOMParser().parseFromString(html, 'text/html')
  const first = document.body.firstElementChild
  if (first?.tagName === 'H1' && normalizeTitle(first.textContent) === normalizeTitle(title)) first.remove()
  return document.body.innerHTML
}
