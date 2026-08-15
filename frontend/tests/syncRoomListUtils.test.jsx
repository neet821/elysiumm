import { describe, expect, it } from 'vitest'

import {
  formatEmptyRoomCountdown,
  getOnlineMemberCount,
} from '../src/pages/syncRoomListUtils.js'

describe('同步房间列表状态格式化', () => {
  it('优先使用后端返回的在线成员数', () => {
    expect(getOnlineMemberCount({ member_count: 2, current_members: 99 })).toBe(2)
    expect(getOnlineMemberCount({ member_count: 0 })).toBe(0)
  })

  it('按空房时间显示十分钟倒计时并在过期时保持零点格式', () => {
    expect(formatEmptyRoomCountdown(
      '2026-08-15T00:00:00Z',
      Date.parse('2026-08-15T00:01:30Z'),
    )).toBe('08:30 后关闭')
    expect(formatEmptyRoomCountdown(
      '2026-08-15T00:00:00Z',
      Date.parse('2026-08-15T00:10:01Z'),
    )).toBe('00:00 后关闭')
  })
})
