# Elysium 核心代码清理与可恢复归档报告

Date: 2026-08-30
Scope: 当前 `main` 的死代码移出、归档索引、Archive API 退役；不部署生产。

## Release candidate status

本次清理候选为 **PASS（代码、迁移与核心测试）/ BLOCKED（既有 JavaScript 预算）**。
清理前先创建并推送了注释标签
`archive/pre-core-cleanup-2026-08-30`，标签指向清理前提交
`3cde728e4ef8dfff34989093ae1922a2e0e86e10`，且没有覆盖已存在的标签。
归档索引位于 [legacy-code-archive.md](docs/reference/legacy-code-archive.md)，每组都记录原路径、退役理由、依赖边界和恢复命令。

没有修改 Aliyun 服务、Nginx、systemd、FRP、静态目录或数据库，也没有执行部署和回滚。用户未跟踪的运维文件保持原内容和状态；只有归档索引作为本次新增跟踪文件。Books API 没有因“无请求”而强行删除：它仍被媒体首页、媒体服务、后台服务和 ORM 测试使用，因此按计划保留。

## Architecture and delivered scope

当前正式入口是 React 前端的文章首页、文章阅读、认证、音乐房、观影房、直播、账户、传输和 `/admin/*` 管理壳；文章 API、直接音乐 provider、认证、内容、文件、同步、媒体和实时协议均由 FastAPI 承载，MediaMTX、FRP 文件同步和发布/回滚链保持明确边界。

本次没有触碰 MediaMTX、FRP 文件同步、同步代理、认证和实时房间、首页书签/媒体供给链、Alembic 历史、生产数据；旧 3D 房间、旧首页/Archive/Collection/Books/Tools 页面、旧独立服务和专属测试被移出，原代码仍可由归档标签精确恢复。

## Phase delivery summary

| Phase | Result | Evidence and scope |
| --- | --- | --- |
| Phase 0 | PASS | 记录 Git 状态、路由、依赖、服务引用、生产 release 标记和未跟踪文件快照。 |
| Phase 1 | PASS | 创建并推送注释归档标签，建立保护边界和可恢复索引。 |
| Phase 2 | PASS | 移出根目录旧 Vite/3D 入口、旧 `src/`、旧浏览器脚本、旧前端页面/组件/测试、旧样式、素材、模板和阶段报告；精简包脚本与依赖。 |
| Phase 3 | PASS | 保留文章服务、当前首页文章流、首页设置、书签与媒体数据供给链。 |
| Phase 4 | PASS | 保留认证、账户、文件传输、FRP 同步和后台当前页面；旧 Collection UI 归档，受保护的 Collection API/数据未删除。 |
| Phase 5 | PASS | 保留当前 Mineradio embed、房间同步和视频播放器适配器；旧独立播放器实现归档。 |
| Phase 6 | PASS | 保留当前音乐 provider、曲库、歌词、签名音频和服务端房间权限。 |
| Phase 7 | PASS | 保留音乐房的服务端权威快照、队列、聊天、历史、重连和多客户端协议。 |
| Phase 8 | PASS | 保留观影房、视频播放列表、上传、字幕、Range 流和同步时钟。 |
| Phase 9 | PASS | 保留直播、管理、传输和既有实时安全边界；旧游戏前端和已退役的游戏平台迁移历史不回流。 |
| Phase 10 | PASS/BLOCKED | 48 小时生产日志满足 Archive 退役条件；Books 组因活跃内部消费者而阻止 ORM/API 退役。 |
| Phase 11 | PASS/BLOCKED | 当前测试、构建、Chrome 验收和归档恢复验证完成；JavaScript 预算仍是真实失败，阈值未提高。 |

## API retirement evidence

在 2026-08-30 00:51（Asia/Shanghai）即时计算的连续 48 小时窗口为
2026-08-28 00:51–2026-08-30 00:51。读取生产 Nginx `access.log`、`.1` 和
`.2.gz` 后，`/api/archive`、`/api/books`、`/api/admin/books*`、
`/api/admin/book-lists*` 均为 **0 请求（任何状态码都计数）**；活动配置范围内也没有 Nginx、systemd 或同步客户端引用。

- Archive 满足“无入口、无内部调用、无活动基础设施引用”，已删除 router 和专属响应类型；`/api/archive` 现在由契约测试确认返回 404/OpenAPI 不再暴露。
- Books 虽然 48 小时无请求，但 `media_service`、媒体路由、`admin_dashboard_service`、首页/媒体测试和 ORM 仍消费 Book/BookList/BookListItem，因此退役被 **BLOCKED**。保留 `/api/books`、后台 Books 服务/模型、`books`、`book_lists`、`book_list_items` 表及全部迁移；没有新增破坏性迁移，也没有把这些表加入 Alembic 忽略集合。
- `/api/homepage` 明确保留：当前首页和 Header 仍读取设置，书签与媒体供给链仍由页面调用。

## Migrations

Alembic 当前线性历史从 `0001_legacy_baseline` 延伸至
`0023_remove_game_platform`。本次验证覆盖 `0009_phase10_books_files_admin`、
`0010_repair_legacy_gaps` 以及后续 `0011`–`0023`；空库升级到 head 成功，
autogenerate 报告无新操作。Books 表和历史迁移保持不变，生产数据不被脚本触碰。
详见 [migrations](docs/migrations.md)。

## Security

认证、授权、JWT、Socket.IO 身份、房间成员权限、上传路径/类型/大小检查、FRP 文件同步鉴权、Public Sync 凭据摘要、备份恢复和生产配置 fail-closed 边界均保留。删除只针对已证明不可达的旧代码；归档索引不包含生产密钥、用户内容或凭据。安全模型见 [security](docs/security.md)。

## Verification evidence

已运行并记录以下证据（均为隔离临时状态，未使用生产数据）：

| Check | Result |
| --- | --- |
| Backend fatal lint/compile | PASS |
| Backend unittest | PASS — 357 tests |
| Alembic empty upgrade/autogenerate | PASS — head `0023_remove_game_platform`，无新操作 |
| Frontend source contracts | PASS — 51 files |
| Frontend Vitest | PASS — 34 files / 238 tests |
| Frontend production build | PASS — initial JS 423,764 B / gzip 134,918 B；total JS 1,141,499 B；CSS 170,190 B；async chunks 30 |
| CSS budget | PASS — 170,190 B 已低于 230,000 B 阈值 |
| JavaScript budget | **BLOCKED** — initial JS 423,764 B > 360,000 B，gzip 134,918 B > 120,000 B；保留真实失败，不提高阈值 |
| Archive 404 contract | PASS — 后端测试与 OpenAPI 检查 |
| Chrome browser acceptance | PASS — `scripts/phase11-accessibility-compat-smoke.mjs`，Chrome 152 via CDP，8 个视口、50 个页面检查，含 FastAPI Articles、原生音乐房、键盘焦点、44px 控件、溢出和第三方请求检查 |
| Patch format | PASS — `git diff --check` |

`scripts/release-gate.sh` 会在资源预算步骤保留上述 JavaScript 失败并停止；其余已修改的浏览器脚本使用当前路由，Phase 11 已单独以真实 Chrome 重跑。完整命令和解释见 [testing](docs/testing.md)。

## Performance and compatibility

清理前基线为 initial JS 425,932 B、gzip 135,425 B、CSS 275,189 B；当前 CSS 降至 170,190 B，JavaScript 仅小幅下降。说明死样式和 `three` 依赖已移除，但当前入口仍有真实 JavaScript 超预算，后续应作为独立性能任务处理。

Phase 11 在 360、390、430、768、1024、1366、1920、2560 宽度运行，覆盖 `/`、`/content`、认证、文章服务、音乐房和退役路由 404；Firefox/WebKit 仅有源代码和构建层面的兼容检查，未声称实时引擎通过。生产网络 Web Vitals、真实设备和生产 Nginx 仍需部署后由运维验收。

## Third-party licenses

Mineradio 的运行边界和归属保留在 `mineradio/LICENSE`、`mineradio/NOTICE.md` 与
`mineradio/BLUE_ALBUM_INTEGRATION.md`；旧前端独立播放器及其专属 notice 一并归档，没有把 GPL 代码复制进当前 React 入口。npm/Python 依赖继续由各自 lockfile、requirements 和上游许可约束。

## Deployment and rollback

本次只提交代码、文档和标签，**没有部署生产**。部署前应先审阅干净提交、执行 [release checklist](docs/release-checklist.md)、运行
`scripts/release-preflight.sh`、制作带 `SHA256SUMS` 的迁移前发布包，并由授权运维执行显式回滚链；不可把本地测试结果当作生产健康证明。生产回滚使用 `scripts/rollback-production.py` 的组件事务入口，不猜测 Alembic downgrade；历史 `scripts/rollback-prod.sh` 仅作为兼容别名。

任一归档组可恢复，例如：

```bash
git restore --source archive/pre-core-cleanup-2026-08-30 -- frontend/src/pages/ArchivePage.jsx
```

完整路径清单、依赖和验证命令见 [legacy-code-archive.md](docs/reference/legacy-code-archive.md)。

## External blockers

| Item | Status | Reason |
| --- | --- | --- |
| JavaScript budget | BLOCKED | 当前入口仍超过既有阈值；本次只删除死代码，未提高阈值。 |
| Books API/ORM retirement | BLOCKED | 48 小时无请求，但活跃媒体首页、后台服务和 ORM 消费者仍在。 |
| Production deployment | BLOCKED | 本请求明确不部署，且本地没有执行生产写权限。 |
| Firefox/WebKit live engine | BLOCKED | 工作区未安装这两个引擎；已完成源/构建检查。 |

## Known limitations

- 本次清理不删除生产表、不修改 Aliyun 配置、不清理用户未跟踪运维文件；生产切换和真实设备验收仍是后续运维工作。
- Books 数据兼容边界仍然存在，只有旧前端入口和专属 API 退役；必须在内部消费者消失并再次完成连续 48 小时日志审计后，才能讨论下一次退役。
- 当前 JavaScript bundle 预算仍未达标；这不是通过提高门槛掩盖的“通过”。
- Chrome 是唯一执行的实时浏览器；Firefox/WebKit、生产 TLS/DNS、外部 provider/Kavita、监控和 off-host 备份需在目标环境验证。
- 归档标签恢复的是清理前源码，不会自动恢复生产静态目录、数据库行或外部服务状态。
