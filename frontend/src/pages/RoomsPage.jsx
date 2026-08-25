import { DoorOpen, Film, Gamepad2, Headphones, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import './roomsHub.css'

const rooms = [
  { title: '听歌房', description: '和朋友一起排队、播放并同步聆听。', to: '/rooms/music', icon: Headphones, tone: 'blue', action: '进入听歌房' },
  { title: '观影房', description: '同步播放视频，保留原有房间与字幕能力。', to: '/rooms/watch', icon: Film, tone: 'violet', action: '进入观影房' },
  { title: '桌游房', description: '新的桌游体验正在重做。', to: '/rooms/games', icon: Gamepad2, tone: 'muted', action: '待重做' },
]

export default function RoomsPage() {
  return (
    <section className="rooms-hub">
      <div className="rooms-hub__grid">
        {rooms.map(({ title, description, to, icon: Icon, tone, action }) => (
          <article className={`rooms-hub__card rooms-hub__card--${tone}`} key={title}>
            <div className="rooms-hub__icon"><Icon size={24} aria-hidden="true" /></div>
            <div><p className="rooms-hub__label">{title === '桌游房' ? 'COMING LATER' : 'ONLINE SPACE'}</p><h2>{title}</h2><p>{description}</p></div>
            {title === '桌游房' ? <span className="rooms-hub__disabled"><Users size={15} aria-hidden="true" /> {action}</span> : <Link className="rooms-hub__link" to={to}><DoorOpen size={16} aria-hidden="true" /> {action}</Link>}
          </article>
        ))}
      </div>
    </section>
  )
}
