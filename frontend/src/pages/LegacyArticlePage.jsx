import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { MarkdownContent } from '../features/content/ContentCatalog.jsx'
import '../features/content/articleFlowBase.css'
import '../features/content/legacyArticle.css'

export default function LegacyArticlePage() {
  const location = useLocation()
  const rawSlug = location.pathname.slice('/article/'.length)
  const [article, setArticle] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setArticle(null)
    setError('')
    fetch(`/api/articles/${rawSlug}`)
      .then((response) => {
        if (!response.ok) throw new Error(response.status === 404 ? '找不到这篇文章。' : '服务器没有返回文章。')
        return response.json()
      })
      .then((data) => { if (active) setArticle(data.article || data) })
      .catch((reason) => { if (active) setError(reason.message || '暂时无法打开') })
    return () => { active = false }
  }, [rawSlug])

  if (error) return <section className="state"><h1>暂时无法打开</h1><p>{error}</p><Link to="/">返回首页</Link></section>
  if (!article) return <section className="state" aria-busy="true"><p>正在读取文章……</p></section>

  return (
    <div className="legacy-old-home">
      <article className="reader reader--article">
        <Link className="back-link" to="/" aria-label="返回首页" title="返回首页">←</Link>
        <header className="reader-header"><h1>{article.title}</h1></header>
        <MarkdownContent markdown={article.markdown} html={article.html} className="reader-body" />
      </article>
    </div>
  )
}
