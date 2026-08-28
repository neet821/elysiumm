import { Film, Music2 } from 'lucide-react'

export const TOOL_ENTRIES = [
  {
    id: 'video',
    number: '01',
    title: '同步观影',
    to: '/rooms/watch',
    description: '创建或加入视频房，与朋友保持播放进度同步。',
    icon: Film,
  },
  {
    id: 'music',
    number: '02',
    title: '同步听歌',
    to: '/rooms/music',
    description: '进入音乐大厅，创建听歌房并打开 Mineradio 播放器。',
    icon: Music2,
  },
]
