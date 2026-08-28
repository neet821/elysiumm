import { useState } from 'react'
import { Link } from 'react-router-dom'

import LoginCard from '../components/auth/LoginCard.jsx'
import { Dialog } from '../components/ui/index.js'
import { useAuth } from '../contexts/AuthContext.jsx'
import { getServiceGroups } from '../navigation.js'
import { TOOL_ENTRIES } from './toolEntries.js'

function ToolCard({ entry, enabled, onLogin }) {
  const Icon = entry.icon
  const content = (
    <>
      <div className="toolbox-portal__topline">
        <span className="toolbox-portal__icon">
          <Icon size={23} aria-hidden="true" />
        </span>
        <span className="toolbox-portal__number">{entry.number}</span>
      </div>
      <h2>{entry.title}</h2>
      <p>{entry.description}</p>
      <span className="toolbox-portal__action">{enabled ? `进入${entry.title} →` : '登录后可用'}</span>
    </>
  )

  const className = `toolbox-portal toolbox-portal--${entry.id}${enabled ? '' : ' toolbox-portal--disabled'}`
  if (!enabled) return <button type="button" className={className} onClick={onLogin} aria-label={`登录后打开${entry.title}`}>{content}</button>
  return <Link aria-label={`打开${entry.title}`} className={className} to={entry.to}>{content}</Link>
}

export default function ToolsPage({ isDark, styles }) {
  const { isAuthenticated, isAdmin } = useAuth()
  const [loginOpen, setLoginOpen] = useState(false)
  const serviceGroups = getServiceGroups(isAuthenticated, isAdmin)
    .filter((group) => group.label !== '协作房间')

  return (
    <section className="route-shell toolbox-page">
      <header className="route-shell__intro">
        <p className="route-shell__eyebrow">两个核心空间 · 登录后使用</p>
        <h1>工具箱</h1>
        <p>一起观看，一起聆听。</p>
      </header>

      <section className="toolbox-triptych" aria-label="两个核心空间">
        {TOOL_ENTRIES.map((entry) => <ToolCard enabled={isAuthenticated} entry={entry} key={entry.to} onLogin={() => setLoginOpen(true)} />)}
      </section>

      <section className="service-directory" aria-label="全部服务">
        <div className="service-directory__heading">
          <p className="route-shell__eyebrow">按用途浏览</p>
          <h2>全部服务</h2>
        </div>
        {serviceGroups.map((group) => (
          <section className="service-directory__group" key={group.label} aria-labelledby={`service-group-${group.label}`}>
            <h3 id={`service-group-${group.label}`}>{group.label}</h3>
            <div className="service-directory__items">
              {group.items.map((item) => {
                const content = (
                  <span>
                    <strong>{item.label}</strong>
                    <small>{item.available ? item.description : '登录后可用'}</small>
                  </span>
                )
                if (!item.available) {
                  return <button aria-label={`登录后打开${item.label}`} className="service-directory__item" key={item.to} onClick={() => setLoginOpen(true)} type="button">{content}<span aria-hidden="true">→</span></button>
                }
                return <Link className="service-directory__item" key={item.to} to={item.to}>{content}<span aria-hidden="true">→</span></Link>
              })}
            </div>
          </section>
        ))}
      </section>

      <Dialog open={!isAuthenticated && loginOpen} onOpenChange={setLoginOpen} title="登录后打开工具箱">
        <div className="toolbox-login-dialog">
          <LoginCard
            buttonText="登录并打开工具箱"
            heading="欢迎回来"
            isDark={isDark}
            onSuccess={() => setLoginOpen(false)}
            styles={styles}
            subtitle="登录后可进入同步观影和同步听歌"
          />
        </div>
      </Dialog>
    </section>
  )
}
