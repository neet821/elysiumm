# Elysium 服务器布局

这份文件是切换前的安装模板，不会自动修改服务器。

| 内容 | 新位置 |
| --- | --- |
| 单仓代码 | `/home/elysiumm/app` |
| 前端静态文件 | `/var/www/elysiumm` |
| 生产配置 | `/etc/elysiumm` |
| 后端服务 | `elysiumm-backend.service` |
| 音乐服务 | `elysiumm-mineradio.service` |
| 直播服务 | `elysiumm-mediamtx.service` |
| 原用户数据、上传、录像、备份 | 保留在原 `/home/blue-album`、`/var/lib/blue-album` 路径 |
| CouchDB | 保留原服务和数据库，不改库名 |

## 安装顺序

1. 先完成最终备份并保存校验值。
2. 将仓库发布到 `/home/elysiumm/app`，配置放到 `/etc/elysiumm`，权限设为 `600`。
3. 先执行只读预检，再安装三个 systemd 服务和 Nginx 模板。
4. 依次验证 `/api/health`、登录、管理员权限、音乐、直播、WebSocket 和同步服务。
5. DNS、证书和 Obsidian 同步验证全部通过后，才停用旧域名。

## 回滚原则

回滚只恢复程序、网页和配置；数据库、上传、录像和备份目录保留原位置。任何数据数量异常减少都中止切换，不删除旧备份。
