import { Link } from "react-router-dom";

import { MarkdownContent } from "./ContentCatalog.jsx";
import HomeSidebar from "./HomeSidebar.jsx";
import { coverUrl, formatDate } from "./articleFlowUtils.js";

function formatWritingDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? String(value)
    : new Intl.DateTimeFormat("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
      }).format(date);
}

function articleHref(item) {
  return `/article/${encodeURIComponent(item.slug)}`;
}

function LegacyArticleCard({ item }) {
  return (
    <article className="article-card article-card--featured">
      <div className="article-card-info">
        <h2>
          <Link to={articleHref(item)}>{item.title}</Link>
        </h2>
        {item.cover && (
          <div className="article-card-cover article-card-cover--centered article-card-cover--compact">
            <img src={coverUrl(item)} alt={item.title} loading="lazy" />
          </div>
        )}
        <div className="article-card-preview">
          {item.excerpt && (
            <MarkdownContent
              markdown={item.excerpt}
              className="article-card-preview-body"
            />
          )}
          <time className="article-card-preview-time">
            {formatWritingDate(item.createdAt || item.date || item.updatedAt)}
          </time>
        </div>
      </div>
    </article>
  );
}

function LegacyPhotoCard({ item }) {
  const image = item.cover ? (
    <img src={coverUrl(item)} alt={item.title} loading="lazy" />
  ) : null;
  return (
    <article className="photo-card">
      {image ? (
        <div className="photo-frame">{image}</div>
      ) : (
        <div className="photo-frame" />
      )}
      <h3>{item.title}</h3>
      <div className="photo-meta">
        {formatDate(item.date || item.createdAt || item.updatedAt)}
        {item.location ? ` · ${item.location}` : ""}
      </div>
    </article>
  );
}

function PhotoStrip({ photos }) {
  return (
    <section className="photo-strip photo-strip--bottom">
      <div className="photo-strip-grid">
        {photos.length > 0 ? (
          photos.map((item) => <LegacyPhotoCard key={item.slug} item={item} />)
        ) : (
          <p className="photo-strip-empty">还没有照片。</p>
        )}
      </div>
    </section>
  );
}

export function ArticleFlowContent({
  currentPage,
  essays,
  fullEssayBySlug,
  homeSidebarOpen,
  homeSidebarRef,
  paginationItems,
  photos,
  records,
  totalPages,
  visibleArticles,
  closeHomeSidebar,
}) {
  return (
    <>
      {homeSidebarOpen && (
        <button
          className="home-sidebar-backdrop"
          type="button"
          aria-label="关闭记录和随笔"
          onClick={closeHomeSidebar}
        />
      )}
      <div className="home-layout">
        <section className="home-main" aria-label="文章流">
          <h1 className="sr-only">首页</h1>
          <section className="articles-section">
            <div className="writing-list">
              {visibleArticles.length > 0 ? (
                visibleArticles.map((item) => (
                  <LegacyArticleCard key={item.slug} item={item} />
                ))
              ) : (
                <p className="empty">还没有文章。</p>
              )}
            </div>
            {totalPages > 1 && (
              <nav className="home-pagination" aria-label="文章分页">
                {currentPage > 1 ? (
                  <Link
                    className="home-pagination__previous"
                    to={`/?page=${currentPage - 1}`}
                    rel="prev"
                  >
                    上一页
                  </Link>
                ) : (
                  <span
                    className="home-pagination__disabled"
                    aria-disabled="true"
                  >
                    上一页
                  </span>
                )}
                {paginationItems.map((item) =>
                  typeof item === "number" ? (
                    <Link
                      key={item}
                      aria-current={item === currentPage ? "page" : undefined}
                      to={`/?page=${item}`}
                    >
                      {item}
                    </Link>
                  ) : (
                    <span
                      className="home-pagination__ellipsis"
                      key={item}
                      aria-hidden="true"
                    >
                      …
                    </span>
                  ),
                )}
                {currentPage < totalPages ? (
                  <Link
                    className="home-pagination__next"
                    to={`/?page=${currentPage + 1}`}
                    rel="next"
                  >
                    下一页
                  </Link>
                ) : (
                  <span
                    className="home-pagination__disabled"
                    aria-disabled="true"
                  >
                    下一页
                  </span>
                )}
              </nav>
            )}
            {visibleArticles.length > 0 && (
              <div className="articles-section__end-cap" aria-hidden="true" />
            )}
          </section>
        </section>
        <HomeSidebar
          essays={essays}
          fullEssayBySlug={fullEssayBySlug}
          isOpen={homeSidebarOpen}
          onClose={closeHomeSidebar}
          records={records}
          sidebarRef={homeSidebarRef}
        />
        <PhotoStrip photos={photos} />
      </div>
    </>
  );
}
