import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import {
  Avatar,
  Button,
  Card,
  EmptyState,
  Input,
  RoomStatus,
  Skeleton,
  Tabs,
  Tag,
} from '../src/components/ui/index.js'

const TAB_ITEMS = [
  { value: 'archive', label: 'Archive', content: 'Archive panel' },
  { value: 'photos', label: 'Photos', content: 'Photos panel' },
  { value: 'notes', label: 'Notes', content: 'Notes panel' },
]

function ControlledTabs() {
  const [value, setValue] = useState('archive')
  return <Tabs items={TAB_ITEMS} value={value} onChange={setValue} label="Archive sections" />
}

describe('Blue Album UI primitives', () => {
  it('disables and announces a loading button without hiding its label', () => {
    render(<Button isLoading>Save changes</Button>)

    const button = screen.getByRole('button', { name: 'Save changes' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
  })

  it('connects an input with its label, hint, and validation error', () => {
    render(
      <Input
        id="email"
        label="Email address"
        hint="Used only for account recovery."
        error="Enter a valid email address."
      />,
    )

    const input = screen.getByLabelText('Email address')
    const hint = screen.getByText('Used only for account recovery.')
    const error = screen.getByText('Enter a valid email address.')
    const describedBy = input.getAttribute('aria-describedby').split(' ')

    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(describedBy).toEqual(expect.arrayContaining([hint.id, error.id]))
  })

  it('keeps an interactive card semantically neutral for nested links and buttons', () => {
    render(<Card interactive data-testid="card"><a href="/content">Open content</a></Card>)

    const card = screen.getByTestId('card')
    expect(card).not.toHaveAttribute('role', 'button')
    expect(card).not.toHaveAttribute('tabindex')
  })

  it('supports arrow, Home, and End keyboard selection for tabs', async () => {
    const user = userEvent.setup()
    render(<ControlledTabs />)

    const archive = screen.getByRole('tab', { name: 'Archive' })
    archive.focus()
    await user.keyboard('{ArrowRight}')

    const photos = screen.getByRole('tab', { name: 'Photos' })
    expect(photos).toHaveFocus()
    expect(photos).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Photos panel')

    await user.keyboard('{End}')
    expect(screen.getByRole('tab', { name: 'Notes' })).toHaveFocus()
    await user.keyboard('{Home}')
    expect(archive).toHaveFocus()
  })

  it('exports the supporting visual primitives with useful accessible output', () => {
    render(
      <>
        <Tag>私密</Tag>
        <Avatar name="Blue Album" />
        <RoomStatus status="live" />
        <Skeleton label="正在载入归档" />
        <EmptyState title="这里还没有内容" description="请添加第一项内容。" />
      </>,
    )

    expect(screen.getByText('私密')).toBeInTheDocument()
    expect(screen.getByLabelText('Blue Album')).toBeInTheDocument()
    expect(screen.getByText('进行中')).toBeInTheDocument()
    expect(screen.getByLabelText('正在载入归档')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '这里还没有内容' })).toBeInTheDocument()
  })
})
