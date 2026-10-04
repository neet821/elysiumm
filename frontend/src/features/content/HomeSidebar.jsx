import { X } from "lucide-react";
import { Link } from "react-router-dom";

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
      <section className="sidebar-section sidebar-section--records">
        <div className="section-heading"><h2>最近记录</h2><Link to="/content/record" aria-label="查看全部记录">查看全部</Link></div>
        <div className="sidebar-previews">
          {records.length > 0 ? (
            records.slice(0, 3).map((item) => <RecordCard key={item.slug} item={item} />)
          ) : (
            <p className="empty">还没有记录。</p>
          )}
        </div>
      </section>
      <section className="sidebar-section sidebar-section--essays">
        <div className="section-heading"><h2>随笔</h2><Link to="/content/essay" aria-label="查看全部随笔">查看全部</Link></div>
        <div className="sidebar-previews">
          {essays.length > 0 ? (
            essays.slice(0, 2).map((item) => (
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
      </section>
    </aside>
  );
}
