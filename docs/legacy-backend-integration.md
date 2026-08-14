# Elysium 首页与原有功能整合

Elysium 是正式域名 `elysiumm.top` 的首页。首页路径 `/` 使用当前 3D 房间；原有功能不迁移、不重写，继续使用同域的既有地址：

| 功能 | 地址 |
| --- | --- |
| 归档 | `/archive` |
| 直播 | `/live` |
| 音乐 | `/music` |
| 工具箱 | `/tools` |
| 收藏 | `/collection` |
| 书籍 | `/books` |
| 桌游 | `/games` |
| 账户 | `/account` |

部署时必须保留原 Blue Album 后端服务、数据库、WebSocket 和 `/api/` 反代。新首页只替换静态首页资源，不删除原有后端或数据。

建议的发布顺序：

1. 将本项目 `dist/` 发布到新的首页静态目录。
2. 保留原后端服务和数据库不变。
3. Nginx 只把 `/` 的静态首页切换到 Elysium，并继续为上表路径和 `/api/`、`/ws/` 保留原有处理规则。
4. 依次检查 `https://elysiumm.top/`、`/archive`、`/live`、`/music`、`/tools` 和 `/api/health`。

不要把所有请求都用 Elysium 的 `index.html` 回退，否则原有功能页面会被新首页拦截。
