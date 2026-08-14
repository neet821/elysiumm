import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { MessageCircle, Send } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { API_ENDPOINTS } from '../../config.js'
import apiClient from '../../utils/request.js'
import { Button, Card } from '../ui/index.js'

const formatDate = (value) => {
  if (!value) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(new Date(value))
}

export default function MessageBoardCard({ messages: initialMessages = [] }) {
  const auth = useAuth() || {}
  const { isAuthenticated = false, user = null } = auth
  const [messages, setMessages] = useState(initialMessages)
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setMessages(initialMessages)
  }, [initialMessages])

  const submitMessage = async (event) => {
    event.preventDefault()
    const normalized = content.trim()
    if (!normalized) return

    setSubmitting(true)
    setError('')
    try {
      const response = await apiClient.post(API_ENDPOINTS.MESSAGE_BOARD, { content: normalized })
      const created = {
        ...response.data,
        user: response.data?.user || user,
      }
      setMessages((current) => [created, ...current].slice(0, 3))
      setContent('')
    } catch (requestError) {
      console.error('首页留言发布失败:', requestError)
      setError('留言暂时无法发布，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card as="section" className="home-message-card" role="region" aria-label="留言板">
      <header className="home-card__header">
        <span className="home-card__eyebrow"><MessageCircle size={14} aria-hidden="true" /> 留言</span>
        <h2>留言板</h2>
      </header>

      <div className="home-message-card__list" aria-live="polite">
        {messages.length ? messages.slice(0, 3).map((message) => (
          <article className="home-message-card__entry" key={message.id}>
            <p>{message.content}</p>
            <footer>
              <span>{message.user?.username || 'Blue Album 访客'}</span>
              <time dateTime={message.created_at}>{formatDate(message.created_at)}</time>
            </footer>
          </article>
        )) : (
          <p className="home-card__empty">暂时没有留言，第一张便签可以由你写下。</p>
        )}
      </div>

      {isAuthenticated ? (
        <form className="home-message-card__form" onSubmit={submitMessage}>
          <label htmlFor="homepage-message">写下留言</label>
          <textarea
            id="homepage-message"
            aria-label="写下留言"
            value={content}
            maxLength={500}
            rows={3}
            placeholder="写下一条公开留言…"
            onChange={(event) => setContent(event.target.value)}
          />
          {error && <p className="ui-field__error" role="alert">{error}</p>}
          <Button
            className="home-message-card__submit"
            type="submit"
            size="sm"
            isLoading={submitting}
            disabled={!content.trim()}
            aria-label="发布留言"
          >
            <Send size={14} aria-hidden="true" />
            发布留言
          </Button>
        </form>
      ) : (
        <Link className="home-card__link" to="/login?next=%2F%23messages" aria-label="登录后留言">
          登录后留言
        </Link>
      )}
    </Card>
  )
}
