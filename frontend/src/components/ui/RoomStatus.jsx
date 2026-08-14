const STATUS_LABELS = {
  closed: '已关闭',
  idle: '空闲',
  live: '进行中',
  offline: '离线',
  private: '私密',
  waiting: '等待中',
}

export function RoomStatus({ className, label, status = 'offline', ...props }) {
  return (
    <span
      className={['ui-room-status', className].filter(Boolean).join(' ')}
      data-status={status}
      {...props}
    >
      <span className="ui-room-status__dot" aria-hidden="true" />
      {label || STATUS_LABELS[status] || status}
    </span>
  )
}
