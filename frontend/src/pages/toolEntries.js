import { Film, Gamepad2, Music2 } from 'lucide-react'

export const TOOL_ENTRIES = [
  {
    id: 'video',
    number: '01',
    title: '同步观影',
    to: '/tools/sync-room',
    description: '创建或加入视频房，与朋友保持播放进度同步。',
    icon: Film,
  },
  {
    id: 'music',
    number: '02',
    title: '同步听歌',
    to: '/music',
    description: '进入音乐大厅，创建听歌房并打开 Mineradio 播放器。',
    icon: Music2,
  },
  {
    id: 'game',
    number: '03',
    title: '桌游',
    to: '/games',
    description: '进入桌游大厅，创建房间、加入对局或观看回放。',
    icon: Gamepad2,
  },
]
