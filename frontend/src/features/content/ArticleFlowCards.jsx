import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  BookOpen,
  ChevronDown,
  Clapperboard,
  Disc3,
  Gamepad2,
  X,
} from "lucide-react";

import { MarkdownContent } from "./ContentCatalog.jsx";

const RECORD_TYPES = {
  album: { label: "专辑", Icon: Disc3 },
  movie: { label: "电影", Icon: Clapperboard },
  game: { label: "游戏", Icon: Gamepad2 },
  book: { label: "书籍", Icon: BookOpen },
};
const ESSAY_COLLAPSE_THRESHOLD = 120;
const RECORD_REVIEW_PREVIEW_LENGTH = 72;

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? String(value)
    : new Intl.DateTimeFormat("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(date);
}

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

function coverUrl(item) {
  if (!item.cover) return "";
  if (/^(?:https?:|data:|\/)/i.test(item.cover)) return item.cover;
  return `/media/${encodeURIComponent(item.slug)}/${encodeURIComponent(item.cover)}`;
}

function contentTextLength(value) {
  return String(value || "")
    .replace(/<[^>]*>/g, "")
    .replace(/[`*_#>\-[\]|]/g, "")
    .replace(/\s+/g, "").length;
}

function RecordTypeIcon({ type }) {
  const recordType = RECORD_TYPES[type] || { label: "记录", Icon: BookOpen };
  const Icon = recordType.Icon;
  return (
    <span
      className="record-type-icon"
      aria-label={`${recordType.label}类型`}
      title={recordType.label}
    >
      <Icon aria-hidden="true" size={15} strokeWidth={1.8} />
    </span>
  );
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

function LegacyEssayCard({ item, markdown, html }) {
  const [expanded, setExpanded] = useState(false);
  const bodyId = `essay-body-${item.slug.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const source = markdown || html || item.excerpt || "";
  const collapsible = contentTextLength(source) > ESSAY_COLLAPSE_THRESHOLD;
  return (
    <article
      className={`essay-card essay-card--compact${collapsible ? " essay-card--collapsible" : ""}${expanded ? " is-expanded" : ""}`}
    >
      <h2>{item.title}</h2>
      <MarkdownContent
        markdown={markdown}
        html={html}
        fallback={item.excerpt}
        className="essay-body"
        id={bodyId}
      />
      {collapsible && (
        <button
          className="essay-toggle"
          type="button"
          aria-controls={bodyId}
          aria-expanded={expanded}
          aria-label={expanded ? "收起随笔" : "展开随笔"}
          onClick={() => setExpanded((value) => !value)}
        >
          <span className="essay-toggle-icon" aria-hidden="true">
            ⌄
          </span>
        </button>
      )}
      <time className="card-time">
        {formatDate(item.createdAt || item.date || item.updatedAt)}
      </time>
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

function RecordCard({ item }) {
  const [reviewExpanded, setReviewExpanded] = useState(false);
  const [reviewPopoverStyle, setReviewPopoverStyle] = useState(null);
  const reviewRegionRef = useRef(null);
  const image = item.cover ? (
    <img src={coverUrl(item)} alt={item.title} loading="lazy" />
  ) : (
    <span className="cover-missing">暂无封面</span>
  );
  const review = String(item.review || "").trim();
  const hasReview = Boolean(review);
  const reviewPreview =
    review.length > RECORD_REVIEW_PREVIEW_LENGTH
      ? `${review.slice(0, RECORD_REVIEW_PREVIEW_LENGTH).trimEnd()}…`
      : review || "—";
  const fields = [
    item.author && (
      <div key="author">
        <dt>作者</dt>
        <dd>{item.author}</dd>
      </div>
    ),
    item.year && (
      <div key="year">
        <dt>年份</dt>
        <dd>{item.year}</dd>
      </div>
    ),
    item.country && (
      <div key="country">
        <dt>国家</dt>
        <dd>{item.country}</dd>
      </div>
    ),
    item.language && (
      <div key="language">
        <dt>语言</dt>
        <dd>{item.language}</dd>
      </div>
    ),
  ].filter(Boolean);

  useEffect(() => {
    if (!reviewExpanded) return undefined;
    const closeOnOutsidePointer = (event) => {
      if (!reviewRegionRef.current?.contains(event.target))
        setReviewExpanded(false);
    };
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    return () =>
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
  }, [reviewExpanded]);

  useLayoutEffect(() => {
    if (!reviewExpanded) {
      setReviewPopoverStyle(null);
      return undefined;
    }
    const updateReviewPopoverPosition = () => {
      const reviewRegion = reviewRegionRef.current;
      if (!reviewRegion) return;
      const rect = reviewRegion.getBoundingClientRect();
      const width = Math.min(352, Math.max(0, window.innerWidth - 32));
      const maxHeight = Math.min(256, window.innerHeight * 0.5);
      const left = Math.max(
        16,
        Math.min(rect.left, window.innerWidth - width - 16),
      );
      const top = Math.max(
        16,
        Math.min(rect.bottom + 6, window.innerHeight - maxHeight - 16),
      );
      setReviewPopoverStyle({
        left: `${left}px`,
        top: `${top}px`,
        width: `${width}px`,
      });
    };
    updateReviewPopoverPosition();
    window.addEventListener("resize", updateReviewPopoverPosition);
    window.addEventListener("scroll", updateReviewPopoverPosition, true);
    return () => {
      window.removeEventListener("resize", updateReviewPopoverPosition);
      window.removeEventListener("scroll", updateReviewPopoverPosition, true);
    };
  }, [reviewExpanded]);

  return (
    <article
      className={`record-card record-card--priority${reviewExpanded ? " is-review-expanded" : ""}`}
    >
      <div className="record-cover">{image}</div>
      <div className="record-info">
        <h2>
          <RecordTypeIcon type={item.type} />
          <span>{item.title}</span>
        </h2>
        {fields.length > 0 && <dl className="record-details">{fields}</dl>}
        {item.createdAt && (
          <div className="record-added-time">
            添加时间：{formatDate(item.createdAt)}
          </div>
        )}
        <div
          className={`record-review${reviewExpanded ? " is-expanded" : ""}`}
          ref={reviewRegionRef}
        >
          <div className="record-review-summary">
            <span className="record-review-label">个人评论：</span>
            <span className="record-review-text">{reviewPreview}</span>
            {hasReview && (
              <button
                className="record-review-toggle"
                type="button"
                aria-expanded={reviewExpanded}
                aria-label={reviewExpanded ? "收起完整评论" : "展开完整评论"}
                onClick={() => setReviewExpanded((value) => !value)}
              >
                <ChevronDown size={14} aria-hidden="true" />
              </button>
            )}
          </div>
          {hasReview && reviewExpanded && (
            <div
              className="record-review-popover"
              role="region"
              aria-label="完整评论"
              style={reviewPopoverStyle || undefined}
            >
              <p>{review}</p>
            </div>
          )}
        </div>
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
  const recordsHaveOverflow = records.length > 2;
  const essaysHaveOverflow = essays.length > 2;
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
        <aside
          ref={homeSidebarRef}
          className={`home-sidebar${homeSidebarOpen ? " home-sidebar--drawer-open" : ""}`}
          id="home-sidebar"
          role={homeSidebarOpen ? "dialog" : undefined}
          aria-modal={homeSidebarOpen ? "true" : undefined}
          aria-label={homeSidebarOpen ? "侧栏内容" : undefined}
        >
          {homeSidebarOpen && (
            <button
              className="home-sidebar__close"
              type="button"
              aria-label="收起记录和随笔"
              title="收起记录和随笔"
              onClick={closeHomeSidebar}
            >
              <X size={19} aria-hidden="true" />
            </button>
          )}
          <section
            className={`sidebar-section sidebar-section--records sidebar-section--records-scroll${recordsHaveOverflow ? " sidebar-section--has-overflow" : ""}`}
          >
            <div className="sidebar-scroll-viewport sidebar-scroll-viewport--independent sidebar-scroll-viewport--records">
              {records.length > 0 ? (
                records.map((item) => (
                  <RecordCard key={item.slug} item={item} />
                ))
              ) : (
                <p className="empty">还没有记录。</p>
              )}
            </div>
            {recordsHaveOverflow && (
              <span className="sidebar-scroll-cue" aria-hidden="true" />
            )}
          </section>
          <section
            className={`sidebar-section sidebar-section--essays${essaysHaveOverflow ? " sidebar-section--has-overflow" : ""}`}
          >
            <div className="sidebar-scroll-viewport sidebar-scroll-viewport--independent sidebar-scroll-viewport--essays">
              {essays.length > 0 ? (
                essays.map((item) => (
                  <LegacyEssayCard
                    key={item.slug}
                    item={item}
                    markdown={fullEssayBySlug[item.slug]?.markdown}
                    html={fullEssayBySlug[item.slug]?.html}
                  />
                ))
              ) : (
                <p className="empty">还没有随笔。</p>
              )}
            </div>
            {essaysHaveOverflow && (
              <span className="sidebar-scroll-cue" aria-hidden="true" />
            )}
          </section>
        </aside>
        <PhotoStrip photos={photos} />
      </div>
    </>
  );
}
