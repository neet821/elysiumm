import { ArchiveRestore, Download, FileCheck2, HardDrive, Upload } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { Button, Card, Dialog, EmptyState, Skeleton, Tag } from '../ui/index.js'

function messageFromError(error, fallback) {
  return error?.response?.data?.detail || error?.message || fallback
}

function importEndpoint(format) {
  return format === 'html'
    ? API_ENDPOINTS.BOOKMARK_IMPORT_HTML
    : API_ENDPOINTS.BOOKMARK_IMPORT_JSON
}

function contentType(format) {
  return format === 'html' ? 'text/html' : 'application/json'
}

function readFile(file) {
  if (typeof file?.text === 'function') return file.text()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error('文件读取失败'))
    reader.readAsText(file)
  })
}

function downloadBlob(blob, filename) {
  const objectUrl = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(objectUrl)
}

function formatBytes(value) {
  const bytes = Number(value) || 0
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '日期未知'
  return new Intl.DateTimeFormat('zh-CN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function ImportReport({ job }) {
  if (!job) return null
  const readyCount = job.report?.importable_count ?? job.imported_count ?? 0
  const folderCount = job.report?.folder_count ?? job.folder_count ?? 0
  const duplicateCount = job.report?.duplicate_count ?? job.duplicate_count ?? 0
  const skippedCount = job.report?.skipped_count ?? job.skipped_count ?? 0
  const warnings = Array.isArray(job.report?.warnings) ? job.report.warnings : []
  return (
    <div className="collection-import-report" aria-label="导入报告">
      <div className="collection-import-report__stats">
        <strong>{readyCount} 个收藏可导入</strong>
        <span>{folderCount} 个文件夹可导入</span>
        <span>{duplicateCount} 个重复项</span>
        <span>{skippedCount} 个跳过项</span>
      </div>
      {warnings.length > 0 && (
        <ul>
          {warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      )}
    </div>
  )
}

export default function CollectionTransferPanel({ onCollectionChanged = () => {} }) {
  const [files, setFiles] = useState({ json: null, html: null })
  const [staged, setStaged] = useState(null)
  const [previewJob, setPreviewJob] = useState(null)
  const [completedJob, setCompletedJob] = useState(null)
  const [previewing, setPreviewing] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState('')
  const [backups, setBackups] = useState([])
  const [backupsLoading, setBackupsLoading] = useState(true)
  const [backupError, setBackupError] = useState('')
  const [backupMessage, setBackupMessage] = useState('')
  const [creatingBackup, setCreatingBackup] = useState(false)
  const [restoreBackup, setRestoreBackup] = useState(null)
  const [replaceExisting, setReplaceExisting] = useState(false)
  const [restoring, setRestoring] = useState(false)
  const [restoreError, setRestoreError] = useState('')
  const [exporting, setExporting] = useState('')

  const loadBackups = useCallback(async () => {
    setBackupsLoading(true)
    setBackupError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.BOOKMARK_BACKUPS)
      setBackups(Array.isArray(response.data) ? response.data : [])
    } catch (error) {
      setBackupError(messageFromError(error, '备份暂时无法载入。'))
    } finally {
      setBackupsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadBackups()
  }, [loadBackups])

  const chooseFile = (format, file) => {
    setFiles((current) => ({ ...current, [format]: file || null }))
    setStaged(null)
    setPreviewJob(null)
    setCompletedJob(null)
    setImportError('')
  }

  const previewImport = async (format) => {
    const file = files[format]
    if (!file) return
    setPreviewing(format)
    setImportError('')
    setCompletedJob(null)
    try {
      const body = await readFile(file)
      const response = await apiClient.post(
        importEndpoint(format),
        body,
        {
          headers: { 'Content-Type': contentType(format) },
          params: { dry_run: true },
        },
      )
      setStaged({ body, file, format })
      setPreviewJob(response.data)
    } catch (error) {
      setImportError(messageFromError(error, '导入预检失败。'))
    } finally {
      setPreviewing('')
    }
  }

  const importNow = async () => {
    if (!staged || !previewJob?.dry_run) return
    setImporting(true)
    setImportError('')
    try {
      const response = await apiClient.post(
        importEndpoint(staged.format),
        staged.body,
        { headers: { 'Content-Type': contentType(staged.format) } },
      )
      setCompletedJob(response.data)
      setConfirmOpen(false)
      setBackupMessage('收藏导入已完成。')
      await loadBackups()
      onCollectionChanged()
    } catch (error) {
      setImportError(messageFromError(error, '导入失败，所有变更已安全回退。'))
    } finally {
      setImporting(false)
    }
  }

  const exportCollection = async (format) => {
    setExporting(format)
    setBackupError('')
    try {
      if (format === 'html') {
        const response = await apiClient.get(API_ENDPOINTS.BOOKMARK_EXPORT_HTML, { responseType: 'blob' })
        const blob = response.data instanceof Blob
          ? response.data
          : new Blob([response.data], { type: 'text/html' })
        downloadBlob(blob, `blue-album-collection-${Date.now()}.html`)
      } else {
        const response = await apiClient.get(API_ENDPOINTS.BOOKMARK_EXPORT_JSON)
        downloadBlob(
          new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' }),
          `blue-album-collection-${Date.now()}.json`,
        )
      }
    } catch (error) {
      setBackupError(messageFromError(error, `${format.toUpperCase()} 导出失败。`))
    } finally {
      setExporting('')
    }
  }

  const createBackup = async () => {
    setCreatingBackup(true)
    setBackupError('')
    try {
      await apiClient.post(API_ENDPOINTS.BOOKMARK_BACKUPS)
      setBackupMessage('安全备份已创建。')
      await loadBackups()
    } catch (error) {
      setBackupError(messageFromError(error, '安全备份创建失败。'))
    } finally {
      setCreatingBackup(false)
    }
  }

  const openRestore = (backup) => {
    setRestoreBackup(backup)
    setReplaceExisting(false)
    setRestoreError('')
  }

  const restoreNow = async () => {
    if (!restoreBackup) return
    setRestoring(true)
    setRestoreError('')
    try {
      await apiClient.post(
        API_ENDPOINTS.BOOKMARK_BACKUP_RESTORE(restoreBackup.id),
        { replace_existing: replaceExisting },
      )
      setRestoreBackup(null)
      setBackupMessage('备份已恢复。')
      await loadBackups()
      onCollectionChanged()
    } catch (error) {
      setRestoreError(messageFromError(error, '备份恢复失败，收藏内容没有发生变化。'))
    } finally {
      setRestoring(false)
    }
  }

  return (
    <section className="collection-transfer" aria-labelledby="collection-transfer-title">
      <header className="collection-transfer__intro">
        <div>
          <p className="route-shell__eyebrow">安全传输</p>
          <h2 id="collection-transfer-title">导入、导出与备份</h2>
          <p>所有导入都会先预检，正式导入前自动创建安全备份。</p>
        </div>
        <div className="collection-transfer__exports">
          <Button variant="secondary" isLoading={exporting === 'json'} onClick={() => exportCollection('json')}>
            <Download size={15} aria-hidden="true" /> 导出 JSON
          </Button>
          <Button variant="secondary" isLoading={exporting === 'html'} onClick={() => exportCollection('html')}>
            <Download size={15} aria-hidden="true" /> 导出 HTML
          </Button>
        </div>
      </header>

      {importError && !confirmOpen && <p className="collection-action-error" role="alert">{importError}</p>}
      {backupError && <p className="collection-action-error" role="alert">{backupError}</p>}
      {backupMessage && <p className="collection-action-message" role="status">{backupMessage}</p>}
      {completedJob?.backup_id && (
        <p className="collection-transfer__automatic-backup" role="status">
          <FileCheck2 size={16} aria-hidden="true" /> 已自动创建安全备份 #{completedJob.backup_id}。
        </p>
      )}

      <div className="collection-transfer__import-grid">
        {['json', 'html'].map((format) => (
          <Card key={format} className="collection-import-card">
            <Upload size={20} aria-hidden="true" />
            <div>
              <h3>导入 {format.toUpperCase()}</h3>
              <p>{format === 'json' ? 'Elysium 完整备份。' : '浏览器通用书签文件。'}</p>
            </div>
            <label className="collection-file-field">
              <span>{format.toUpperCase()} 收藏文件</span>
              <input
                type="file"
                accept={format === 'json' ? '.json,application/json' : '.html,.htm,text/html'}
                onChange={(event) => chooseFile(format, event.target.files?.[0])}
              />
            </label>
            {files[format] && <p className="collection-file-field__selected">已选择 {files[format].name}</p>}
            <Button
              variant="secondary"
              disabled={!files[format]}
              isLoading={previewing === format}
              onClick={() => previewImport(format)}
            >
              预检 {format.toUpperCase()} 导入
            </Button>
          </Card>
        ))}
      </div>

      {previewJob && staged && (
        <Card className="collection-transfer__staged">
          <div>
            <p className="route-shell__eyebrow">预检完成</p>
            <h3>{staged.file.name}</h3>
          </div>
          <ImportReport job={previewJob} />
          <Button onClick={() => setConfirmOpen(true)}>确认导入</Button>
        </Card>
      )}

      <section className="collection-backups" aria-labelledby="collection-backups-title">
        <header>
          <div>
            <p className="route-shell__eyebrow">已验证副本</p>
            <h3 id="collection-backups-title">安全备份</h3>
          </div>
          <Button variant="secondary" isLoading={creatingBackup} onClick={createBackup}>
            <HardDrive size={15} aria-hidden="true" /> 创建备份
          </Button>
        </header>
        {backupsLoading ? (
          <div className="collection-backups__loading" aria-label="正在载入备份">
            <Skeleton /><Skeleton />
          </div>
        ) : backups.length === 0 ? (
          <EmptyState
            className="collection-backups__empty"
            icon={<HardDrive size={30} />}
            title="还没有安全备份"
            description="可以立即创建，也可以在正式导入时自动创建。"
          />
        ) : (
          <div className="collection-backups__list">
            {backups.map((backup) => (
              <Card key={backup.id} as="article" className="collection-backup-card">
                <div>
                  <strong>{backup.filename}</strong>
                  <span>{formatDate(backup.created_at)}</span>
                </div>
                <span>{formatBytes(backup.file_size)}</span>
                <code title={backup.sha256 || '无摘要'}>{backup.sha256 ? `${backup.sha256.slice(0, 12)}…` : '无摘要'}</code>
                <Tag tone="success">资料已验证</Tag>
                <Button size="sm" variant="secondary" onClick={() => openRestore(backup)}>
                  <ArchiveRestore size={14} aria-hidden="true" /> 恢复 {backup.filename}
                </Button>
              </Card>
            ))}
          </div>
        )}
      </section>

      <Dialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`导入 ${staged?.file.name || '收藏'}`}
        description="服务器会先创建安全备份，再一次性应用全部已验证内容。"
      >
        {importError && <p className="collection-form__error" role="alert">{importError}</p>}
        <ImportReport job={previewJob} />
        <div className="collection-form__actions">
          <Button variant="danger" isLoading={importing} onClick={importNow}>立即导入</Button>
          <Button variant="ghost" onClick={() => setConfirmOpen(false)}>取消</Button>
        </div>
      </Dialog>

      <Dialog
        open={Boolean(restoreBackup)}
        onOpenChange={(open) => {
          if (!open) setRestoreBackup(null)
        }}
        title={`恢复 ${restoreBackup?.filename || '备份'}`}
        description="恢复前，服务器会验证文件位置、大小和摘要。"
      >
        {restoreError && <p className="collection-form__error" role="alert">{restoreError}</p>}
        <label className="collection-restore-replace">
          <input aria-label="替换现有收藏" type="checkbox" checked={replaceExisting} onChange={(event) => setReplaceExisting(event.target.checked)} />
          <span>
            <strong>替换现有收藏</strong>
            <small>操作前会再次创建安全备份。关闭时将合并内容并跳过重复项。</small>
          </span>
        </label>
        <div className="collection-form__actions">
          <Button variant="danger" isLoading={restoring} onClick={restoreNow}>恢复备份</Button>
          <Button variant="ghost" onClick={() => setRestoreBackup(null)}>取消</Button>
        </div>
      </Dialog>
    </section>
  )
}
