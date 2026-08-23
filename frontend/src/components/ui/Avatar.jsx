function initialsFor(name) {
  return String(name || '?')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0))
    .join('')
    .toUpperCase() || '?'
}

export function Avatar({ className, name, size = 'md', src, status, ...props }) {
  return (
    <span
      className={['ui-avatar', `ui-avatar--${size}`, className].filter(Boolean).join(' ')}
      {...props}
    >
      {src ? (
        <img className="ui-avatar__image" src={src} alt={name || ''} />
      ) : (
        <span
          className="ui-avatar__fallback"
          role="img"
          aria-label={name || 'Account'}
          data-initials={initialsFor(name)}
        />
      )}
      {status && <span className="ui-avatar__status" data-status={status} aria-hidden="true" />}
    </span>
  )
}
