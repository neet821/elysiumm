export const ROUTES = Object.freeze({
  projects: {
    id: 'projects',
    title: 'Projects',
    subtitle: '我做过的小项目',
    items: [
      { title: '3D Room', body: '纯前端 Three.js 线稿数字房间，三个固定机位与环境系统。' },
      { title: '桌面小工具', body: '日常使用的本地小工具集合，内容正在整理中。' },
      { title: '原型与实验', body: '一些交互原型与视觉实验的存档。' },
    ],
  },
  gallery: {
    id: 'gallery',
    title: 'Gallery',
    subtitle: '照片与收藏',
    items: [
      { title: '房间照片墙', body: '把值得记住的瞬间挂到墙上。' },
      { title: '唱片封面', body: '黑胶收藏的封面大图。' },
      { title: '随手拍', body: '日常记录的照片归档。' },
    ],
  },
  reading: {
    id: 'reading',
    title: 'Reading',
    subtitle: '书单与摘录',
    items: [
      { title: '在读', body: '最近翻开的三本书。' },
      { title: '想读', body: '排队中的书目。' },
      { title: '摘录', body: '划线句子与短评。' },
    ],
  },
  movies: {
    id: 'movies',
    title: 'Movies',
    subtitle: '电影与影像',
    items: [
      { title: '最近看过', body: '最近几部电影的短评。' },
      { title: '片单', body: '按心情整理的片单。' },
      { title: '海报墙', body: '喜欢的电影海报。' },
    ],
  },
})

export const ROUTE_BY_ID = Object.freeze({
  monitor: 'projects',
  photoWall: 'gallery',
  books: 'reading',
  moviePoster: 'movies',
})

export const FOCUS_POSES = Object.freeze({
  monitor: {
    position: [-0.15, 2.9, 0.65],
    target: [-0.4, 2.78, -3.18],
    fov: 34,
    duration: 0.8,
  },
  photoWall: {
    position: [3.65, 4.28, -2.43],
    target: [6.58, 4.28, -2.43],
    fov: 38,
    duration: 0.8,
  },
  books: {
    position: [3.35, 4.42, 0.05],
    target: [6.58, 4.42, 0.05],
    fov: 38,
    duration: 0.8,
  },
  moviePoster: {
    position: [3.65, 4.1, 3.07],
    target: [6.58, 4.1, 3.07],
    fov: 38,
    duration: 0.8,
  },
})

export function routeFromHash() {
  const match = globalThis.location?.hash.match(/^#\/([a-z-]+)/)
  return match && ROUTES[match[1]] ? match[1] : null
}
