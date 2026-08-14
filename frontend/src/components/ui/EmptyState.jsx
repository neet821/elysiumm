export function EmptyState({ action, className, description, icon, title }) {
  return (
    <section className={['ui-empty-state', className].filter(Boolean).join(' ')}>
      {icon && <span className="ui-empty-state__icon" aria-hidden="true">{icon}</span>}
      <h2 className="ui-empty-state__title">{title}</h2>
      {description && <p className="ui-empty-state__description">{description}</p>}
      {action && <div className="ui-empty-state__action">{action}</div>}
    </section>
  )
}
