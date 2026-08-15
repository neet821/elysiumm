import { expect, test } from '@playwright/test'

test.describe('Elysium 首页', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())
    await page.reload()
  })

  test('默认载入 3D 房间和简洁顶部导航', async ({ page }) => {
    await expect(page.getByTestId('home-experience')).toHaveAttribute('data-room-mode', '3d')
    await expect(page.locator('#room-canvas')).toHaveAttribute('data-engine', 'three.js r179')
    await expect(page.getByTestId('camera-overview')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Elysium 首页' })).toBeVisible()
    await expect(page.getByRole('link', { name: '工具箱' })).toBeVisible()
    await expect(page.getByRole('link', { name: '登录' })).toBeVisible()
    await expect(page.getByRole('link', { name: '归档' })).toHaveCount(0)
  })

  test('可以切换镜头并记住轻量模式偏好', async ({ page }) => {
    await page.getByTestId('camera-desk').click()
    await expect(page.getByTestId('camera-desk')).toHaveAttribute('aria-pressed', 'true')
    await page.getByRole('button', { name: '切换到轻量模式' }).click()
    await expect(page.getByTestId('home-experience')).toHaveAttribute('data-room-mode', 'lite')
    await page.reload()
    await expect(page.getByTestId('home-experience')).toHaveAttribute('data-room-mode', 'lite')
    await page.getByRole('button', { name: '切换到三维模式' }).click()
    await expect(page.getByTestId('home-experience')).toHaveAttribute('data-room-mode', '3d')
  })

  test('电脑启动器提供正式功能入口', async ({ page }) => {
    await expect(page.locator('#room-canvas')).toHaveAttribute('data-engine', 'three.js r179')
    await page.getByTestId('camera-desk').click()
    await page.waitForFunction(() => window.__ROOM_APP__ && !window.__ROOM_APP__.rig.isTransitioning)
    const monitor = await page.evaluate(() => window.__ROOM_APP__.interactions.screenPositionFor('monitor'))
    await page.mouse.click(monitor.x, monitor.y)
    const dialog = page.getByRole('dialog', { name: '电脑桌面' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('link', { name: '看归档' })).toHaveAttribute('href', '/archive')
    await expect(dialog.getByRole('link', { name: '看直播' })).toHaveAttribute('href', '/live')
    await expect(dialog.getByRole('link', { name: '听音乐' })).toHaveAttribute('href', '/music')
    await expect(dialog.getByRole('link', { name: '工具箱' })).toHaveAttribute('href', '/tools')
    await expect(dialog.getByRole('link', { name: '收藏' })).toHaveAttribute('href', '/collection')
    await expect(dialog.getByRole('link', { name: '书籍' })).toHaveAttribute('href', '/books')
    await expect(dialog.getByRole('link', { name: '桌游' })).toHaveAttribute('href', '/games')
    await expect(dialog.getByRole('link', { name: '账户' })).toHaveAttribute('href', '/account')
  })
})
