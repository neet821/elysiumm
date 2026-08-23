import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Copy,
  Download,
  FileText,
  FolderSync,
  Laptop,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCw,
  Search,
  ShieldOff,
  Trash2,
  Upload,
} from 'lucide-react'
import { Button, Card, Dialog, EmptyState, Input, Skeleton, Tabs, Tag } from '../components/ui/index.js'
import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'

const EMPTY_SYNC = { devices: [], events: [], files: [] }

function errorDetail(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim().slice(0, 240)
  if (Array.isArray(detail)) {
    const message = detail.map((item) => item?.msg).filter(Boolean).join(', ')
    if (message) return message.slice(0, 240)
  }
  return fallback
}

function formatSize(value) {
  const bytes = Number(value) || 0
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = bytes / 1024
  let unit = units[0]
  for (let index = 1; index < units.length && size >= 1024; index += 1) {
    size /= 1024
    unit = units[index]
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${unit}`
}

function formatDate(value, fallback = '暂无') {
  if (!value) return fallback
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? fallback : date.toLocaleString('zh-CN')
}

const statusLabel = (value) => ({ online: '在线', offline: '离线', revoked: '已撤销', synced: '已同步', uploading: '上传中', success: '成功', failed: '失败', paused: '已暂停' }[value] || value)
const actionLabel = (value) => ({ pause: '暂停', resume: '恢复', revoke: '撤销', rotate: '更新凭据', scan: '扫描' }[value] || value)
const eventLabel = (value) => ({ delete: '删除文件', failure: '同步失败', upsert: '更新文件' }[value] || '同步事件')

function StatusMessage({ error, notice }) {
  if (error) return <p className="admin-files__message admin-files__message--error" role="alert">{error}</p>
  if (notice) return <p className="admin-files__message admin-files__message--success" role="status">{notice}</p>
  return null
}

export default function AdminFilesPage() {
  const [activeTab, setActiveTab] = useState('manual')
  const [manualFiles, setManualFiles] = useState([])
  const [syncData, setSyncData] = useState(EMPTY_SYNC)
  const [manualLoading, setManualLoading] = useState(true)
  const [syncLoading, setSyncLoading] = useState(true)
  const [manualError, setManualError] = useState('')
  const [syncError, setSyncError] = useState('')
  const [notice, setNotice] = useState('')
  const [busyAction, setBusyAction] = useState('')
  const [uploadProgress, setUploadProgress] = useState(null)
  const [deviceFormOpen, setDeviceFormOpen] = useState(false)
  const [deviceName, setDeviceName] = useState('')
  const [credentialDays, setCredentialDays] = useState('90')
  const [oneTimeSecret, setOneTimeSecret] = useState(null)
  const fileInputRef = useRef(null)

  const loadManual = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setManualLoading(true)
    setManualError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_FILES)
      setManualFiles(Array.isArray(response.data) ? response.data : [])
    } catch (error) {
      setManualError(errorDetail(error, '手动文件暂时无法载入。'))
    } finally {
      if (!quiet) setManualLoading(false)
    }
  }, [])

  const loadSync = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setSyncLoading(true)
    setSyncError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.PUBLIC_SYNC_DASHBOARD)
      setSyncData({ ...EMPTY_SYNC, ...response.data })
    } catch (error) {
      setSyncError(errorDetail(error, '同步信息暂时无法载入。'))
    } finally {
      if (!quiet) setSyncLoading(false)
    }
  }, [])

  const refreshAll = useCallback(async () => {
    setNotice('')
    await Promise.all([loadManual(), loadSync()])
  }, [loadManual, loadSync])

  useEffect(() => {
    refreshAll()
  }, [refreshAll])

  const uploadManualFile = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    const body = new FormData()
    body.append('file', file)
    setBusyAction('manual-upload')
    setUploadProgress(0)
    setManualError('')
    setNotice('')
    try {
      await apiClient.post(API_ENDPOINTS.ADMIN_FILE_UPLOAD, body, {
        onUploadProgress: ({ loaded, total }) => {
          if (total) setUploadProgress(Math.min(100, Math.round((loaded * 100) / total)))
        },
      })
      setUploadProgress(100)
      setNotice(`${file.name} 已上传。`)
      await loadManual({ quiet: true })
    } catch (error) {
      setManualError(errorDetail(error, '文件上传失败。'))
    } finally {
      setBusyAction('')
      setUploadProgress(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const downloadManualFile = async (file) => {
    let objectUrl = null
    setBusyAction(`download-${file.id}`)
    setManualError('')
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_FILE_DOWNLOAD(file.id), {
        responseType: 'blob',
      })
      objectUrl = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.download = file.name
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
    } catch (error) {
      setManualError(errorDetail(error, '文件下载失败。'))
    } finally {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      setBusyAction('')
    }
  }

  const deleteManualFile = async (file) => {
    if (!window.confirm(`确定删除 ${file.name} 吗？`)) return
    setBusyAction(`delete-${file.id}`)
    setManualError('')
    try {
      await apiClient.delete(API_ENDPOINTS.ADMIN_FILE(file.id))
      setManualFiles((items) => items.filter((item) => item.id !== file.id))
      setNotice(`${file.name} 已删除。`)
    } catch (error) {
      setManualError(errorDetail(error, '文件删除失败。'))
    } finally {
      setBusyAction('')
    }
  }

  const createDevice = async (event) => {
    event.preventDefault()
    const normalizedName = deviceName.trim()
    if (!normalizedName) return
    const body = new FormData()
    body.append('name', normalizedName)
    body.append('expires_in_days', credentialDays)
    setBusyAction('device-create')
    setSyncError('')
    try {
      const response = await apiClient.post(API_ENDPOINTS.PUBLIC_SYNC_DEVICES, body)
      setOneTimeSecret({ name: response.data.name, value: response.data.device_token })
      setDeviceFormOpen(false)
      setDeviceName('')
      await loadSync({ quiet: true })
    } catch (error) {
      setSyncError(errorDetail(error, '同步设备创建失败。'))
    } finally {
      setBusyAction('')
    }
  }

  const deviceAction = async (device, action) => {
    if (action === 'revoke' && !window.confirm(`确定撤销 ${device.name} 吗？`)) return
    const endpoint = {
      pause: API_ENDPOINTS.PUBLIC_SYNC_PAUSE(device.id),
      resume: API_ENDPOINTS.PUBLIC_SYNC_RESUME(device.id),
      revoke: API_ENDPOINTS.PUBLIC_SYNC_REVOKE(device.id),
      rotate: API_ENDPOINTS.PUBLIC_SYNC_ROTATE(device.id),
      scan: API_ENDPOINTS.PUBLIC_SYNC_SCAN(device.id),
    }[action]
    const body = action === 'rotate' ? new FormData() : undefined
    if (body) body.append('expires_in_days', '90')
    setBusyAction(`${action}-${device.id}`)
    setSyncError('')
    setNotice('')
    try {
      const response = body
        ? await apiClient.post(endpoint, body)
        : await apiClient.post(endpoint)
      if (action === 'rotate') {
        setOneTimeSecret({ name: device.name, value: response.data.device_token })
      } else {
        setNotice(`${device.name}：${actionLabel(action)}已完成。`)
      }
      await loadSync({ quiet: true })
    } catch (error) {
      setSyncError(errorDetail(error, `${actionLabel(action)}操作失败。`))
    } finally {
      setBusyAction('')
    }
  }

  const copySecret = async () => {
    if (!oneTimeSecret?.value) return
    try {
      await navigator.clipboard.writeText(oneTimeSecret.value)
      setNotice('设备凭据已复制。')
    } catch {
      setSyncError('凭据复制失败，请手动选择并复制。')
    }
  }

  const manualPanel = manualLoading ? (
    <div className="admin-files__loading" role="status" aria-label="正在载入手动文件"><Skeleton /><Skeleton /></div>
  ) : (
    <section className="admin-files__panel">
      <header className="admin-files__toolbar">
        <div><h2>手动文件</h2><p>管理员私有上传，下载时必须验证身份。</p></div>
        <label className="ui-button ui-button--primary ui-button--md admin-files__upload-label">
          <Upload size={16} aria-hidden="true" />
          <span>{busyAction === 'manual-upload' ? '正在上传…' : '上传文件'}</span>
          <input ref={fileInputRef} type="file" aria-label="上传手动文件" disabled={busyAction === 'manual-upload'} onChange={uploadManualFile} />
        </label>
      </header>
      {uploadProgress !== null && <div className="admin-files__upload-progress" role="progressbar" aria-label="手动文件上传进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow={uploadProgress}><span style={{ width: `${uploadProgress}%` }} /></div>}
      {manualFiles.length === 0 ? (
        <EmptyState icon={<FileText />} title="还没有手动文件" description="需要临时私密交接时，可在这里上传文件。" />
      ) : (
        <div className="admin-files__records">
          {manualFiles.map((file) => <Card as="article" className="admin-files__record" key={file.id}><div><FileText size={19} aria-hidden="true" /><div><h3>{file.name}</h3><p>{formatSize(file.size)} · {formatDate(file.modified)}</p></div></div><div className="admin-files__record-actions"><Button variant="secondary" size="sm" aria-label={`下载 ${file.name}`} isLoading={busyAction === `download-${file.id}`} onClick={() => downloadManualFile(file)}><Download size={15} aria-hidden="true" /> 下载</Button><Button variant="danger" size="sm" aria-label={`删除 ${file.name}`} isLoading={busyAction === `delete-${file.id}`} onClick={() => deleteManualFile(file)}><Trash2 size={15} aria-hidden="true" /> 删除</Button></div></Card>)}
        </div>
      )}
    </section>
  )

  const devicesPanel = syncLoading ? (
    <div className="admin-files__loading" role="status" aria-label="正在载入设备"><Skeleton /><Skeleton /></div>
  ) : (
    <section className="admin-files__panel">
      <header className="admin-files__toolbar"><div><h2>同步设备</h2><p>签发、更新、暂停、扫描或撤销设备的同步权限。</p></div><Button onClick={() => setDeviceFormOpen(true)}><Plus size={16} aria-hidden="true" /> 添加设备</Button></header>
      {syncData.devices.length === 0 ? <EmptyState icon={<Laptop />} title="还没有同步设备" description="创建设备后会获得仅显示一次的设置凭据。" action={<Button onClick={() => setDeviceFormOpen(true)}>添加设备</Button>} /> : <div className="admin-files__device-grid">{syncData.devices.map((device) => <Card as="article" className="admin-files__device" key={device.id}><header><div><h3>{device.name}</h3><p>{device.root_name} · 凭据尾号 {device.token_hint}</p></div><Tag tone={device.revoked_at ? 'danger' : device.status === 'online' ? 'success' : 'neutral'}>{device.revoked_at ? '已撤销' : statusLabel(device.status)}</Tag></header><dl><div><dt>最近出现</dt><dd>{formatDate(device.last_seen_at)}</dd></div><div><dt>凭据到期</dt><dd>{formatDate(device.token_expires_at, '永不过期')}</dd></div></dl><div className="admin-files__device-actions"><Button size="sm" variant="secondary" aria-label={`${device.is_paused ? '恢复' : '暂停'} ${device.name}`} disabled={Boolean(device.revoked_at)} isLoading={busyAction === `${device.is_paused ? 'resume' : 'pause'}-${device.id}`} onClick={() => deviceAction(device, device.is_paused ? 'resume' : 'pause')}>{device.is_paused ? <Play size={15} /> : <Pause size={15} />} {device.is_paused ? '恢复' : '暂停'}</Button><Button size="sm" variant="secondary" aria-label={`扫描 ${device.name}`} disabled={Boolean(device.revoked_at)} isLoading={busyAction === `scan-${device.id}`} onClick={() => deviceAction(device, 'scan')}><Search size={15} /> 扫描</Button><Button size="sm" variant="secondary" aria-label={`更新 ${device.name} 的凭据`} isLoading={busyAction === `rotate-${device.id}`} onClick={() => deviceAction(device, 'rotate')}><RotateCw size={15} /> 更新凭据</Button><Button size="sm" variant="danger" aria-label={`撤销 ${device.name}`} disabled={Boolean(device.revoked_at)} isLoading={busyAction === `revoke-${device.id}`} onClick={() => deviceAction(device, 'revoke')}><ShieldOff size={15} /> 撤销</Button></div></Card>)}</div>}
    </section>
  )

  const syncedPanel = syncLoading ? (
    <div className="admin-files__loading" role="status" aria-label="正在载入同步文件"><Skeleton /><Skeleton /></div>
  ) : (
    <section className="admin-files__panel"><header className="admin-files__toolbar"><div><h2>同步文件</h2><p>查看已发布文件和正在验证的上传任务。</p></div></header>{syncData.files.length === 0 ? <EmptyState icon={<FolderSync />} title="还没有同步文件" description="设备完成上传后，文件会显示在这里。" /> : <div className="admin-files__records">{syncData.files.map((file) => <Card as="article" className="admin-files__sync-file" key={file.id}><div><h3>{file.relative_path}</h3><p>{formatSize(file.sync_status === 'uploading' ? file.bytes_transferred : file.file_size)} · {formatDate(file.last_synced_at)}</p></div><div className="admin-files__sync-state"><Tag tone={file.sync_status === 'synced' ? 'success' : 'neutral'}>{statusLabel(file.sync_status)}</Tag><div className="admin-files__progress" role="progressbar" aria-label={`${file.relative_path} 的上传进度`} aria-valuemin="0" aria-valuemax="100" aria-valuenow={file.progress_percent}><span style={{ width: `${Math.max(0, Math.min(100, file.progress_percent))}%` }} /></div><small>{file.progress_percent}%</small></div></Card>)}</div>}</section>
  )

  const activityPanel = syncLoading ? (
    <div className="admin-files__loading" role="status" aria-label="正在载入同步动态"><Skeleton /><Skeleton /></div>
  ) : (
    <section className="admin-files__panel"><header className="admin-files__toolbar"><div><h2>同步动态</h2><p>显示有限范围的同步事件，不暴露内部错误细节。</p></div></header>{syncData.events.length === 0 ? <EmptyState icon={<RefreshCw />} title="还没有同步动态" description="最近的上传、删除和安全失败标记会显示在这里。" /> : <ol className="admin-files__activity">{syncData.events.map((event) => <li key={event.id}><div><strong>{eventLabel(event.event_type)}</strong><span>{event.relative_path || '设备事件'}</span></div><div><Tag tone={event.status === 'success' ? 'success' : event.status === 'failed' ? 'danger' : 'neutral'}>{statusLabel(event.status)}</Tag><time dateTime={event.created_at}>{formatDate(event.created_at)}</time></div></li>)}</ol>}</section>
  )

  const tabs = [
    { value: 'manual', label: '手动文件', content: manualPanel },
    { value: 'devices', label: '同步设备', content: devicesPanel },
    { value: 'synced', label: '同步文件', content: syncedPanel },
    { value: 'activity', label: '同步动态', content: activityPanel },
  ]

  return (
    <section className="page-shell admin-files">
      <header className="admin-files__intro"><div><p className="page-shell__eyebrow">管理员空间</p><h1>文件</h1><p>在同一个私有空间管理手动交接和 Public Sync 文件。</p></div><Button variant="secondary" onClick={refreshAll} isLoading={manualLoading || syncLoading}><RefreshCw size={16} aria-hidden="true" /> 刷新</Button></header>
      <StatusMessage error={activeTab === 'manual' ? manualError : deviceFormOpen ? '' : syncError} notice={notice} />
      <Tabs label="文件管理" value={activeTab} onChange={(value) => { setActiveTab(value); setNotice('') }} items={tabs} />

      <Dialog open={deviceFormOpen} onOpenChange={setDeviceFormOpen} title="添加同步设备" description="创建后只显示一次设置凭据。">
        <form className="admin-files__device-form" onSubmit={createDevice}>{syncError && <p className="admin-files__message admin-files__message--error" role="alert">{syncError}</p>}<Input label="设备名称" maxLength={100} required value={deviceName} onChange={(event) => setDeviceName(event.target.value)} /><label className="ui-field"><span className="ui-field__label">凭据有效期</span><select className="ui-input" value={credentialDays} onChange={(event) => setCredentialDays(event.target.value)}><option value="30">30 天</option><option value="90">90 天</option><option value="365">365 天</option></select></label><div className="admin-files__dialog-actions"><Button variant="secondary" onClick={() => setDeviceFormOpen(false)}>取消</Button><Button type="submit" isLoading={busyAction === 'device-create'}>创建设备</Button></div></form>
      </Dialog>

      <Dialog open={Boolean(oneTimeSecret)} onOpenChange={(open) => { if (!open) setOneTimeSecret(null) }} title="保存设备凭据" description="关闭此窗口后将无法再次显示这项内容。">
        <div className="admin-files__secret"><p>{oneTimeSecret?.name}</p><code>{oneTimeSecret?.value}</code><div className="admin-files__dialog-actions"><Button variant="secondary" aria-label="复制凭据" onClick={copySecret}><Copy size={16} aria-hidden="true" /> 复制凭据</Button><Button aria-label="关闭凭据窗口" onClick={() => setOneTimeSecret(null)}>我已保存</Button></div></div>
      </Dialog>
    </section>
  )
}
