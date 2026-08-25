import { Search, Trash2, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'

import { API_ENDPOINTS } from '../config.js'
import { useAuth } from '../contexts/AuthContext.jsx'
import { Avatar } from '../components/ui/Avatar.jsx'
import apiClient from '../utils/request.js'

const avatarUrl = (user) => user?.avatar && (/^(?:https?:|data:|\/)/i.test(user.avatar) ? user.avatar : `/${user.avatar}`)

export default function AdminUsersPage() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')

  async function load() { try { const response = await apiClient.get(API_ENDPOINTS.ADMIN_USERS); setUsers(response.data || []); setError('') } catch { setError('用户列表暂时无法载入。') } }
  useEffect(() => { load() }, [])

  async function remove(user) {
    if (user.role === 'admin' || user.id === currentUser?.id) return
    if (!window.confirm(`确定删除 ${user.username} 吗？`)) return
    try { await apiClient.delete(API_ENDPOINTS.ADMIN_USER_DETAIL(user.id)); setUsers((items) => items.filter((item) => item.id !== user.id)) }
    catch (reason) { setError(reason.response?.data?.detail || '用户删除失败。') }
  }

  const filtered = users.filter((user) => `${user.username} ${user.email}`.toLowerCase().includes(query.toLowerCase()))
  return <section className="admin-table-page"><header className="admin-page-heading"><div><p>管理控制台 / 用户</p><h2>用户</h2></div><span>{users.length} 个账户</span></header><label className="admin-search"><Search size={16} /><input placeholder="搜索用户名或邮箱" value={query} onChange={(event) => setQuery(event.target.value)} /></label>{error && <p className="admin-inline-error" role="alert">{error}</p>}<div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>用户</th><th>邮箱</th><th>注册时间</th><th>详情</th><th>操作</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.id}><td><span className="admin-user-cell"><Avatar className="admin-user-cell__avatar" name={item.username} src={avatarUrl(item)} size="sm" /><strong>{item.username}</strong>{item.role === 'admin' && <small>ADMIN</small>}</span></td><td>{item.email}</td><td>{item.created_at ? new Date(item.created_at).toLocaleDateString('zh-CN') : '—'}</td><td><span className="admin-muted"><UserRound size={14} />账户详情</span></td><td>{item.role === 'admin' || item.id === currentUser?.id ? <span className="admin-muted">受保护</span> : <button className="admin-danger-button" type="button" onClick={() => remove(item)} aria-label={`删除 ${item.username}`}><Trash2 size={15} />删除</button>}</td></tr>)}</tbody></table></div>{!filtered.length && <p className="admin-empty">没有匹配的用户。</p>}</section>
}
