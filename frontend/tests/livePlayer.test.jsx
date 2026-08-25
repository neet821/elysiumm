import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

vi.mock('hls.js', () => ({
  default: {
    isSupported: () => false,
  },
}))

import LivePlayer from '../src/features/live/LivePlayer.jsx'


describe('minimal live player', () => {
  it('starts at zero volume without a sound prompt and refreshes on demand', async () => {
    const user = userEvent.setup()
    const onRefresh = vi.fn()
    render(<LivePlayer mediaUrl="" minimal onRefresh={onRefresh} />)

    expect(screen.getByLabelText('直播音量')).toHaveValue('0')
    expect(screen.queryByRole('button', { name: '开启声音' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '刷新直播' }))
    expect(onRefresh).toHaveBeenCalledOnce()
  })
})
