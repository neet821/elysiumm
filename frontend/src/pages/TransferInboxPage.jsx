import { Download, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { API_ENDPOINTS } from '../config.js'
import apiClient from '../utils/request.js'

const formatSize = (value) => { const bytes = Number(value) || 0; if (bytes < 1024) return `${bytes} B`; const units = ['KB', 'MB', 'GB']; let size = bytes / 1024; let unit = units[0]; for (let i = 1; i < units.length && size >= 1024; i += 1) { size /= 1024; unit = units[i] } return `${size.toFixed(size >= 10 ? 1 : 2)} ${unit}` }

export default function TransferInboxPage() {
  const [files, setFiles] = useState([]); const [error, setError] = useState('')
  const load = useCallback(async () => { try { const response = await apiClient.get(API_ENDPOINTS.ADMIN_TRANSFER_FILES); setFiles(Array.isArray(response.data) ? response.data : []); setError('') } catch (reason) { setError(reason.response?.data?.detail || '文件暂时无法载入。') } }, [])
  useEffect(() => { load() }, [load])
  return <section className="transfer-inbox-page"><header><h1>全部文件</h1><button type="button" onClick={load} aria-label="刷新文件"><RefreshCw size={16} /></button></header>{error && <p className="admin-inline-error" role="alert">{error}</p>}<div className="transfer-inbox-list">{files.map((item) => <a key={item.id} href={item.download_url}><Download size={16} /><span><strong>{item.name}</strong><small>{formatSize(item.size)} · 中转 #{item.transfer_id}</small></span></a>)}{!files.length && !error && <p className="admin-empty">暂无文件。</p>}</div></section>
}
