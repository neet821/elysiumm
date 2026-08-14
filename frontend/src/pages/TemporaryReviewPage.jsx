import { Link, Outlet, useLocation } from 'react-router-dom'

export const LEGACY_REVIEW_ITEMS = [
  { id: 'posts', label: '旧文章列表', to: '/account/admin/temporary-review/posts', description: '旧文章页面的当前实现' },
  { id: 'photos', label: '旧照片列表', to: '/account/admin/temporary-review/photos', description: '旧照片页面的当前实现' },
  { id: 'messages', label: '旧留言板', to: '/account/admin/temporary-review/messages', description: '旧留言板页面的当前实现' },
  { id: 'links', label: '旧书签管理', to: '/account/admin/temporary-review/links', description: '旧书签管理页面的当前实现' },
  { id: 'player', label: '本地音乐演示', to: '/account/admin/temporary-review/player', description: '未接入正式音乐服务的本地演示' },
]

export default function TemporaryReviewPage() {
  const location = useLocation()
  const isHub = location.pathname.endsWith('/temporary-review')

  return (
    <section className="route-shell temporary-review-page">
      <header className="route-shell__intro">
        <p className="route-shell__eyebrow">临时管理员功能</p>
        <h1>历史页面检查</h1>
        <p>临时审阅页面，不属于正式站点。检查完成后再决定保留、合并或清理。</p>
      </header>

      {isHub ? (
        <div className="temporary-review-page__list" aria-label="历史页面列表">
          {LEGACY_REVIEW_ITEMS.map((item) => (
            <Link className="temporary-review-page__link" key={item.id} to={item.to}>
              <strong>{item.label}</strong>
              <span>{item.description}</span>
            </Link>
          ))}
        </div>
      ) : (
        <div className="legacy-review-surface dark">
          <p className="legacy-review-surface__notice">临时审阅页面，不属于正式站点。当前页面保留原貌，仅供检查。</p>
          <Outlet />
        </div>
      )}
    </section>
  )
}
