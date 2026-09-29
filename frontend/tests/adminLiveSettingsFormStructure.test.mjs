import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const sourceDir = new URL('../src/', import.meta.url)
const pagePath = new URL('pages/AdminLivePage.jsx', sourceDir)
const formPath = new URL('features/live/AdminLiveSettingsForm.jsx', sourceDir)
const page = readFileSync(pagePath, 'utf8')

test('admin live page composes its feature-owned settings form', () => {
  assert.ok(existsSync(formPath), 'the live feature must own its settings form')
  assert.match(page, /<AdminLiveSettingsForm\b/)
  assert.doesNotMatch(page, /<form\s+onSubmit=\{saveSettings\}/)

  const form = readFileSync(formPath, 'utf8')
  for (const control of ['直播名称', '推流画质', '直播延时', '观看方式', 'OBS 服务器', '保存设置']) {
    assert.ok(form.includes(control), `settings form must retain ${control}`)
  }
  assert.match(form, /onSubmit=\{onSave\}/)
})
