import { ArrowLeft, Wrench } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function AccessDeniedPage() {
  return (
    <div className="route-shell">
      <section className="mx-auto max-w-2xl rounded-[2rem] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-8 text-center shadow-xl sm:p-12">
        <p className="route-shell__eyebrow">权限提醒 · 403</p>
        <h1 className="text-4xl font-semibold text-[var(--text-primary)]">无权访问此页面</h1>
        <p className="mx-auto mt-4 max-w-lg leading-7 text-[var(--text-secondary)]">
          这里包含管理员专用功能。普通工具仍可在工具箱中正常使用。
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link className="ui-button ui-button--secondary ui-button--md" to="/account">
            <ArrowLeft size={17} aria-hidden="true" /> 返回账户
          </Link>
          <Link className="ui-button ui-button--primary ui-button--md" to="/tools">
            <Wrench size={17} aria-hidden="true" /> 打开工具箱
          </Link>
        </div>
      </section>
    </div>
  )
}
