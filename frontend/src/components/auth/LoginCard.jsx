import { useState } from 'react'
import { Eye, EyeOff, LockKeyhole, UserRound } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useAuth } from '../../contexts/AuthContext.jsx'

export default function LoginCard({
  buttonText = '登录',
  heading = '欢迎回来',
  isDark = false,
  onSuccess,
  styles = {},
  subtitle = '登录到 Elysium',
}) {
  const { login } = useAuth()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const result = await login(identifier.trim(), password)
      if (!result?.success) {
        setError(result?.message || '登录失败，请检查账号和密码')
        return
      }
      await onSuccess?.()
    } catch {
      setError('暂时无法登录，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section
      className={`w-full max-w-md rounded-[2rem] border p-6 shadow-2xl shadow-black/10 backdrop-blur-xl sm:p-8 ${styles.bg || 'bg-[var(--surface-card)]'} ${styles.border || 'border-[var(--border-subtle)]'}`}
      aria-labelledby="login-card-title"
    >
      <header className="mb-7 text-center">
        <p className={`mb-2 text-xs font-semibold tracking-[0.2em] ${styles.accentClass || 'text-[var(--accent-blue)]'}`}>Elysium</p>
        <h1 id="login-card-title" className={`text-3xl font-semibold ${styles.text || 'text-[var(--text-primary)]'}`}>{heading}</h1>
        <p className={`mt-2 text-sm ${styles.textMuted || 'text-[var(--text-muted)]'}`}>{subtitle}</p>
      </header>

      {error && (
        <div className="mb-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">
          {error}
        </div>
      )}

      <form className="space-y-5" onSubmit={handleSubmit}>
        <div>
          <label className={`mb-2 block text-sm font-medium ${styles.text || 'text-[var(--text-primary)]'}`} htmlFor="login-identifier">
            用户名或邮箱
          </label>
          <div className="relative">
            <UserRound className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" size={18} aria-hidden="true" />
            <input
              id="login-identifier"
              autoComplete="username"
              className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-card-muted)] py-3 pl-11 pr-4 text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-blue)] focus:ring-2 focus:ring-[var(--accent-blue)]/20"
              onChange={(event) => setIdentifier(event.target.value)}
              placeholder="输入用户名或邮箱"
              required
              value={identifier}
            />
          </div>
        </div>

        <div>
          <label className={`mb-2 block text-sm font-medium ${styles.text || 'text-[var(--text-primary)]'}`} htmlFor="login-password">
            密码
          </label>
          <div className="relative">
            <LockKeyhole className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" size={18} aria-hidden="true" />
            <input
              id="login-password"
              autoComplete="current-password"
              className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-card-muted)] py-3 pl-11 pr-12 text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-blue)] focus:ring-2 focus:ring-[var(--accent-blue)]/20"
              onChange={(event) => setPassword(event.target.value)}
              placeholder="输入密码"
              required
              type={showPassword ? 'text' : 'password'}
              value={password}
            />
            <button
              aria-label={showPassword ? '隐藏密码' : '显示密码'}
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              onClick={() => setShowPassword((visible) => !visible)}
              type="button"
            >
              {showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
            </button>
          </div>
        </div>

        <button
          className={`w-full rounded-xl px-4 py-3 font-semibold text-white transition disabled:cursor-wait disabled:opacity-60 ${isDark ? 'bg-orange-600 hover:bg-orange-500' : 'bg-[#189BCC] hover:bg-[#147aa6]'}`}
          disabled={submitting}
          type="submit"
        >
          {submitting ? '正在登录…' : buttonText}
        </button>
      </form>

      <p className={`mt-6 text-center text-sm ${styles.textMuted || 'text-[var(--text-muted)]'}`}>
        还没有账号？{' '}
        <Link className="font-semibold text-[var(--accent-blue)] hover:underline" to="/register">立即注册</Link>
      </p>
    </section>
  )
}
