import { useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { ArticleFlowContent } from '../features/content/ArticleFlowCards.jsx'
import { organizeHomeContent, paginateHomeArticles } from '../features/content/articleFlowModel.js'
import { useArticleFlowData } from '../features/content/useArticleFlowData.js'
import { useHomeSidebar } from '../contexts/HomeSidebarContext.jsx'
import HomeNavigation from '../components/layout/HomeNavigation.jsx'
import '../features/content/articleFlowBase.css'
import '../features/content/articleFlow.css'

export default function ArticleFlowHome() {
  const [searchParams] = useSearchParams()
  const { isOpen: homeSidebarOpen, close: closeHomeSidebar } = useHomeSidebar()
  const homeSidebarRef = useRef(null)
  const sidebarWasOpenRef = useRef(false)
  const { articles, fullEssays, homeLabel, articleTitleScale, error } = useArticleFlowData()

  useEffect(() => {
    if (!homeSidebarOpen || !homeSidebarRef.current) {
      if (sidebarWasOpenRef.current) {
        const toggle = [...document.querySelectorAll('[aria-label="收起记录和随笔"], [aria-label="展开记录和随笔"]')].find((element) => {
          const style = getComputedStyle(element)
          const rect = element.getBoundingClientRect()
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
        })
        toggle?.focus()
        sidebarWasOpenRef.current = false
      }
      return
    }
    homeSidebarRef.current.scrollTop = 0
    homeSidebarRef.current.querySelector('.home-sidebar__close')?.focus()
    sidebarWasOpenRef.current = true
  }, [homeSidebarOpen])

  const pageParam = searchParams.get('page') || '1'
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [pageParam])

  if (error) return <section className="state"><h1>暂时无法打开</h1><p>{error}</p><Link to="/">返回首页</Link></section>
  if (!articles) return <section className="state" aria-busy="true"><p>正在读取文章……</p></section>

  const { articleItems, essays, records, photos } = organizeHomeContent(articles)
  const { totalPages, currentPage, visibleArticles, paginationItems } =
    paginateHomeArticles(articleItems, searchParams.get('page'))

  return (
    <div className="legacy-old-home legacy-old-home--flat" style={{ '--home-article-title-scale': articleTitleScale }}>
      <HomeNavigation label={homeLabel} activeView="home" className="home-nav--local" />
      <nav className="home-categories" aria-label="内容分类">
        <Link to="/content/article">文章</Link><Link to="/content/record">记录</Link>
        <Link to="/content/essay">随笔</Link><Link to="/content/photo">照片</Link>
      </nav>
      <ArticleFlowContent
        currentPage={currentPage}
        essays={essays}
        fullEssayBySlug={fullEssays}
        homeSidebarOpen={homeSidebarOpen}
        homeSidebarRef={homeSidebarRef}
        paginationItems={paginationItems}
        photos={photos}
        records={records}
        totalPages={totalPages}
        visibleArticles={visibleArticles}
        closeHomeSidebar={closeHomeSidebar}
      />
    </div>
  )
}
