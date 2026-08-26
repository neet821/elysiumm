import { MessageCircle, Users } from 'lucide-react'
import { useState } from 'react'


export default function VideoRoomCommunity({ roomState }) {
  const {
    buffers,
    currentItem,
    isHost,
    kickMember,
    localReady,
    members,
    messages,
    sendMessage,
    transferHost,
    userId,
  } = roomState
  const [chat, setChat] = useState('')
  const [messageTarget, setMessageTarget] = useState('')

  return (
    <div className="grid min-w-0 gap-4 lg:grid-cols-2" aria-label="房间交流区">
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-3 flex items-center gap-2 font-semibold"><Users size={18} />在线成员</h2>
        <ul className="grid gap-2 text-sm">
          {members.map((member) => (
            <li key={member.user_id} className="flex flex-wrap items-center justify-between gap-2">
              <span className={member.is_online === false ? 'text-slate-400' : ''}>{member.username}</span>
              <span className="text-xs text-slate-500">{currentItem?.source_type === 'legacy_local' ? (localReady[member.user_id]?.ready && localReady[member.user_id]?.item_id === currentItem.id ? '本地文件已准备' : '等待选择本地文件') : buffers[member.user_id] ? '缓冲中' : member.is_online === false ? '离线' : '在线'}</span>
              {isHost && String(member.user_id) !== String(userId) && (
                <span className="flex basis-full justify-end gap-2 text-xs">
                  <button type="button" onClick={() => transferHost(member.user_id)} className="text-sky-700 dark:text-sky-300">转让房主</button>
                  <button type="button" onClick={() => kickMember(member.user_id)} className="text-rose-600">移出房间</button>
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="flex min-h-72 flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h2 className="mb-3 flex items-center gap-2 font-semibold"><MessageCircle size={18} />聊天</h2>
        <div className="min-h-40 flex-1 space-y-2 overflow-y-auto" aria-live="polite">
          {messages.map((message) => (
            <p key={message.id} className="rounded-lg bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800">
              <strong>{message.username || message.user || '成员'}：</strong>{message.message || message.text}
            </p>
          ))}
        </div>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (sendMessage(chat, messageTarget ? Number(messageTarget) : null)) setChat('')
          }}
        >
          <div className="min-w-0 flex-1 space-y-2">
            <select aria-label="消息接收人" value={messageTarget} onChange={(event) => setMessageTarget(event.target.value)} className="w-full rounded-lg border border-slate-300 bg-transparent px-2 py-1 text-xs dark:border-slate-600">
              <option value="">所有成员</option>
              {members.filter((member) => String(member.user_id) !== String(userId)).map((member) => (
                <option key={member.user_id} value={member.user_id}>私信 {member.username}</option>
              ))}
            </select>
            <input aria-label="聊天消息" value={chat} onChange={(event) => setChat(event.target.value)} maxLength={500} className="w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm dark:border-slate-600" />
          </div>
          <button type="submit" className="rounded-lg bg-sky-600 px-3 py-2 text-sm text-white">发送</button>
        </form>
      </section>
    </div>
  )
}
