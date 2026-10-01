import { useState } from "react";

import { MarkdownContent } from "./ContentCatalog.jsx";
import { contentTextLength, formatDate } from "./articleFlowUtils.js";

const ESSAY_COLLAPSE_THRESHOLD = 120;

export default function EssayCard({ item, markdown, html }) {
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
