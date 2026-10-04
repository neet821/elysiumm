# Elysium 架构与运行边界

## 一句话边界

Elysium 是一个 React 应用和一个 FastAPI 应用。生产数据经 SQLAlchemy/Alembic 存在 MariaDB/MySQL；隔离测试使用 SQLite。Nginx 提供前端静态文件，并把 `/api/`、`/media/`、`/ws/` 转给后端。Articles、音乐 provider、认证、媒体、文件、管理和实时协议都属于 FastAPI 进程边界。

实时生产拓扑必须保持 **单 Uvicorn worker**：Socket.IO 房间成员、在线状态、限流、缓冲遥测和短生命周期协调状态在进程内。没有共享 manager 时增加 worker 会拆分房间，不是本版本支持的优化。

## 组件职责

- `frontend/` 负责页面、路由、房间展示、媒体适配器和管理员界面；权限和持久化规则仍在后端。
- `backend/` 的 router 只翻译 HTTP/Socket.IO 输入，`*_service.py` 负责领域操作；旧的 `models.music`、`models.rooms`、`book_service.py`、`music_service.py` 等聚合入口是兼容 facade，调用方名称不能随意删除。
- `backend/articles/` 负责 Markdown 清洗、分类和媒体；`/api/articles/**`、`/api/content/**`、`/media/**` 是现役契约。
- `backend/music/` 负责网易云、QQ、Audius 适配器和服务端音源；搜索、平台凭据和授权由 FastAPI 管理，允许的公开媒体 URL 可交给原生播放器。浏览器不接触 provider Cookie。
- `backend/catalog_search_service.py`、`backend/catalog_lyrics_service.py` 是曲库搜索/歌词缓存的实际 owner，`catalog_service.py` 保留旧导入入口。
- `Room Core` 负责媒体身份、位置、播放、服务端时间、速率和版本；音乐再增加队列、投票、收藏和历史，视频再增加播放列表、字幕、上传和 Range 流。
- 旧多人游戏平台已退役；现役“游戏记录”是文章内容分类，不是实时游戏房。相关历史数据库迁移保留。

## 音乐侧车与许可证

音乐 Node 侧车由 `backend/music_node/server.cjs` 包装，不是上游源码副本；只监听 loopback，生产由 `elysiumm-music-api.service` 与后端管理，浏览器不直连。生产侧车使用每个 backend release 私有的 Node runtime，不依赖宿主机全局 Node。当前锁定版本和许可证来源如下：

| 组件 | 固定版本 | 许可证/边界 |
| --- | --- | --- |
| 官方 Node.js Linux x64 runtime | `v22.23.3`；[官方归档](https://nodejs.org/dist/v22.23.3/node-v22.23.3-linux-x64.tar.xz)；归档 SHA-256：`df450af89261115ef9f9e3830c3eeb2cc9213b63c720b1af623cb5dcbe2e02de`；每个 backend `RELEASE.json` 的 `node_runtime` 记录版本、归档和 `node` 二进制摘要 | 仅兼容 Linux x86_64；随归档保留官方 `LICENSE`，按 Node.js 及随包第三方许可声明履行 |
| `@neteasecloudmusicapienhanced/api` | 4.40.1，见 `backend/music_node/package-lock.json` | MIT，以锁文件元数据为准 |
| `@neteasecloudmusicapienhanced/unblockmusic-utils` | 0.4.4，传递依赖 | MIT，以锁文件元数据为准 |
| `@unblockneteasemusic/server` | 0.28.0，传递依赖 | LGPL-3.0-only，需重新审查履行义务 |

生产音乐侧车不再要求宿主机全局 Node 22：部署器在新的 backend release `.node/` 内完成下载、校验和安装，systemd 的 `PATH` 以 `/srv/services/elysium/backend-current/.node/bin` 开头；构建/测试使用的 Node.js 22 仍是 CI/CD 运行线，但不是生产主机全局安装要求。该 app-private runtime 只覆盖 Linux x86_64 裸机 release；frontend-only 发布不安装它，后端回滚跟随 `backend-current`。`ENABLE_GENERAL_UNBLOCK=false`，不允许跨来源静默换歌；只有未来能校验标题、艺人、时长和实际来源时，才可另行设计显式替代播放。升级必须同时审查 lockfile、Node 要求、行为和许可证。

## 上传、同步与直播

- 持久传输文件只允许已登录管理员：Uppy → `/api/admin/tus/` → loopback `tusd` → 完整校验后的原子发布。浏览器不会得到 tusd 地址或服务器路径；公开中转链接只读/下载。
- `@uppy/core`、`@uppy/tus` 当前均为 6.0.0/MIT；tusd 为 v2.10.0/MIT，许可证文件必须保留在 `backend/third_party_licenses/tusd/LICENSE.txt`，二进制由 CI 摘要固定。未完成上传放在 release 外的 shared 暂存目录。
- Public Sync 是管理员创建的设备通道，凭据只显示一次，数据库只留 digest，客户端通过 `X-Sync-Token` 使用；它不是特权文件系统桥。
- MediaMTX 是独立直播服务；`deployment/live/` 的配置、systemd 单元和 Nginx 片段由直播安装/检查脚本消费。普通前后端发布不应擅自重启它。
- Obsidian LiveSync 是独立的 CouchDB/Nginx 同步边界。CouchDB 保持 loopback，私有 `LIVE_PATH`、凭据、`.env` 和加密连接内容不进入 Git；设备验收必须通过实际设备创建无害笔记确认。

tusd 发布压缩包 SHA-256 为 68bd62773a494c621b2b806dfaa03a57aac44044c9757440a17765283fbd7a68，Linux x86_64 二进制 SHA-256 为 b01e54afb2449738cee6114aeca65b1b339b3e56bcbe301ce7b7bcd3db37537c；更新版本时同步复核安装脚本、CI/CD、运行配置和许可证。

## 请求、状态与兼容性

FastAPI/Pydantic 先校验输入，认证在每次受保护请求解析活动用户，service 在变更前执行 owner/管理员检查，事务提交后只序列化公开字段。Socket.IO 握手建立认证身份；成功变更仍由同一 service 提交，重连、刷新和冲突都回到服务端 Snapshot。

客户端的 `client_instance_id`、递增 `operation_seq` 和 `clock_probe` 用于防重放、重连和时钟估计；旧客户端未发送扩展字段时继续走兼容行为。客户端不能通过重复广播本地播放状态成为权威。

公开首页、文章、音乐房、观影房、直播、传输和 `/admin/*` 是现役入口。旧 `/music`、`/tools/sync-room` 只做重定向；旧独立 Mineradio provider HTTP 桥和其回滚配置已退役，但 `MineradioPage`、直接 provider、数据库、Books API/表、Public Sync、FRP 文件同步和历史迁移仍受保护。Kavita 属于独立服务，网站不配置、不控制、不拼接其 reader 链接。

## 清理证据与保留项

| 对象 | 消费者与处理 |
| --- | --- |
| 旧 `Header.jsx` 和专属样式 | 全部页面改用 `HomeNavigation`，检查路由/导入及构建后删除；认证、账户、后台和房间链接保留。 |
| 音乐粒子画布 | 仅用于播放器装饰，无业务消费者；移除画布及样式，保留原生音频、同步、歌词、队列和聊天。 |
| 旧专题/计划/交接文档 | 现役操作合并到本组指南，历史保存在 Git 和仓库外备份；发布脚本不依赖这些 Markdown。路径扫描的文档例外指向新指南。 |
| 书签和 Books | 独立页面虽退役，首页供给、媒体、后台统计、API 与测试仍有消费者，模型、表、数据和迁移全部保留。 |
| 资源求助、历史文件路径及公开重定向 | 外部消费者无法证明为零，本次不删除。 |
| 部署模板 | impact map、CD、配置检查及直播安装器使用不同入口；相同名字/内容不是删除证据，本次保留。 |

历史源代码可从 `archive/pre-core-cleanup-2026-08-30` 或 `archive/pre-slimming-20260913-d7d039b` 查阅；只恢复审查过的单文件，不整体合并旧分支。旧的 48 小时零请求记录只证明当时的流量，不能用作现在删除公开 API 的授权。

## 数据库与发布边界

Alembic 历史是线性 `0001`–`0027`，包括 Books、直播、传输、公开 token、用户播放列表和 `0027_tus_upload_reservations`。普通服务启动不自动迁移；发布事务读取生产 `alembic_version`，只有存在 pending descendants 才先备份再执行 `alembic upgrade heads`。详见 [迁移指南](./migrations.md) 和 [数据格式](./data-formats.md)。

裸机生产使用 `/srv/services/elysium`、Nginx、systemd、MariaDB 和单 worker。前后端分别放在不可变 release 中，只切换 `frontend-current`/`backend-current`；上传、私有文件、同步、传输和备份在 `shared/`；事务在 `releases/deployment-history/`。不可变 baseline 放在 `/srv/backups/elysium/baseline/`，不能依赖旧 release 或兼容链接。

Docker Compose 是本地/自托管路径：`db`、`backend`、`frontend`、私有 NCM 侧车和私有 tusd 侧车使用命名卷；侧车不发布宿主机端口。它不代替裸机生产，也不负责 DNS、TLS、生产凭据、监控、Redis 或分布式队列。详见 [部署指南](./deployment.md)、[安全模型](./security.md)、[CI/CD 运维](./operations/release-cicd.md)。

FlClash/FlClashCore 永远不属于 Elysium 的部署、baseline、回滚或健康检查控制面；任何涉及它的配置只能由其自身运维流程处理。
