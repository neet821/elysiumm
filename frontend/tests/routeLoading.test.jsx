import { lazy } from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import path from 'node:path'

import { RouteLoadingFallback, RouteSuspense } from '../src/routes.jsx'


describe('route-level loading', () => {
  it('shows one named polite status while a route module loads', async () => {
    let resolveRoute
    const LazyFixture = lazy(() => new Promise((resolve) => {
      resolveRoute = () => resolve({ default: () => <h1>Deferred route</h1> })
    }))

    render(<RouteSuspense><LazyFixture /></RouteSuspense>)

    expect(screen.getByRole('status', { name: '正在载入页面' })).toHaveAttribute('aria-live', 'polite')
    resolveRoute()
    expect(await screen.findByRole('heading', { name: 'Deferred route' })).toBeInTheDocument()
  })

  it('keeps the loading fallback independently renderable for error boundaries', () => {
    render(<RouteLoadingFallback />)
    expect(screen.getByRole('status', { name: '正在载入页面' })).toBeInTheDocument()
  })

  it('loads public, account, editor, room, game and administrator pages on demand', () => {
    const source = readFileSync(
      path.join(process.cwd(), 'src/routes.jsx'),
      'utf8',
    )
    for (const page of (
      ['ArchivePage', 'BooksPage', 'PrivateCollectionPage', 'PostEditorPage',
        'MineradioPage', 'GameRoomPage', 'AdminFilesPage']
    )) {
      expect(source).toMatch(new RegExp(`lazy\\(\\(\\) => import\\(["']\\./pages/${page}`))
      expect(source).not.toMatch(new RegExp(`import ${page} from`))
    }
    expect(source).toContain('<RouteSuspense>')
  })
})
