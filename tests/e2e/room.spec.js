import fs from 'node:fs'
import { test, expect } from '@playwright/test'

const SCREENSHOT_DIR = '.superpowers/sdd/2026-08-04-elysium-room/task-8-screenshots'

test.beforeEach(async ({ page }) => {
  page.__errors = []
  page.on('console', (message) => {
    if (message.type() === 'error') page.__errors.push(message.text())
  })
  page.on('pageerror', (error) => page.__errors.push(String(error)))
})

async function waitForApp(page) {
  await page.waitForSelector('#room-canvas')
  await page.waitForFunction(() => globalThis.__ROOM_APP__ !== undefined)
}

async function expectNoErrors(page) {
  expect(page.__errors).toEqual([])
}

async function clickObject(page, id, point = {}) {
  const position = await page.evaluate(({ objectId, point: clickPoint }) => {
    const app = globalThis.__ROOM_APP__
    const found = app.interactions.screenPositionFor(objectId, clickPoint)
    return found ? { x: found.x, y: found.y, behind: found.behind } : null
  }, { objectId: id, point })
  expect(position, `screen position for ${id}`).not.toBeNull()
  expect(position.behind, `${id} should be in front of the camera`).toBe(false)
  await page.mouse.click(position.x, position.y)
}

test('room loads and renders without console errors', async ({ page }) => {
  await page.goto('/')
  await waitForApp(page)
  await expect(page.locator('#room-canvas')).toBeVisible()
  await expect(page.locator('[data-testid="hud"]')).toBeVisible()
  await expect(page.locator('[data-testid="route-overlay"]')).toBeHidden()
  await expectNoErrors(page)
})

test('three fixed cameras switch through animated transitions', async ({ page }) => {
  await page.goto('/')
  await waitForApp(page)

  const cases = [
    ['camera-desk', 'desk', [-1.2, 2.9, 4.2]],
    ['camera-right', 'right', [0.5, 2.85, 0.05]],
    ['camera-overview', 'overview', [-9.8, 6.6, 11.5]],
  ]
  for (const [testId, name, expected] of cases) {
    await page.click(`[data-testid="${testId}"]`)
    await expect(page.locator(`[data-testid="${testId}"]`)).toHaveAttribute('aria-pressed', 'true')
    await page.waitForFunction(() => globalThis.__ROOM_APP__.rig.isTransitioning === false)
    const position = await page.evaluate(() => globalThis.__ROOM_APP__.rig.camera.position.toArray())
    expect(position.map((value) => +value.toFixed(4))).toEqual(expected)
    expect(await page.evaluate(() => globalThis.__ROOM_APP__.rig.getActivePreset())).toBe(name)
  }
  await expectNoErrors(page)
})

test('type A navigation flow works for all four routes and returns to the room', async ({ page }) => {
  const flows = [
    ['monitor', 'projects'],
    ['photoWall', 'gallery'],
    ['books', 'reading'],
    ['moviePoster', 'movies'],
  ]
  for (const [objectId, route] of flows) {
    await page.goto('/')
    await waitForApp(page)
    await clickObject(page, objectId)
    await page.waitForURL(`**/#/${route}`)
    await expect(page.locator('[data-testid="route-overlay"]')).toBeVisible()
    await expect(page.locator('[data-testid="route-title"]')).toHaveText(
      route === 'projects' ? 'Projects' : route === 'gallery' ? 'Gallery' : route === 'reading' ? 'Reading' : 'Movies',
    )
    await page.click('[data-testid="route-back"]')
    await page.waitForFunction(() => globalThis.location.hash === '')
    await expect(page.locator('[data-testid="route-overlay"]')).toBeHidden()
    await page.waitForFunction(() => globalThis.__ROOM_APP__.rig.isTransitioning === false)
    await expectNoErrors(page)
  }
})

test('record player, lamp, album rack, scenery and time mode interactions work', async ({ page }) => {
  await page.goto('/')
  await waitForApp(page)

  const lampPosition = await page.evaluate(() => {
    const position = globalThis.__ROOM_APP__.interactions.screenPositionFor('lamp')
    return position ? { x: position.x, y: position.y } : null
  })
  expect(lampPosition).not.toBeNull()
  await page.mouse.move(lampPosition.x, lampPosition.y)
  await expect(page.locator('[data-testid="hover-hint"]')).toContainText('台灯')
  expect(await page.evaluate(() => document.body.style.cursor)).toBe('pointer')

  await clickObject(page, 'lamp')
  await expect(page.locator('[data-testid="lamp-state"]')).toHaveText('台灯：开')
  await clickObject(page, 'lamp')
  await expect(page.locator('[data-testid="lamp-state"]')).toHaveText('台灯：关')

  await clickObject(page, 'recordPlayer')
  await expect(page.locator('[data-testid="record-state"]')).toHaveText('唱片机：播放中')
  await clickObject(page, 'recordPlayer')
  await expect(page.locator('[data-testid="record-state"]')).toHaveText('唱片机：未播放')

  const albumBefore = await page.locator('[data-testid="album-label"]').textContent()
  await clickObject(page, 'recordRack')
  await expect(page.locator('[data-testid="album-label"]')).not.toHaveText(albumBefore)

  const sceneryBefore = await page.locator('[data-testid="scenery-label"]').textContent()
  await clickObject(page, 'window', { ny: 0.18 })
  await page.waitForFunction((before) => {
    const current = globalThis.__ROOM_APP__.environment.getSnapshot().scenery
    return before.includes('自然') ? current !== 'nature' : current === 'nature'
  }, sceneryBefore)
  await expect(page.locator('[data-testid="scenery-label"]')).not.toHaveText(sceneryBefore)

  await page.click('[data-testid="time-day"]')
  await expect(page.locator('[data-testid="environment-readout"]')).toContainText('白天')
  await page.click('[data-testid="time-night"]')
  await expect(page.locator('[data-testid="environment-readout"]')).toContainText('夜晚')
  await page.click('[data-testid="time-auto"]')
  await expect(page.locator('[data-testid="environment-readout"]')).toContainText('自动')

  await expectNoErrors(page)
})

test('resize and direct route refresh stay stable', async ({ page }) => {
  await page.setViewportSize({ width: 2560, height: 1440 })
  await page.goto('/')
  await waitForApp(page)
  await page.waitForTimeout(600)
  await expectNoErrors(page)

  await page.goto('/#/projects')
  await waitForApp(page)
  await expect(page.locator('[data-testid="route-overlay"]')).toBeVisible()
  await expect(page.locator('[data-testid="route-title"]')).toHaveText('Projects')
  await page.click('[data-testid="route-back"]')
  await page.waitForFunction(() => globalThis.location.hash === '')
  await expect(page.locator('[data-testid="route-overlay"]')).toBeHidden()
  await expectNoErrors(page)
})

test('captures the three camera views at desktop resolutions', async ({ page }) => {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })
  await page.setViewportSize({ width: 1920, height: 1080 })
  await page.goto('/')
  await waitForApp(page)
  await page.click('[data-testid="time-day"]')
  await page.waitForTimeout(400)

  const shots = [
    ['camera-overview', 'overview-1920x1080.png'],
    ['camera-desk', 'desk-1920x1080.png'],
    ['camera-right', 'right-1920x1080.png'],
  ]
  for (const [testId, fileName] of shots) {
    await page.click(`[data-testid="${testId}"]`)
    await page.waitForFunction(() => globalThis.__ROOM_APP__.rig.isTransitioning === false)
    await page.waitForTimeout(250)
    await page.screenshot({ path: `${SCREENSHOT_DIR}/${fileName}` })
  }

  await page.setViewportSize({ width: 2560, height: 1440 })
  await page.click('[data-testid="camera-overview"]')
  await page.waitForFunction(() => globalThis.__ROOM_APP__.rig.isTransitioning === false)
  await page.waitForTimeout(250)
  await page.screenshot({ path: `${SCREENSHOT_DIR}/overview-2560x1440.png` })
  await expectNoErrors(page)
})
