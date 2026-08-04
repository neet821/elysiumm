import './styles.css'
import { createEnvironmentState } from './environment/environmentState.js'
import { createPageThemeVariables, environmentPalettes } from './environment/palette.js'

const environment = createEnvironmentState()
const app = document.querySelector('#app')

app.innerHTML = `
  <main class="app-shell">
    <header class="app-header">
      <p class="eyebrow">ELYSIUM</p>
      <h1>3D Room</h1>
      <p class="environment-readout" aria-live="polite"></p>
    </header>
    <section class="room-stage" aria-label="3D room loading area">
      <p>Room foundation ready</p>
    </section>
    <nav class="environment-controls" aria-label="Environment mode">
      <button type="button" data-mode="auto">Auto</button>
      <button type="button" data-mode="dawn">Dawn</button>
      <button type="button" data-mode="day">Day</button>
      <button type="button" data-mode="dusk">Dusk</button>
      <button type="button" data-mode="night">Night</button>
    </nav>
  </main>
`

const readout = app.querySelector('.environment-readout')
const controls = [...app.querySelectorAll('[data-mode]')]
const themeColorMeta = document.querySelector('meta[name="theme-color"]')

function renderEnvironment() {
  const state = environment.getState()
  const palette = environmentPalettes[state.mode]

  for (const [name, value] of Object.entries(createPageThemeVariables(palette))) {
    document.documentElement.style.setProperty(name, value)
  }

  document.documentElement.dataset.environment = state.mode
  themeColorMeta.setAttribute('content', palette.sky)
  readout.textContent = `${state.mode} · ${state.isAuto ? 'auto' : 'manual'}`
  controls.forEach((control) => {
    const selected = control.dataset.mode === (state.isAuto ? 'auto' : state.mode)
    control.setAttribute('aria-pressed', String(selected))
  })
}

controls.forEach((control) => {
  control.addEventListener('click', () => {
    environment.setMode(control.dataset.mode)
    renderEnvironment()
  })
})

renderEnvironment()
window.setInterval(renderEnvironment, 60_000)
