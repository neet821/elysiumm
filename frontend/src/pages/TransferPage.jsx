import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import { useParams } from 'react-router-dom'

import apiClient from '../utils/request.js'
import { formatTransferDate } from '../utils/transfer.js'

export default function TransferPage() {
  const { token } = useParams(); const [data, setData] = useState(null); const [error, setError] = useState('')
  async function load() { try { const response = await apiClient.get(`/api/transfers/${token}`); setData(response.data); setError('') } catch (reason) { setError(reason.response?.status === 404 ? '链接不可用。' : reason.response?.data?.detail || '链接不可用。') } }
  useEffect(() => { load() }, [token])
  return <section className="transfer-page">{error && <p className="admin-inline-error" role="alert">{error}</p>}{data && <><div className="transfer-page__meta"><span>{formatExpiry(data.expires_at)}</span><span>{formatSize(data.total_bytes)} / {formatSize(data.max_bytes)}</span></div><div className="transfer-page__files">{data.files.map((item) => <a key={item.id} href={item.download_url}><Download size={16} />{item.name}<small>{formatSize(item.size)} · {item.sha256}</small></a>)}</div></>}</section>
}
const formatSize = (value) => { const bytes = Number(value) || 0; if (bytes < 1024) return `${bytes} B`; const units = ['KB', 'MB', 'GB']; let size = bytes / 1024; let unit = units[0]; for (let i = 1; i < units.length && size >= 1024; i += 1) { size /= 1024; unit = units[i] } return `${size.toFixed(1)} ${unit}` }
const formatExpiry = (value) => value ? `有效期至 ${formatTransferDate(value)}` : ''
