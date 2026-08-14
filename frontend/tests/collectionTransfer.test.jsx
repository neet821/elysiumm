import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/utils/request.js', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import CollectionTransferPanel from '../src/components/collection/CollectionTransferPanel.jsx'
import apiClient from '../src/utils/request.js'
import { API_ENDPOINTS } from '../src/config.js'

const backup = {
  id: 17,
  filename: 'bookmarks-20260715.json',
  file_size: 2048,
  sha256: 'abc123def456',
  created_at: '2026-07-15T12:00:00',
}

const dryRunReport = {
  id: 21,
  user_id: 7,
  status: 'completed',
  source_type: 'json',
  imported_count: 3,
  folder_count: 2,
  skipped_count: 1,
  duplicate_count: 1,
  dry_run: true,
  backup_id: null,
  report: { warnings: ['One duplicate URL will be skipped.'] },
  error_message: null,
  created_at: '2026-07-15T12:00:00',
  finished_at: '2026-07-15T12:00:01',
}

function fileWithText(name, type, text) {
  const file = new File([text], name, { type })
  Object.defineProperty(file, 'text', { value: vi.fn(async () => text) })
  return file
}

function renderPanel(onCollectionChanged = vi.fn()) {
  render(<CollectionTransferPanel onCollectionChanged={onCollectionChanged} />)
  return onCollectionChanged
}

describe('Collection import, export, and backup panel', () => {
  beforeEach(() => {
    apiClient.get.mockReset().mockImplementation((url) => {
      if (url === API_ENDPOINTS.BOOKMARK_BACKUPS) return Promise.resolve({ data: [backup] })
      if (url === API_ENDPOINTS.BOOKMARK_EXPORT_JSON) return Promise.resolve({ data: { version: 2 } })
      if (url === API_ENDPOINTS.BOOKMARK_EXPORT_HTML) return Promise.resolve({ data: new Blob(['<html>']) })
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    apiClient.post.mockReset().mockImplementation((url, _body, config) => {
      if (url === API_ENDPOINTS.BOOKMARK_IMPORT_JSON && config?.params?.dry_run) {
        return Promise.resolve({ data: dryRunReport })
      }
      if (url === API_ENDPOINTS.BOOKMARK_IMPORT_JSON) {
        return Promise.resolve({ data: { ...dryRunReport, dry_run: false, backup_id: 17 } })
      }
      if (url === API_ENDPOINTS.BOOKMARK_IMPORT_HTML && config?.params?.dry_run) {
        return Promise.resolve({ data: { ...dryRunReport, source_type: 'html' } })
      }
      if (url === API_ENDPOINTS.BOOKMARK_IMPORT_HTML) {
        return Promise.resolve({ data: { ...dryRunReport, source_type: 'html', dry_run: false, backup_id: 17 } })
      }
      if (url === API_ENDPOINTS.BOOKMARK_BACKUPS) return Promise.resolve({ data: backup })
      if (url === API_ENDPOINTS.BOOKMARK_BACKUP_RESTORE(17)) {
        return Promise.resolve({ data: { ...dryRunReport, dry_run: false, backup_id: 17 } })
      }
      return Promise.reject(new Error(`Unexpected POST ${url}`))
    })
    Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:test') })
    Object.defineProperty(window.URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  it('requires a JSON dry run, shows the report, and confirms the real import', async () => {
    const user = userEvent.setup()
    const onCollectionChanged = renderPanel()
    const file = fileWithText('collection.json', 'application/json', '{"version":2}')
    await screen.findByText('bookmarks-20260715.json')

    await user.upload(screen.getByLabelText('JSON 收藏文件'), file)
    await user.click(screen.getByRole('button', { name: '预检 JSON 导入' }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      API_ENDPOINTS.BOOKMARK_IMPORT_JSON,
      '{"version":2}',
      {
        headers: { 'Content-Type': 'application/json' },
        params: { dry_run: true },
      },
    ))
    expect(await screen.findByText('3 个收藏可导入')).toBeInTheDocument()
    expect(screen.getByText('2 个文件夹可导入')).toBeInTheDocument()
    expect(screen.getByText('1 个重复项')).toBeInTheDocument()
    expect(screen.getByText('One duplicate URL will be skipped.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '确认导入' }))
    const dialog = screen.getByRole('dialog', { name: '导入 collection.json' })
    await user.click(within(dialog).getByRole('button', { name: '立即导入' }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      API_ENDPOINTS.BOOKMARK_IMPORT_JSON,
      '{"version":2}',
      { headers: { 'Content-Type': 'application/json' } },
    ))
    expect(await screen.findByText('已自动创建安全备份 #17。')).toBeInTheDocument()
    expect(onCollectionChanged).toHaveBeenCalledTimes(1)
  })

  it('supports HTML dry run and both safe exports', async () => {
    const user = userEvent.setup()
    renderPanel()
    const html = '<!DOCTYPE NETSCAPE-Bookmark-file-1><DL><p></DL>'
    const file = fileWithText('browser-bookmarks.html', 'text/html', html)
    await screen.findByText('bookmarks-20260715.json')

    await user.upload(screen.getByLabelText('HTML 收藏文件'), file)
    await user.click(screen.getByRole('button', { name: '预检 HTML 导入' }))
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      API_ENDPOINTS.BOOKMARK_IMPORT_HTML,
      html,
      {
        headers: { 'Content-Type': 'text/html' },
        params: { dry_run: true },
      },
    ))

    await user.click(screen.getByRole('button', { name: '导出 JSON' }))
    await user.click(screen.getByRole('button', { name: '导出 HTML' }))
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.BOOKMARK_EXPORT_JSON)
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.BOOKMARK_EXPORT_HTML, { responseType: 'blob' })
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(2)
  })

  it('keeps the staged report after an import error and restores a verified backup explicitly', async () => {
    const user = userEvent.setup()
    renderPanel()
    const file = fileWithText('collection.json', 'application/json', '{"version":2}')
    await screen.findByText('bookmarks-20260715.json')
    await user.upload(screen.getByLabelText('JSON 收藏文件'), file)
    await user.click(screen.getByRole('button', { name: '预检 JSON 导入' }))
    await screen.findByText('3 个收藏可导入')

    apiClient.post.mockRejectedValueOnce({ response: { data: { detail: 'Import rolled back safely' } } })
    await user.click(screen.getByRole('button', { name: '确认导入' }))
    let dialog = screen.getByRole('dialog', { name: '导入 collection.json' })
    await user.click(within(dialog).getByRole('button', { name: '立即导入' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Import rolled back safely')
    expect(within(dialog).getByText('3 个收藏可导入')).toBeInTheDocument()
    expect(screen.getByText('已选择 collection.json')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: '取消' }))
    await user.click(screen.getByRole('button', { name: '恢复 bookmarks-20260715.json' }))
    dialog = screen.getByRole('dialog', { name: '恢复 bookmarks-20260715.json' })
    fireEvent.click(within(dialog).getByLabelText('替换现有收藏'))
    await user.click(within(dialog).getByRole('button', { name: '恢复备份' }))

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      API_ENDPOINTS.BOOKMARK_BACKUP_RESTORE(17),
      { replace_existing: true },
    ))
    expect(await screen.findByText('备份已恢复。')).toBeInTheDocument()
  })
})
