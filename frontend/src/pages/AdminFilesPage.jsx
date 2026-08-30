import { Check, Copy, Download, FileDown, FolderSync, Link2, LogOut, RefreshCw, Trash2, Upload } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { API_ENDPOINTS, isTransferHost } from '../config.js'
import apiClient from '../utils/request.js'
import { TRANSFER_CURRENT_TOKEN_KEY, formatTransferDate, transferPublicUrl } from '../utils/transfer.js'
import { useAuth } from '../contexts/AuthContext.jsx'

function formatSize(value) {
  const bytes = Number(value) || 0
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let size = bytes / 1024
  let unit = units[0]
  for (let i = 1; i < units.length && size >= 1024; i += 1) { size /= 1024; unit = units[i] }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${unit}`
}

const detail = (reason, fallback) => {
  const value = reason?.response?.data?.detail
  return typeof value === 'string' ? value : fallback
}

export default function AdminFilesPage() {
  const { logout } = useAuth()
  const [sync, setSync] = useState({ status: 'loading', path: '', items: [] })
  const [transfers, setTransfers] = useState([])
  const [error, setError] = useState('')
  const [transfer, setTransfer] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [copied, setCopied] = useState(false)
  const fixedTransferHost = isTransferHost()

  const loadSync = useCallback(async (nextPath = '') => {
    setSync({ status: 'loading', path: nextPath, items: [] })
    try {
      const statusResponse = await apiClient.get(API_ENDPOINTS.ADMIN_FILE_SYNC_STATUS)
      const status = statusResponse.data?.status || 'offline'
      if (status !== 'online') {
        setSync({ status, path: nextPath, items: [] })
        setError(status === 'auth_failed' ? '文件同步鉴权失败。' : '电脑未连接，文件同步暂不可用。')
        return
      }
      const browse = await apiClient.get(API_ENDPOINTS.ADMIN_FILE_SYNC_BROWSE, { params: { path: nextPath } })
      setSync({ status: 'online', path: browse.data?.path || nextPath, items: Array.isArray(browse.data?.items) ? browse.data.items.filter((item) => !item.path.endsWith('/')) : [] })
    } catch (reason) {
      const status = reason.response?.status === 502 ? 'auth_failed' : 'offline'
      setSync({ status, path: nextPath, items: [] })
      setError(status === 'auth_failed' ? '文件同步鉴权失败。' : '电脑未连接，文件同步暂不可用。')
    }
  }, [])

  const loadTransfers = useCallback(async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_TRANSFERS)
      setTransfers(Array.isArray(response.data) ? response.data : [])
    } catch (reason) {
      setError(detail(reason, '中转链接暂时无法载入。'))
    }
  }, [])

  const loadCurrentTransfer = useCallback(async () => {
    const token = localStorage.getItem(TRANSFER_CURRENT_TOKEN_KEY)
    if (!token) return
    try {
      await apiClient.get(`/api/transfers/${token}`)
      setTransfer({ token, url: transferPublicUrl(token), ready: true })
    } catch (reason) {
      if (reason.response?.status === 404) localStorage.removeItem(TRANSFER_CURRENT_TOKEN_KEY)
      else setError(detail(reason, '中转链接暂时无法载入。'))
    }
  }, [])

  useEffect(() => {
    loadSync('')
    loadTransfers()
    loadCurrentTransfer()
  }, [loadCurrentTransfer, loadSync, loadTransfers])

  async function uploadTransfer(event) {
    const input = event.currentTarget
    const file = input.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadProgress(0)
    setError('')
    try {
      let token = transfer?.token
      if (!token) {
        const response = await apiClient.post(API_ENDPOINTS.ADMIN_TRANSFERS)
        token = response.data?.token
        if (!token) throw new Error('中转链接创建失败。')
        setTransfer({ token, url: transferPublicUrl(token), ready: false })
      }
      const uploadResponse = await apiClient.put(`/api/transfers/${token}`, file, {
        timeout: 0,
        params: { filename: file.name },
        headers: { 'Content-Type': 'application/octet-stream' },
        onUploadProgress: ({ loaded, total }) => {
          if (total) setUploadProgress(Math.min(100, Math.round((loaded / total) * 100)))
        },
      })
      const nextToken = uploadResponse.data?.token || token
      localStorage.setItem(TRANSFER_CURRENT_TOKEN_KEY, nextToken)
      setTransfer({ token: nextToken, url: transferPublicUrl(nextToken), ready: true })
      await loadTransfers()
    } catch (reason) {
      if (reason.response?.status === 404) setTransfer(null)
      setError(detail(reason, '文件上传失败。'))
    } finally {
      setUploading(false)
      setUploadProgress(0)
      input.value = ''
    }
  }

  async function copyShareLink() {
    if (!transfer?.url) return
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
      await navigator.clipboard.writeText(transfer.url)
    } catch {
      const input = document.createElement('input')
      input.value = transfer.url
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      input.remove()
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  async function deleteTransfer(id) {
    if (!window.confirm('提前销毁这个中转链接？')) return
    await apiClient.delete(API_ENDPOINTS.ADMIN_TRANSFER(id))
    await loadTransfers()
  }

  async function downloadSync(item) {
    try {
      const itemPath = [sync.path, item.path].filter(Boolean).join('/')
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_FILE_SYNC_DOWNLOAD, { params: { path: itemPath }, responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = item.name
      link.rel = 'noopener'
      link.style.display = 'none'
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (reason) {
      setError(detail(reason, '文件下载失败，请确认电脑仍在线。'))
    }
  }

  const syncOnline = sync.status === 'online'
  const syncRoot = `/home/neet821/Public${sync.path ? `/${sync.path}` : ''}`

  return <section className="admin-files-page">
    <header className="admin-page-heading">
      <div><p>管理控制台 / 文件</p><h2>文件</h2></div>
      <div className="admin-page-heading__actions">
        <button className="admin-icon-button" type="button" onClick={() => { loadSync(sync.path); loadTransfers(); loadCurrentTransfer() }} aria-label="刷新文件"><RefreshCw size={16} /></button>
        {fixedTransferHost && <button className="admin-icon-button" type="button" onClick={() => logout()}><LogOut size={16} /><span>退出登录</span></button>}
      </div>
    </header>
    {error && <p className="admin-inline-error" role="alert">{error}</p>}
    <div className="admin-file-cards">
      <article className={`admin-file-card${syncOnline ? '' : ' admin-file-card--disabled'}`}>
        <div className="admin-file-card__icon"><FolderSync size={21} /></div>
        <h3>文件同步</h3>
        <div className={`admin-file-status admin-file-status--${sync.status}`}>{sync.status === 'online' ? '在线' : sync.status === 'loading' ? '连接中' : sync.status === 'auth_failed' ? '鉴权失败' : '电脑未连接'}</div>
        <div className="admin-file-browser" aria-disabled={!syncOnline}>
          <div className="admin-file-browser__bar"><span>{syncRoot}</span>{sync.path && <button type="button" disabled={!syncOnline} onClick={() => loadSync(sync.path.split('/').slice(0, -1).join('/'))}>上一级</button>}</div>
          {syncOnline && sync.items.map((item) => <button className="admin-file-browser__item" type="button" disabled={!syncOnline} key={item.path} onClick={() => downloadSync(item)}><FileDown size={15} /><span>{item.name}</span><Download size={14} /></button>)}
          {sync.status === 'online' && !sync.items.length && <p className="admin-empty">暂无文件。</p>}
          {sync.status !== 'online' && sync.status !== 'loading' && <p className="admin-empty">电脑未连接，文件同步暂不可用。</p>}
        </div>
      </article>
      <article className="admin-file-card">
        <div className="admin-file-card__icon admin-file-card__icon--violet"><Link2 size={21} /></div>
        <h3>文件中转</h3>
        <label className="admin-transfer-upload"><Upload size={15} />{uploading ? '上传中…' : transfer?.ready ? '继续上传文件' : '选择文件上传'}<input aria-label="选择文件上传" type="file" onChange={uploadTransfer} disabled={uploading} /></label>
        {uploading && <div className="transfer-upload-progress"><progress aria-label="上传进度" max="100" value={uploadProgress} /><span>{uploadProgress}%</span></div>}
        {transfer?.ready && <div className="admin-transfer-created"><span>中转链接</span><div className="transfer-share-row"><input aria-label="中转链接" readOnly value={transfer.url} onFocus={(event) => event.target.select()} /><button type="button" onClick={copyShareLink}>{copied ? <Check size={15} /> : <Copy size={15} />}<span>{copied ? '已复制' : '复制分享链接'}</span></button></div></div>}
        <div className="admin-transfer-list">{transfers.map((item) => <div className="admin-transfer-row" key={item.id}><span><strong>{item.files?.map((file) => file.name).join(' · ') || '暂无文件'}</strong><small>{formatSize(item.total_bytes)} / {formatSize(item.max_bytes)} · 过期：{formatTransferDate(item.expires_at)}</small></span><button type="button" onClick={() => deleteTransfer(item.id)} aria-label="销毁中转链接"><Trash2 size={15} /></button></div>)}</div>
      </article>
    </div>
  </section>
}
