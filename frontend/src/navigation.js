export const SERVICE_DIRECTORY = [
  { id: 'archive', label: '归档', to: '/archive', description: '浏览文章与照片', group: '公开服务' },
  { id: 'live', label: '直播', to: '/live', description: '查看当前直播', group: '公开服务' },
  { id: 'music', label: '音乐', to: '/music', description: '创建或加入听歌房', group: '协作房间', auth: true },
  { id: 'sync-room', label: '同步观影', to: '/rooms/watch', description: '创建或加入观影房', group: '协作房间', auth: true },
  { id: 'games', label: '桌游', to: '/games', description: '进入桌游大厅', group: '协作房间', auth: true },
  { id: 'collection', label: '收藏', to: '/collection', description: '管理个人收藏', group: '个人内容', auth: true },
  { id: 'books', label: '书籍', to: '/books', description: '打开个人书架', group: '个人内容', auth: true },
  { id: 'account', label: '账户', to: '/account', description: '管理个人资料与设置', group: '个人内容', auth: true },
]

export const SERVICE_GROUPS = ['公开服务', '协作房间', '个人内容']

export const AUTHENTICATED_NAV_ITEMS = [
  SERVICE_DIRECTORY.find((item) => item.id === 'archive'),
  { id: 'tools', label: '工具箱', to: '/tools', description: '打开所有服务' },
  SERVICE_DIRECTORY.find((item) => item.id === 'account'),
]

export const ANONYMOUS_NAV_ITEMS = [
  SERVICE_DIRECTORY.find((item) => item.id === 'archive'),
  { id: 'tools', label: '工具箱', to: '/tools', description: '打开所有服务' },
  { id: 'login', label: '登录', to: '/login', description: '登录 Elysium' },
]

export function getPrimaryNavigation(isAuthenticated) {
  return isAuthenticated ? AUTHENTICATED_NAV_ITEMS : ANONYMOUS_NAV_ITEMS
}

export function getCurrentServiceLabel(pathname = '/') {
  if (pathname.startsWith('/account/admin')) return '管理中心'
  if (pathname.startsWith('/account')) return '账户'
  if (pathname.startsWith('/tools/sync-room')) return '同步观影'
  if (pathname.startsWith('/tools')) return '工具箱'
  if (pathname.startsWith('/music')) return '音乐'
  if (pathname.startsWith('/games')) return '桌游'
  if (pathname.startsWith('/collection')) return '收藏'
  if (pathname.startsWith('/books')) return '书籍'
  if (pathname.startsWith('/archive') || pathname.startsWith('/posts')) return '归档'
  if (pathname.startsWith('/live')) return '直播'
  if (pathname.startsWith('/login')) return '登录'
  if (pathname.startsWith('/register')) return '注册'
  return ''
}

export function getServiceGroups(isAuthenticated, isAdmin = false) {
  const groups = SERVICE_GROUPS.map((label) => ({
    label,
    items: SERVICE_DIRECTORY
      .filter((item) => item.group === label)
      .map((item) => ({ ...item, available: !item.auth || isAuthenticated })),
  })).filter((group) => group.items.length)

  if (isAdmin) {
    groups.push({
      label: '管理入口',
      items: [{ id: 'admin', label: '管理中心', to: '/account/admin', description: '管理内容、用户与服务', available: true }],
    })
  }
  return groups
}
