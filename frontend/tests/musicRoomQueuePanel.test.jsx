import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import MusicRoomQueuePanel from '../src/features/music/MusicRoomQueuePanel.jsx'

describe('MusicRoomQueuePanel', () => {
  it('keeps queue voting, room chat, and host settings on the shared room action channel', () => {
    const onAction = vi.fn()
    render(<MusicRoomQueuePanel
      onAction={onAction}
      roomState={{
        canControl: true,
        history: [],
        members: [{ is_online: true, user_id: 7, username: 'host' }],
        messages: [],
        queue: [
          { artist: 'Artist', id: 1, skip_required: 2, skip_votes: 1, status: 'playing', title: 'Current' },
          { artist: 'Artist', id: 2, like_count: 3, liked_by_user_ids: [], status: 'queued', title: 'Next' },
        ],
        room: { host_user_id: 7, id: 5, room_name: 'Blue room', music_skip_vote_percent: 30 },
        syncStatus: 'synced',
        userId: 7,
      }}
    />)

    expect(screen.getByRole('heading', { name: 'Blue room' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '点赞 3' }))
    expect(onAction).toHaveBeenCalledWith({ action: 'like', itemId: 2 })

    fireEvent.change(screen.getByLabelText('聊天消息'), { target: { value: '  hi room  ' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))
    expect(onAction).toHaveBeenCalledWith({ action: 'chat', message: 'hi room' })
    expect(screen.getByLabelText('聊天消息')).toHaveValue('')

    fireEvent.change(screen.getByLabelText('切歌门槛'), { target: { value: '50' } })
    expect(onAction).toHaveBeenCalledWith({ action: 'settings', music_skip_vote_percent: 50 })
  })
})
