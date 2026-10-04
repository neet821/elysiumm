import fs from 'node:fs'
import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import HomeSidebar from '../src/features/content/HomeSidebar.jsx'

vi.mock('../src/pages/SyncRoomList.jsx', () => ({ default: () => <p>房间内容</p> }))
vi.mock('../src/features/music/MusicPlaylistManager.jsx', () => ({ default: () => <p>歌单内容</p> }))
import MusicLobbyPage from '../src/pages/MusicLobbyPage.jsx'

describe('plain unified presentation', () => {
  it('shows bounded previews and explicit routes to all supporting content', () => {
    render(<MemoryRouter><HomeSidebar
      essays={Array.from({ length: 4 }, (_, i) => ({ slug: `e${i}`, title: `随笔${i}` }))}
      records={Array.from({ length: 5 }, (_, i) => ({ slug: `r${i}`, title: `记录${i}`, type: 'book' }))}
      fullEssayBySlug={{}}
    /></MemoryRouter>)
    expect(document.querySelectorAll('.record-card')).toHaveLength(3)
    expect(document.querySelectorAll('.essay-card')).toHaveLength(2)
    expect(screen.getByRole('link', { name: '查看全部记录' })).toHaveAttribute('href', '/content/record')
    expect(screen.getByRole('link', { name: '查看全部随笔' })).toHaveAttribute('href', '/content/essay')
    expect(document.querySelector('.sidebar-scroll-viewport')).toBeNull()
  })

  it('keeps rooms and playlists mounted and supports keyboard switching in the mobile tabs', async () => {
    const user = userEvent.setup()
    render(<MusicLobbyPage />)
    const rooms = screen.getByRole('tab', { name: '一起听' })
    const playlists = screen.getByRole('tab', { name: '我的歌单' })
    expect(rooms).toHaveAttribute('aria-selected', 'true')
    await user.click(playlists)
    expect(playlists).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('房间内容')).toBeInTheDocument()
    expect(screen.getByText('歌单内容')).toBeInTheDocument()
    await user.keyboard('{ArrowLeft}')
    expect(rooms).toHaveFocus()
    expect(rooms).toHaveAttribute('aria-selected', 'true')
  })

  it('bounds the home canvas and keeps navigation labelled with touch-sized controls', () => {
    const layout = fs.readFileSync('src/features/content/articleFlowLayout.css', 'utf8')
    const navigation = fs.readFileSync('src/components/layout/homeNavigation.css', 'utf8')
    expect(layout).toMatch(/max-width:\s*1200px/)
    expect(layout).not.toMatch(/overflow-y:\s*auto|linear-gradient|box-shadow:\s*0|transition:/)
    expect(navigation).toMatch(/min-height:\s*44px/)
    expect(navigation).not.toMatch(/home-nav__action-label\s*\{[^}]*display:\s*none/)
    expect(navigation).not.toMatch(/home-nav-rail-width|scale\(|backdrop-filter/)
  })

  it('keeps the music player functional without a decorative canvas or lyric scaling', () => {
    const player = fs.readFileSync('src/features/music/MusicRoomPlayer.jsx', 'utf8')
    const stage = fs.readFileSync('src/features/music/musicRoomStage.css', 'utf8')
    expect(player).not.toMatch(/ParticleField|requestAnimationFrame/)
    expect(player).toContain('听歌房音频播放器')
    expect(stage).not.toMatch(/gradient|box-shadow|scale\(|transition:/)
  })

  it('preserves meaningful media sizing and online indicators without utility motion', () => {
    const stage = fs.readFileSync('src/features/music/musicRoomStage.css', 'utf8')
    const panels = fs.readFileSync('src/features/music/musicRoomPanels.css', 'utf8')
    const global = fs.readFileSync('src/index.css', 'utf8')
    expect(stage).toMatch(/__cover\.is-large\s*\{[^}]*flex:\s*none/)
    expect(panels).toMatch(/span\.is-online\s*\{\s*background:\s*var\(--accent-success\)/)
    expect(global).toMatch(/\.animate-pulse\s*\{\s*animation:\s*none/)
    expect(global).toMatch(/\.transition-colors\s*\{\s*transition:\s*none/)
  })
})
