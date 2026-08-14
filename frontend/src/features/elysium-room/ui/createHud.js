const MODE_LABELS = Object.freeze({
  dawn: '清晨',
  day: '白天',
  dusk: '黄昏',
  night: '夜晚',
})

const SCENERY_LABELS = Object.freeze({
  nature: '自然',
  city: '城市',
  cloudy: '多云',
  night: '夜景',
})

export function createHud(mount, { onCamera, onTimeMode }) {
  mount.innerHTML = `
    <div class="hud" data-testid="hud">
      <header class="hud-top">
        <div class="hud-status">
          <span class="pill" data-testid="environment-readout"></span>
          <span class="pill" data-testid="scenery-label"></span>
          <span class="pill" data-testid="album-label"></span>
          <span class="pill" data-testid="lamp-state">台灯：关</span>
          <span class="pill" data-testid="record-state">唱片机：未播放</span>
        </div>
      </header>
      <div class="hud-bottom">
        <section class="hud-group" aria-label="视角">
          <h2>视角</h2>
          <div class="button-row">
            <button type="button" data-testid="camera-overview" data-camera="overview">总览</button>
            <button type="button" data-testid="camera-desk" data-camera="desk">书桌</button>
            <button type="button" data-testid="camera-right" data-camera="right">唱片墙</button>
          </div>
        </section>
        <section class="hud-group" aria-label="时间">
          <h2>时间</h2>
          <div class="button-row">
            <button type="button" data-testid="time-auto" data-time="auto">自动</button>
            <button type="button" data-testid="time-day" data-time="day">白天</button>
            <button type="button" data-testid="time-dusk" data-time="dusk">黄昏</button>
            <button type="button" data-testid="time-night" data-time="night">夜晚</button>
          </div>
        </section>
        <p class="hover-hint" data-testid="hover-hint" aria-live="polite"></p>
      </div>
    </div>
  `

  const cameraButtons = [...mount.querySelectorAll('[data-camera]')]
  const timeButtons = [...mount.querySelectorAll('[data-time]')]
  const readout = mount.querySelector('[data-testid="environment-readout"]')
  const sceneryLabel = mount.querySelector('[data-testid="scenery-label"]')
  const albumLabel = mount.querySelector('[data-testid="album-label"]')
  const lampState = mount.querySelector('[data-testid="lamp-state"]')
  const recordState = mount.querySelector('[data-testid="record-state"]')
  const hint = mount.querySelector('[data-testid="hover-hint"]')

  cameraButtons.forEach((button) => {
    button.addEventListener('click', () => onCamera?.(button.dataset.camera))
  })
  timeButtons.forEach((button) => {
    button.addEventListener('click', () => onTimeMode?.(button.dataset.time))
  })

  return {
    render(snapshot) {
      const modeLabel = snapshot.isAuto
        ? `自动 · ${MODE_LABELS[snapshot.mode] ?? snapshot.mode}`
        : `手动 · ${MODE_LABELS[snapshot.mode] ?? snapshot.mode}`
      readout.textContent = modeLabel
      sceneryLabel.textContent = `窗外：${SCENERY_LABELS[snapshot.scenery] ?? snapshot.scenery}`
      albumLabel.textContent = `唱片架：第 ${snapshot.albumIndex + 1} 张`
      lampState.textContent = `台灯：${snapshot.lampOn ? '开' : '关'}`
      recordState.textContent = `唱片机：${snapshot.recordOn ? '播放中' : '未播放'}`
      timeButtons.forEach((button) => {
        const active = button.dataset.time === (snapshot.isAuto ? 'auto' : snapshot.mode)
        button.setAttribute('aria-pressed', String(active))
      })
    },
    setCamera(name) {
      cameraButtons.forEach((button) => {
        button.setAttribute('aria-pressed', String(button.dataset.camera === name))
      })
    },
    setHint(text) {
      hint.textContent = text || ''
    },
  }
}
