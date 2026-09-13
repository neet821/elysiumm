# Elysium 核心代码清理发布检查单

基线：2026-08-30，注释标签 `archive/pre-core-cleanup-2026-08-30`。本次只提交代码、文档和标签，不部署生产。

## Status meanings

- **PASS**：当前命令或证据已完成。
- **BLOCKED**：按计划保留的真实限制、外部环境或尚未满足的退役条件；不伪装成通过。

## Automated release evidence

| Area | Status | Current evidence |
| --- | --- | --- |
| Repository checks | BLOCKED | `scripts/check-all.sh` 的步骤 1–5 已完成（后端 357 tests、前端 source 51 files、Vitest 34 files/238 tests、编译和 lint fatal checks）；步骤 6 因既有 JavaScript 预算超标停止，详见下行。 |
| Migrations | PASS | 临时 SQLite 空库升级到 `0023_remove_game_platform`，autogenerate 无新操作。 |
| Frontend build | PASS | 生产构建完成；initial JS 423,764 B、total JS 1,141,499 B、CSS 170,190 B、async chunks 30。 |
| JavaScript budget | BLOCKED | 既有阈值 360,000 B / gzip 120,000 B 未改变，当前 423,764 B / 134,918 B；后续作为独立性能任务。 |
| CSS budget | PASS | 清理旧样式后 170,190 B，低于 230,000 B 阈值。 |
| Backup/recovery | PASS | 隔离数据库迁移、备份、修改、恢复、完整性和摘要校验完成；临时目录已清理。 |
| Archive API contract | PASS | `/api/archive` 返回 404，专属 schema/router 已移出，后端契约测试通过。 |
| Browser acceptance | PASS | Phase 11 用 Chrome 152 via CDP 检查 8 个视口、50 个页面状态，包含 FastAPI Articles API、认证、首页侧栏、原生音乐房、404、焦点、溢出和第三方请求。 |
| Production deploy | BLOCKED | 本次明确不部署；没有修改 Aliyun、Nginx、systemd、FRP、静态目录或数据库。 |

## Homepage and navigation

| Target | Status | Evidence |
| --- | --- | --- |
| 当前首页文章流和 `/api/homepage` 供给链可达 | PASS | `ContentHomePage`、Header、首页设置测试及 Phase 11 `/` 验收。 |
| 文章、认证、音乐房、观影房、直播、账户、传输和 `/admin/*` 当前入口可达 | PASS | `frontend/src/routes.jsx` 路由合同与 Phase 11/现有页面测试。 |
| 旧 3D 房间、旧首页、旧 Archive/Collection/Books/Tools 页面不回流 | PASS | 旧入口/模块已移出；`/music` 和 `/tools/sync-room` 仅保留兼容重定向，归档路径返回 NotFound。 |
| 键盘跳转、移动侧栏、减少动画和宽度溢出 | PASS | Phase 11 八档视口真实 Chrome 验收。 |

## Collection

| Target | Status | Evidence |
| --- | --- | --- |
| Collection API、备份/恢复、公开字段和权限边界 | PASS | 后端 collection、bookmark backup、授权和序列化测试；数据表与迁移未删除。 |
| 旧 Collection UI、文件夹组件和专属测试归档 | PASS | 路由图无当前消费者，路径记录在 [legacy-code-archive.md](reference/legacy-code-archive.md)。 |
| `/api/homepage` 的书签/媒体供给链保持可用 | PASS | 首页服务和媒体服务仍有内部调用，未纳入退役组。 |

## Player and catalog

| Target | Status | Evidence |
| --- | --- | --- |
| 原生音乐房、房间同步和视频播放器可达 | PASS | `MusicRoomPlayer`、`playerTrack`、`roomPlayerIntegration`、视频房间测试和 Phase 7/11 原生播放器验收。 |
| 旧独立播放器和专属样式/测试移出 | PASS | 当前入口图无消费者；恢复命令见归档索引。 |
| Mineradio 许可和上游边界保留 | PASS | 由归档标签 `archive/pre-slimming-20260913-d7d039b` 中的许可和上游文件继续跟踪；独立服务已退役。 |
| 曲库 provider、签名音频、歌词和失败降级 | PASS | 当前音乐服务/路由/适配器测试。 |

## Music rooms

| Target | Status | Evidence |
| --- | --- | --- |
| JWT 身份、成员/主持权限和服务端快照 | PASS | realtime、music-room service/protocol 测试。 |
| 队列、投票、聊天、历史、重连和漂移校正 | PASS | Phase 7 当前 `/rooms/music/:roomId` 脚本及多客户端测试。 |
| 原生音乐房在隔离浏览器中运行 | PASS | Phase 7/11 Chrome 视口验收；无 iframe、无 3000 端口依赖，本地依赖由前端锁文件安装到 ignored `node_modules`。 |

## Video rooms

| Target | Status | Evidence |
| --- | --- | --- |
| 当前观影房入口、播放列表、上传、字幕和 Range 流 | PASS | Phase 8 当前 `/rooms/watch/:id` 脚本及后端视频测试。 |
| 权威播放状态、重连和权限边界 | PASS | Room Core、video route 和多客户端测试。 |
| 旧 `/tools/sync-room` 页面不再作为实现入口 | PASS | 路由只做兼容重定向，旧页面代码已归档。 |

## Games

| Target | Status | Evidence |
| --- | --- | --- |
| 当前网站不提供旧游戏前端入口 | PASS | 旧页面、导航和专属测试已移出；当前路由无 games 页面。 |
| 游戏数据/迁移历史不被清理破坏 | PASS | Alembic `0023_remove_game_platform` 已验证，历史迁移保持不可变。 |
| 未来恢复旧实现 | PASS | 使用归档标签按路径恢复，不从生产数据库删除数据。 |

## Books, Files and administration

| Target | Status | Evidence |
| --- | --- | --- |
| `/api/archive` 退役并明确返回 404 | PASS | 连续 48 小时无请求、无入口/内部/基础设施消费者；router/schema 删除和 404 合同测试完成。 |
| Books API、服务、ORM 和表退役 | BLOCKED | 同一窗口为 0 请求，但媒体首页、`media_service`、后台服务、测试和 ORM 仍消费 Book/BookList/BookListItem；保留 `/api/books`、后台接口、三张表及全部迁移。 |
| 当前 Files、用户、首页设置、音乐 provider、服务状态后台可达 | PASS | 当前 admin shell/route 测试和 Phase 10 Files/admin 脚本。 |
| FRP 文件同步、Public Sync、传输和备份边界保留 | PASS | 认证、路径安全、摘要凭据、上传/恢复测试；未修改生产同步代理。 |

## Release readiness

| Target | Status | Evidence |
| --- | --- | --- |
| 归档标签可列出并恢复每个移出路径 | PASS | `git tag --list 'archive/pre-core-cleanup-2026-08-30'` 与索引中的 `git restore --source ... -- <paths>`。 |
| 未跟踪运维文件未被写入或暂存 | PASS | 清理前后状态和摘要快照一致；只新增 `docs/reference/legacy-code-archive.md`。 |
| CI/本地门禁复用同一 release gate | PASS | `.github/workflows/quality.yml`、`scripts/release-gate.sh` 和 `docs/testing.md`。 |
| JavaScript 预算与性能后续项 | BLOCKED | 真实预算失败已保留；不得通过提高阈值关闭门禁。 |
| 生产部署、Nginx/systemd/FRP/数据库验收 | BLOCKED | 本次范围不含生产写操作，需后续授权窗口、迁移前备份和真实设备验收。 |

## Required commands

```bash
scripts/check-all.sh
scripts/release-gate.sh
node scripts/phase11-accessibility-compat-smoke.mjs
git diff --check
```

`scripts/release-gate.sh` 在 JavaScript 预算步骤保留真实非零结果并停止；Phase 7、8、10、11 和直播脚本均已改为当前路由，需在预算任务单独处理后作为完整门禁运行。

## 48-hour retirement record

窗口：2026-08-28 00:51–2026-08-30 00:51（Asia/Shanghai）；来源：生产
Nginx `access.log`、`.1`、`.2.gz`。候选 `/api/archive`、`/api/books`、
`/api/admin/books*`、`/api/admin/book-lists*` 均为 0 请求，且活动配置没有
Nginx/systemd/同步客户端引用。零请求只足以退役 Archive；Books 的内部依赖阻止了退役。

## Abort conditions

若发现未记录的路由/服务消费者、任意状态码请求、迁移漂移、备份摘要不一致、授权回归或生产文件变化，应停止清理并用归档标签恢复对应路径。不得删除 `books`、`book_lists`、`book_list_items` 表，不得修改 FRP 认证、Mineradio、MediaMTX、首页供给链或生产数据。

完整架构、迁移和部署说明见 [architecture](architecture.md)、[migrations](migrations.md)、[testing](testing.md) 和 [deployment](deployment.md)。
