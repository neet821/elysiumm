import { useCallback, useEffect, useMemo, useState } from 'react'

import { API_ENDPOINTS } from '../../config'
import { useOptionalAuth } from '../../contexts/AuthContext'
import apiClient from '../../utils/request'


const NICKNAME_KEY = 'blue_live_nickname'

const nicknameKey = (liveSessionId) => (
  liveSessionId ? `${NICKNAME_KEY}:${liveSessionId}` : NICKNAME_KEY
)

const readNickname = (liveSessionId) => {
  try {
    return window.localStorage?.getItem(nicknameKey(liveSessionId)) || ''
  } catch {
    return ''
  }
}

const saveNickname = (liveSessionId, value) => {
  try {
    window.localStorage?.setItem(nicknameKey(liveSessionId), value)
  } catch {
    // Private browsing and embedded webviews may deny storage access.
  }
}

const normalizeNickname = (value) => value.trim().slice(0, 40)
const normalizeContent = (value) => value.trim().slice(0, 300)
const formatTime = (value) => (
  value ? new Date(value).toLocaleTimeString('zh-CN', { hour12: false }) : '刚刚'
)


export default function LiveMessageBoard({ liveSessionId = null, readOnly = false }) {
  const { isAuthenticated, user } = useOptionalAuth()
  const [nickname, setNickname] = useState(() => readNickname(liveSessionId))
  const [nicknameLocked, setNicknameLocked] = useState(() => Boolean(readNickname(liveSessionId)))
  const [content, setContent] = useState('')
  const [messages, setMessages] = useState([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const saved = readNickname(liveSessionId)
    setNickname(saved)
    setNicknameLocked(Boolean(saved))
  }, [liveSessionId])

  const reload = useCallback(async () => {
    const response = await apiClient.get(API_ENDPOINTS.LIVE_MESSAGES, { skipAuthRedirect: true })
    setMessages(Array.isArray(response.data) ? response.data : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        await reload()
      } catch (requestError) {
        if (!cancelled && requestError?.response?.status !== 401) {
          setError('留言加载失败，请稍后重试。')
        }
      }
    }
    load()
    const timer = window.setInterval(load, 4000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [reload])

  const trimmedNickname = useMemo(
    () => normalizeNickname(nickname),
    [nickname],
  )
  const trimmedContent = useMemo(
    () => normalizeContent(content),
    [content],
  )

  const submit = async (event) => {
    event.preventDefault()
    const authorNickname = isAuthenticated ? user?.username : trimmedNickname
    if (!authorNickname || !trimmedContent) {
      setError('请先填写昵称和留言内容。')
      return
    }
    setSending(true)
    setError('')
    try {
      await apiClient.post(API_ENDPOINTS.LIVE_MESSAGES, {
        nickname: authorNickname,
        content: trimmedContent,
      }, { skipAuthRedirect: true })
      if (!isAuthenticated) {
        saveNickname(liveSessionId, authorNickname)
        setNickname(authorNickname)
        setNicknameLocked(true)
      }
      setContent('')
      await reload()
    } catch (requestError) {
      setError(
        requestError?.response?.status === 429
          ? '发送太快了，请稍后再试。'
          : '留言发送失败，请稍后重试。',
      )
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="live-message-board" aria-label="直播留言">
      <header>
        <h2>留言区</h2>
      </header>
      {error && <p className="live-message-board__error" role="alert">{error}</p>}
      <ul>
        {messages.map((message) => (
          <li key={message.id}>
            <div>
              <strong>{message.nickname}</strong>
              <time>{formatTime(message.created_at)}</time>
            </div>
            <p>{message.content}</p>
          </li>
        ))}
        {!messages.length && <li className="live-message-board__empty">还没有留言。</li>}
      </ul>
      {!readOnly && (
        <form onSubmit={submit}>
          {!isAuthenticated && !nicknameLocked && (
            <input
              aria-label="昵称"
              maxLength={40}
              placeholder="你的昵称"
              value={nickname}
              onChange={(event) => setNickname(event.target.value)}
            />
          )}
          {!isAuthenticated && nicknameLocked && <input aria-label="昵称" value={nickname} readOnly disabled />}
          <textarea
            aria-label="留言内容"
            maxLength={300}
            placeholder="说点什么…"
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
          <button type="submit" disabled={sending}>
            {sending ? '发送中…' : '发送留言'}
          </button>
        </form>
      )}
    </section>
  )
}
