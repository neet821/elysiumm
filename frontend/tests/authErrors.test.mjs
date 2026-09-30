import assert from 'node:assert/strict'
import test from 'node:test'

import { getAuthErrorMessage } from '../src/features/auth/authErrors.js'

test('uses a string detail directly and falls back when detail is absent', () => {
  assert.equal(
    getAuthErrorMessage({ response: { data: { detail: '账号已停用' } } }, '登录失败'),
    '账号已停用',
  )
  assert.equal(getAuthErrorMessage({}, '登录失败'), '登录失败')
  assert.equal(
    getAuthErrorMessage({ response: { data: { detail: '' } } }, '登录失败'),
    '登录失败',
  )
})

test('formats validation arrays and object details compatibly', () => {
  assert.equal(
    getAuthErrorMessage({ response: { data: { detail: [{ msg: '缺少用户名' }, { msg: '密码过短' }] } } }, '注册失败'),
    '缺少用户名, 密码过短',
  )
  assert.equal(
    getAuthErrorMessage({ response: { data: { detail: { msg: '请求无效' } } } }, '注册失败'),
    '请求无效',
  )
  assert.equal(
    getAuthErrorMessage({ response: { data: { detail: { code: 'denied' } } } }, '注册失败'),
    '{"code":"denied"}',
  )
})
