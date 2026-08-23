import { useState } from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  CommandPalette,
  Dialog,
  Drawer,
  ToastProvider,
  useToast,
} from '../src/components/ui/index.js'

function DialogHarness() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open details</button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Archive details"
        description="Review this item before continuing."
      >
        <button type="button">Confirm archive</button>
      </Dialog>
    </>
  )
}

function ToastHarness() {
  const toast = useToast()
  return (
    <button
      type="button"
      onClick={() => toast.push({ title: 'Saved', description: 'Your changes are ready.', duration: 1000 })}
    >
      Save
    </button>
  )
}

function CommandHarness({ onSelect }) {
  const [open, setOpen] = useState(true)
  return (
    <CommandPalette
      open={open}
      onOpenChange={setOpen}
      onSelect={onSelect}
      items={[
        { id: 'archive', label: 'Open Archive', keywords: ['writing'] },
        { id: 'photos', label: 'Browse Photos', keywords: ['images'] },
      ]}
    />
  )
}

afterEach(() => {
  vi.useRealTimers()
})

describe('Dialog and Drawer', () => {
  it('labels the dialog, locks scrolling, closes with Escape, and restores focus', async () => {
    const user = userEvent.setup()
    render(<DialogHarness />)

    const trigger = screen.getByRole('button', { name: 'Open details' })
    await user.click(trigger)

    const dialog = screen.getByRole('dialog', { name: 'Archive details' })
    expect(dialog).toHaveAccessibleDescription('Review this item before continuing.')
    expect(document.body.style.overflow).toBe('hidden')
    expect(screen.getByRole('button', { name: '关闭对话框' })).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.body.style.overflow).toBe('')
    expect(trigger).toHaveFocus()
  })

  it('closes only when the dialog backdrop itself is pressed', () => {
    const onOpenChange = vi.fn()
    render(
      <Dialog open onOpenChange={onOpenChange} title="Preview">
        <button type="button">Keep open</button>
      </Dialog>,
    )

    fireEvent.mouseDown(screen.getByRole('dialog'))
    expect(onOpenChange).not.toHaveBeenCalled()
    fireEvent.mouseDown(screen.getByTestId('dialog-backdrop'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('renders a labelled side drawer with the same dismissal contract', () => {
    const onOpenChange = vi.fn()
    render(<Drawer open onOpenChange={onOpenChange} title="Navigation" side="left">Menu</Drawer>)

    expect(screen.getByRole('dialog', { name: 'Navigation' })).toHaveAttribute('data-side', 'left')
    fireEvent.mouseDown(screen.getByTestId('drawer-backdrop'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})

describe('Toast and Command Palette', () => {
  it('announces a toast and removes it after its duration', () => {
    vi.useFakeTimers()
    render(<ToastProvider><ToastHarness /></ToastProvider>)

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByRole('status')).toHaveTextContent('Saved')
    expect(screen.getByRole('status')).toHaveTextContent('Your changes are ready.')

    act(() => vi.advanceTimersByTime(1000))
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
  })

  it('focuses search, filters authorized commands, and selects the active result', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(<CommandHarness onSelect={onSelect} />)

    const search = screen.getByRole('textbox', { name: '搜索页面' })
    expect(search).toHaveFocus()
    await user.type(search, 'photos')
    expect(screen.queryByText('Open Archive')).not.toBeInTheDocument()
    expect(screen.getByText('Browse Photos')).toBeInTheDocument()

    await user.keyboard('{Enter}')
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'photos' }))
    expect(screen.queryByRole('dialog', { name: '快捷导航' })).not.toBeInTheDocument()
  })
})
