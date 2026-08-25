import { useEffect, useRef, useState } from 'react'
import { Camera, Lock, LogOut, Save, Trash2, UserRound } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../contexts/AuthContext.jsx'
import { API_ENDPOINTS } from '../config.js'
import { Avatar } from '../components/ui/Avatar.jsx'
import apiClient from '../utils/request.js'
import './accountPage.css'

function avatarUrl(user) {
  if (!user?.avatar) return undefined
  if (/^(?:https?:|data:|\/)/i.test(user.avatar)) return user.avatar
  return `/${user.avatar}`
}

export default function AccountPage() {
  const { user, isAdmin, logout, refreshUser } = useAuth()
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const [username, setUsername] = useState('')
  const [passwords, setPasswords] = useState({ old_password: '', new_password: '', confirm: '' })
  const [status, setStatus] = useState({ error: '', success: '' })
  const [busy, setBusy] = useState(false)

  useEffect(() => { setUsername(user?.username || '') }, [user?.username])

  if (!user) return null

  async function saveUsername() {
    const value = username.trim()
    if (value.length < 3) return setStatus({ error: '用户名长度至少为 3 个字符。', success: '' })
    setBusy(true); setStatus({ error: '', success: '' })
    try { await apiClient.put('/api/users/me/username', { new_username: value }); await refreshUser(); setStatus({ error: '', success: '用户名已更新。' }) }
    catch (error) { setStatus({ error: error.response?.data?.detail || '用户名修改失败。', success: '' }) }
    finally { setBusy(false) }
  }

  async function changePassword(event) {
    event.preventDefault()
    if (passwords.new_password !== passwords.confirm) return setStatus({ error: '两次输入的新密码不一致。', success: '' })
    setBusy(true); setStatus({ error: '', success: '' })
    try { await apiClient.put(API_ENDPOINTS.UPDATE_PASSWORD, { old_password: passwords.old_password, new_password: passwords.new_password }); setPasswords({ old_password: '', new_password: '', confirm: '' }); setStatus({ error: '', success: '密码已修改。' }) }
    catch (error) { setStatus({ error: error.response?.data?.detail || '密码修改失败。', success: '' }) }
    finally { setBusy(false) }
  }

  async function uploadAvatar(event) {
    const file = event.target.files?.[0]
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(file.type)) return setStatus({ error: '仅支持 JPG、PNG、GIF、WebP。', success: '' })
    if (file.size > 5 * 1024 * 1024) return setStatus({ error: '头像不能超过 5MB。', success: '' })
    setBusy(true); setStatus({ error: '', success: '' })
    try { const body = new FormData(); body.append('file', file); await apiClient.post('/api/users/me/avatar', body); await refreshUser(); setStatus({ error: '', success: '头像已更新。' }) }
    catch (error) { setStatus({ error: error.response?.data?.detail || '头像上传失败。', success: '' }) }
    finally { setBusy(false); event.target.value = '' }
  }

  async function deleteAvatar() {
    setBusy(true); setStatus({ error: '', success: '' })
    try { await apiClient.delete('/api/users/me/avatar'); await refreshUser(); setStatus({ error: '', success: '头像已删除。' }) }
    catch (error) { setStatus({ error: error.response?.data?.detail || '头像删除失败。', success: '' }) }
    finally { setBusy(false) }
  }

  async function signOut() { await logout(); navigate('/login') }

  return (
    <section className="account-page">
      <div className="account-page__grid">
        <section className="account-page__profile">
          <button className="account-page__avatar" type="button" onClick={() => inputRef.current?.click()} aria-label="上传头像"><Avatar name={user.username} src={avatarUrl(user)} size="xl" /><span><Camera size={15} />更换</span></button>
          <input ref={inputRef} hidden type="file" accept="image/jpeg,image/png,image/gif,image/webp" onChange={uploadAvatar} />
          {user.avatar && <button className="account-page__text-button" type="button" onClick={deleteAvatar} disabled={busy}><Trash2 size={14} />删除头像</button>}
          <h2>{user.username}</h2><p>{user.email}</p><span className={`account-page__badge${isAdmin ? ' account-page__badge--admin' : ''}`}>{isAdmin ? 'ADMIN' : 'USER'}</span>
          <button className="account-page__logout" type="button" onClick={signOut}><LogOut size={16} />退出登录</button>
        </section>
        <div className="account-page__sections">
          <section className="account-page__section"><h2><UserRound size={19} />个人信息</h2><div className="account-page__form-grid"><label>用户名<input value={username} onChange={(event) => setUsername(event.target.value)} /></label><label>邮箱<input value={user.email} readOnly /></label></div><button className="account-page__button" type="button" onClick={saveUsername} disabled={busy}><Save size={15} />保存用户名</button></section>
          <section className="account-page__section"><h2><Lock size={19} />修改密码</h2><form className="account-page__password" onSubmit={changePassword}><label>当前密码<input type="password" value={passwords.old_password} onChange={(event) => setPasswords({ ...passwords, old_password: event.target.value })} required /></label><label>新密码<input type="password" value={passwords.new_password} onChange={(event) => setPasswords({ ...passwords, new_password: event.target.value })} minLength="6" required /></label><label>确认新密码<input type="password" value={passwords.confirm} onChange={(event) => setPasswords({ ...passwords, confirm: event.target.value })} minLength="6" required /></label><button className="account-page__button" type="submit" disabled={busy}>更新密码</button></form></section>
          {status.error && <p className="account-page__notice account-page__notice--error" role="alert">{status.error}</p>}{status.success && <p className="account-page__notice" role="status">{status.success}</p>}
        </div>
      </div>
    </section>
  )
}
