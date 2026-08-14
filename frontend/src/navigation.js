export const AUTHENTICATED_NAV_ITEMS = [
  { id: 'archive', label: '归档', to: '/archive', description: '浏览文章与照片' },
  { id: 'tools', label: '工具箱', to: '/tools', description: '打开观影、听歌与桌游空间' },
  { id: 'account', label: '账户', to: '/account', description: '管理个人资料与账户设置' },
]

export const ANONYMOUS_NAV_ITEMS = [
  ...AUTHENTICATED_NAV_ITEMS.slice(0, 2),
  { id: 'login', label: '登录', to: '/login', description: '登录 Blue Album' },
]

export function getPrimaryNavigation(isAuthenticated) {
  return isAuthenticated ? AUTHENTICATED_NAV_ITEMS : ANONYMOUS_NAV_ITEMS
}
