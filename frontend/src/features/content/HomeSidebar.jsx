import { X } from "lucide-react";

import EssayCard from "./EssayCard.jsx";
import RecordCard from "./RecordCard.jsx";

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
