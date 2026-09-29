import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const sourceDir = new URL('../src/', import.meta.url)
const pagePath = new URL('pages/AdminFilesPage.jsx', sourceDir)
const workspacePath = new URL('features/admin-files/useAdminFilesWorkspace.js', sourceDir)
const syncPath = new URL('features/admin-files/useAdminSyncBrowser.js', sourceDir)
const privateFilesPath = new URL('features/admin-files/useAdminPrivateFiles.js', sourceDir)
const transferPath = new URL('features/admin-files/useAdminTransferWorkspace.js', sourceDir)
const page = readFileSync(pagePath, 'utf8')

test('admin files page composes domain-owned sync, private-file, and transfer hooks', () => {
  for (const path of [workspacePath, syncPath, privateFilesPath, transferPath]) {
    assert.ok(existsSync(path), `the admin-files feature must provide ${path.pathname}`)
  }
  assert.match(page, /useAdminFilesWorkspace/)
  assert.doesNotMatch(page, /API_ENDPOINTS|apiClient|utils\/request/)

  const workspace = readFileSync(workspacePath, 'utf8')
  assert.match(workspace, /useAdminSyncBrowser/)
  assert.match(workspace, /useAdminPrivateFiles/)
  assert.match(workspace, /useAdminTransferWorkspace/)
  assert.doesNotMatch(workspace, /API_ENDPOINTS|apiClient/)

  const sync = readFileSync(syncPath, 'utf8')
  const privateFiles = readFileSync(privateFilesPath, 'utf8')
  const transfer = readFileSync(transferPath, 'utf8')
  assert.match(sync, /ADMIN_FILE_SYNC_STATUS/)
  assert.match(sync, /ADMIN_FILE_SYNC_DOWNLOAD/)
  assert.match(privateFiles, /ADMIN_FILES/)
  assert.match(privateFiles, /ADMIN_FILE\(/)
  assert.match(transfer, /useAdminTusUploads/)
  assert.match(transfer, /ADMIN_TRANSFER_CURRENT_LINK/)
  for (const source of [workspace, sync, privateFiles, transfer]) {
    assert.doesNotMatch(source, /from ['"].*pages\//)
  }
})
