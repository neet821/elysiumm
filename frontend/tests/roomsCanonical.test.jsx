import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import RoomsPage from '../src/pages/RoomsPage.jsx'

describe('rooms hub', () => {
  it('exposes the canonical music and watch room entry points', () => {
    render(<MemoryRouter><RoomsPage /></MemoryRouter>)

    expect(screen.getByRole('link', { name: /进入听歌房/ })).toHaveAttribute('href', '/rooms/music')
    expect(screen.getByRole('link', { name: /进入观影房/ })).toHaveAttribute('href', '/rooms/watch')
    expect(screen.queryByText('房间')).not.toBeInTheDocument()
    expect(screen.queryByText(/选择一个空间/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Elysium/i)).not.toBeInTheDocument()
  })
})
