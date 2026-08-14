import { ROUTES } from '../routes/routeConfig.js'

export class RouteOverlay {
  constructor(mount, { onBack = () => {} } = {}) {
    this.mount = mount
    this.onBack = onBack
    this.current = null
    mount.innerHTML = `
      <div class="route-backdrop" data-testid="route-overlay" hidden>
        <article class="route-panel">
          <header class="route-header">
            <h2 data-testid="route-title"></h2>
            <button type="button" data-testid="route-back">返回房间</button>
          </header>
          <p class="route-subtitle" data-testid="route-subtitle"></p>
          <ul class="route-items" data-testid="route-items"></ul>
          <p class="route-note">内容页正在扩充中，导航流程已可用。</p>
        </article>
      </div>
    `
    this.root = mount.firstElementChild
    this.title = mount.querySelector('[data-testid="route-title"]')
    this.subtitle = mount.querySelector('[data-testid="route-subtitle"]')
    this.items = mount.querySelector('[data-testid="route-items"]')
    mount.querySelector('[data-testid="route-back"]').addEventListener('click', () => this.onBack())
  }

  open(routeKey) {
    const route = ROUTES[routeKey]
    if (!route) return
    this.current = routeKey
    this.title.textContent = route.title
    this.subtitle.textContent = route.subtitle
    this.items.innerHTML = route.items
      .map(
        (item) => `
          <li>
            <h3>${item.title}</h3>
            <p>${item.body}</p>
          </li>
        `,
      )
      .join('')
    this.root.hidden = false
  }

  close() {
    this.current = null
    this.root.hidden = true
  }

  isOpen() {
    return this.current !== null
  }
}
