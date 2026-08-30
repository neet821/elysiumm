import { Download, RefreshCw, Upload, Copy, Check } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'
import { TRANSFER_CURRENT_TOKEN_KEY, formatTransferDate, transferPublicUrl } from '../utils/transfer.js'

const formatSize = (value) => { const bytes = Number(value) || 0; if (bytes < 1024) return `${bytes} B`; const units = ['KB', 'MB', 'GB']; let size = bytes / 1024; let unit = units[0]; for (let i = 1; i < units.length && size >= 1024; i += 1) { size /= 1024; unit = units[i] } return `${size.toFixed(size >= 10 ? 1 : 2)} ${unit}` }

export default function TransferInboxPage() {
  const [files, setFiles] = useState([]); const [error, setError] = useState(''); const [token, setToken] = useState(() => localStorage.getItem(TRANSFER_CURRENT_TOKEN_KEY) || ''); const [shareUrl, setShareUrl] = useState(() => { const current = localStorage.getItem(TRANSFER_CURRENT_TOKEN_KEY); return current ? transferPublicUrl(current) : '' }); const [copied, setCopied] = useState(false); const [busy, setBusy] = useState(false); const [uploadProgress, setUploadProgress] = useState(0)
  const loadFiles = useCallback(async () => { try { const response = await apiClient.get(API_ENDPOINTS.ADMIN_TRANSFER_FILES); setFiles(Array.isArray(response.data) ? response.data : []); setError('') } catch (reason) { setError(reason.response?.data?.detail || '文件暂时无法载入。') } }, [])
  const acquireLink = useCallback(async () => {
    const stored = localStorage.getItem(TRANSFER_CURRENT_TOKEN_KEY)
    if (stored) {
      try { await apiClient.get(`/api/transfers/${stored}`); setToken(stored); setShareUrl(transferPublicUrl(stored)); return stored } catch (reason) { if (reason.response?.status !== 404) throw reason }
    }
    const response = await apiClient.post(API_ENDPOINTS.ADMIN_TRANSFER_CURRENT_LINK)
    const next = response.data?.token
    if (!next) throw new Error('分享链接创建失败。')
    localStorage.setItem(TRANSFER_CURRENT_TOKEN_KEY, next); setToken(next); setShareUrl(transferPublicUrl(next)); return next
  }, [])
  const load = useCallback(async () => { try { await acquireLink(); await loadFiles() } catch (reason) { setError(reason.response?.data?.detail || reason.message || '文件暂时无法载入。') } }, [acquireLink, loadFiles])
  useEffect(() => { load(); const interval = window.setInterval(loadFiles, 15000); return () => window.clearInterval(interval) }, [load, loadFiles])
  async function upload(event) { const input = event.currentTarget; const file = input.files?.[0]; if (!file) return; setBusy(true); setUploadProgress(0); setError(''); try { const currentToken = token || await acquireLink(); const response = await apiClient.put(`/api/transfers/${currentToken}`, file, { timeout: 0, params: { filename: file.name }, headers: { 'Content-Type': 'application/octet-stream' }, onUploadProgress: ({ loaded, total }) => { if (total) setUploadProgress(Math.min(100, Math.round((loaded / total) * 100))) } }); const next = response.data?.token; if (!next) throw new Error('分享链接更新失败。'); localStorage.setItem(TRANSFER_CURRENT_TOKEN_KEY, next); setToken(next); setShareUrl(transferPublicUrl(next)); await loadFiles() } catch (reason) { setError(reason.response?.data?.detail || reason.message || '文件上传失败。') } finally { setBusy(false); setUploadProgress(0); input.value = '' } }
  async function copyShareLink() { if (!shareUrl) return; try { await navigator.clipboard.writeText(shareUrl) } catch { const input = document.createElement('input'); input.value = shareUrl; document.body.appendChild(input); input.select(); document.execCommand('copy'); input.remove() } setCopied(true); window.setTimeout(() => setCopied(false), 1600) }
  return <section className="transfer-inbox-page"><header><h1>全部文件</h1><button type="button" onClick={() => loadFiles()} aria-label="刷新文件"><RefreshCw size={16} /></button></header>{error && <p className="admin-inline-error" role="alert">{error}</p>}<div className="transfer-inbox-actions"><label className="transfer-inbox-upload"><Upload size={17} />{busy ? '上传中…' : '上传文件'}<input aria-label="选择文件上传" type="file" onChange={upload} disabled={busy} /></label>{busy && <div className="transfer-upload-progress"><progress aria-label="上传进度" max="100" value={uploadProgress} /><span>{uploadProgress}%</span></div>}{shareUrl && <div className="transfer-share-row"><input aria-label="分享链接" readOnly value={shareUrl} /><button type="button" onClick={copyShareLink}>{copied ? <Check size={16} /> : <Copy size={16} />}<span>{copied ? '已复制' : '复制分享链接'}</span></button></div>}</div><div className="transfer-inbox-list">{files.map((item) => <a key={item.id} href={item.download_url}><Download size={16} /><span><strong>{item.name}</strong><small>{formatSize(item.size)} · 中转 #{item.transfer_id} · {formatTransferDate(item.expires_at)} 失效</small></span></a>)}{!files.length && !error && <p className="admin-empty">暂无文件。</p>}</div></section>
}
