import { useState } from 'react'

import MusicRoomCover from './MusicRoomCover.jsx'

const statusLabels = {
  connecting: '正在连接…',
  syncing: '正在同步…',
  synced: '已同步',
  reconnecting: '连接中断',
  error: '同步失败',
}

export default function MusicRoomQueuePanel({ roomState = {}, onAction = () => {} }) {
  const current = roomState.queue?.find((item) => item.status === 'playing')
  const waiting = roomState.queue?.filter((item) => item.status !== 'playing') || []
  const userId = Number(roomState.userId)
  const isHost = Number(roomState.room?.host_user_id) === userId
  const isAdmin = Boolean(roomState.isAdmin)
  const [message, setMessage] = useState('')

  const submitChat = (event) => {
    event.preventDefault()
    const value = message.trim()
    if (!value) return
    onAction({ action: 'chat', message: value })
    setMessage('')
  }

  const share = async () => {
    const url = `${window.location.origin}/rooms/music/${roomState.room?.id || ''}`
    try {
      await navigator.clipboard?.writeText(url)
      onAction({ action: 'notice', message: '房间链接已复制' })
    } catch {
      onAction({ action: 'notice', message: url })
    }
  }

  return (
    <aside aria-label="听歌房控制台" className="music-room-native__panel">
      <div className="music-room-native__panel-header">
        <div>
          <p className="music-room-native__eyebrow">LISTENING ROOM</p>
          <h2>{roomState.room?.room_name || '听歌房'}</h2>
        </div>
        <button aria-label="退出房间" className="music-room-native__icon-button" onClick={() => onAction({ action: 'leave' })} type="button">×</button>
      </div>
      <div className="music-room-native__room-meta">
        <span data-sync-status={roomState.syncStatus}><i />{statusLabels[roomState.syncStatus] || roomState.syncStatus}</span>
        <button onClick={share} type="button">复制链接</button>
      </div>

      <section aria-labelledby="music-room-queue-title" className="music-room-native__panel-section">
        <div className="music-room-native__section-heading">
          <h2 id="music-room-queue-title">歌单</h2>
          <span>{waiting.length} 首待播</span>
        </div>
        {current && (
          <div className="music-room-native__now-card">
            <MusicRoomCover large track={current} />
            <div><strong>{current.title}</strong><small>{current.artist}</small></div>
            <button disabled={!current || current.skip_voted_by_user_ids?.includes(userId)} onClick={() => onAction({ action: 'vote-skip' })} type="button">
              {current.skip_voted_by_user_ids?.includes(userId) ? '已投票' : `投票切歌 ${current.skip_votes || 0}/${current.skip_required || 1}`}
            </button>
          </div>
        )}
        {waiting.length > 0 ? (
          <ul className="music-room-native__queue">
            {waiting.map((item) => {
              const liked = item.liked_by_user_ids?.some((id) => Number(id) === userId)
              return (
                <li key={item.id}>
                  <MusicRoomCover track={item} />
                  <span><strong>{item.title}</strong><small>{item.artist} · {item.status === 'proposed' ? '待确认' : '等待播放'}</small></span>
                  {item.status === 'proposed' ? (
                    <small className="music-room-native__muted">历史候选，投票已停用</small>
                  ) : (
                    <button onClick={() => onAction({ action: 'like', itemId: item.id })} type="button">
                      {liked ? `取消 ${item.like_count || 0}` : `点赞 ${item.like_count || 0}`}
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
        ) : <p className="music-room-native__muted">搜索一首歌，把它放进房间的下一段时间。</p>}
      </section>

      <section aria-labelledby="music-room-members-title" className="music-room-native__panel-section">
        <div className="music-room-native__section-heading">
          <h2 id="music-room-members-title">在线成员与聊天</h2>
          <span>{roomState.members?.filter((member) => member.is_online).length || 0} 人在线</span>
        </div>
        <ul className="music-room-native__members">
          {(roomState.members || []).map((member) => (
            <li key={member.user_id}><span className={member.is_online ? 'is-online' : ''} />{member.nickname || member.username || '成员'}{Number(member.user_id) === Number(roomState.room?.host_user_id) ? ' · 房主' : ''}</li>
          ))}
        </ul>
        <div aria-live="polite" className="music-room-native__chat">
          {(roomState.messages || []).slice(-12).map((item) => <p key={item.id}><strong>{item.username || '成员'}</strong>{item.message}</p>)}
          {(!roomState.messages || roomState.messages.length === 0) && <span className="music-room-native__muted">还没有消息</span>}
        </div>
        <form className="music-room-native__chat-form" onSubmit={submitChat}>
          <input aria-label="聊天消息" maxLength={500} onChange={(event) => setMessage(event.target.value)} placeholder="说点什么…" value={message} />
          <button type="submit">发送</button>
        </form>
      </section>

      {(isHost || isAdmin) && (
        <details className="music-room-native__admin">
          <summary>{isAdmin && !isHost ? '管理员功能' : '房主管理'}</summary>
          <div>
            <button disabled={!current} onClick={() => onAction({ action: 'force-skip' })} type="button">立即切歌</button>
            <label>切歌门槛
              <select defaultValue={String(roomState.room?.music_skip_vote_percent || 30)} onChange={(event) => onAction({ action: 'settings', music_skip_vote_percent: Number(event.target.value) })}>
                {[30, 50, 70].map((value) => <option key={value} value={value}>{value}%</option>)}
              </select>
            </label>
          </div>
        </details>
      )}

      <details className="music-room-native__history">
        <summary>历史听歌记录 <span>{roomState.history?.length || 0} 条</span></summary>
        <ul>
          {(roomState.history || []).filter((item) => item.event_type === 'track_changed' && item.summary).slice(0, 12).map((item) => (
            <li key={item.id}><button aria-label={`重新加入《${item.summary.title || '未命名歌曲'}》`} onClick={() => onAction({ action: 'readd-history', eventId: item.id })} type="button"><strong>{item.summary.title || '未命名歌曲'}</strong><small>{item.summary.artist || ''}</small></button></li>
          ))}
        </ul>
      </details>
    </aside>
  )
}
