import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  Clapperboard,
  Disc3,
  Gamepad2,
  X,
} from "lucide-react";

import { MarkdownContent } from "./ContentCatalog.jsx";
import { contentTextLength, coverUrl, formatDate } from "./articleFlowUtils.js";

const RECORD_TYPES = {
  album: { label: "专辑", Icon: Disc3 },
  movie: { label: "电影", Icon: Clapperboard },
  game: { label: "游戏", Icon: Gamepad2 },
  book: { label: "书籍", Icon: BookOpen },
};
const ESSAY_COLLAPSE_THRESHOLD = 120;
const RECORD_REVIEW_PREVIEW_LENGTH = 72;

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

function EssayCard({ item, markdown, html }) {
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

export default function HomeSidebar({
  essays,
  fullEssayBySlug,
  isOpen,
  onClose,
  records,
  sidebarRef,
}) {
  const recordsHaveOverflow = records.length > 2;
  const essaysHaveOverflow = essays.length > 2;

  return (
    <aside
      ref={sidebarRef}
      className={`home-sidebar${isOpen ? " home-sidebar--drawer-open" : ""}`}
      id="home-sidebar"
      role={isOpen ? "dialog" : undefined}
      aria-modal={isOpen ? "true" : undefined}
      aria-label={isOpen ? "侧栏内容" : undefined}
    >
      {isOpen && (
        <button
          className="home-sidebar__close"
          type="button"
          aria-label="收起记录和随笔"
          title="收起记录和随笔"
          onClick={onClose}
        >
          <X size={19} aria-hidden="true" />
        </button>
      )}
      <section
        className={`sidebar-section sidebar-section--records sidebar-section--records-scroll${recordsHaveOverflow ? " sidebar-section--has-overflow" : ""}`}
      >
        <div className="sidebar-scroll-viewport sidebar-scroll-viewport--independent sidebar-scroll-viewport--records">
          {records.length > 0 ? (
            records.map((item) => <RecordCard key={item.slug} item={item} />)
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
              <EssayCard
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
  );
}
