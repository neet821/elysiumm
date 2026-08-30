import { useEffect, useState } from 'react'
import { Download, Upload } from 'lucide-react'
import { useParams } from 'react-router-dom'

import apiClient from '../utils/request.js'

export default function TransferPage() {
  const { token } = useParams(); const [data, setData] = useState(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  async function load() { try { const response = await apiClient.get(`/api/transfers/${token}`); setData(response.data); setError('') } catch (reason) { setError(reason.response?.status === 404 ? '链接不可用。' : reason.response?.data?.detail || '链接不可用。') } }
  useEffect(() => { load() }, [token])
  const [uploadProgress, setUploadProgress] = useState(0)
  async function upload(event) { const file = event.target.files?.[0]; if (!file) return; setBusy(true); setUploadProgress(0); setError(''); try { await apiClient.put(`/api/transfers/${token}`, file, { timeout: 0, params: { filename: file.name }, headers: { 'Content-Type': 'application/octet-stream' }, onUploadProgress: ({ loaded, total }) => { if (total) setUploadProgress(Math.min(100, Math.round((loaded / total) * 100))) } }); await load() } catch (reason) { setError(reason.response?.data?.detail || '上传失败。') } finally { setBusy(false); setUploadProgress(0); event.target.value = '' } }
  return <section className="transfer-page">{error && <p className="admin-inline-error" role="alert">{error}</p>}{data && <><div className="transfer-page__meta"><span>{formatExpiry(data.expires_at)}</span><span>{formatSize(data.total_bytes)} / {formatSize(data.max_bytes)}</span></div><label className="transfer-page__upload"><Upload size={20} />{busy ? '上传中…' : '选择文件上传'}<input type="file" onChange={upload} disabled={busy} /></label>{busy && <div className="transfer-upload-progress"><progress aria-label="上传进度" max="100" value={uploadProgress} /><span>{uploadProgress}%</span></div>}<div className="transfer-page__files">{data.files.map((item) => <a key={item.id} href={item.download_url}><Download size={16} />{item.name}<small>{formatSize(item.size)} · {item.sha256}</small></a>)}</div></>}</section>
}
const formatSize = (value) => { const bytes = Number(value) || 0; if (bytes < 1024) return `${bytes} B`; const units = ['KB', 'MB', 'GB']; let size = bytes / 1024; let unit = units[0]; for (let i = 1; i < units.length && size >= 1024; i += 1) { size /= 1024; unit = units[i] } return `${size.toFixed(1)} ${unit}` }
const formatExpiry = (value) => value ? `有效期至 ${new Date(value).toLocaleString('zh-CN')}` : ''
