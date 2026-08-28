# 网站与独立服务解耦设计

## 背景

当前 Elysium 网站代码包含三类不应继续扩散的外部服务耦合：Books 使用 `KAVITA_PUBLIC_BASE_URL` 拼接阅读链接；管理员后台通过本机路径和 `systemctl` 直接管理 FRP；网站后台提供数据库/配置备份与恢复界面。与此同时，Mineradio、MediaMTX、FRP 文件同步及其认证属于当前仍在使用的业务能力，本次不改变其行为。

## 目标

- 网站不再依赖 Kavita 的 URL 基础配置，也不再展示 Kavita 阅读入口。
- 网站不再读取或修改 `/home/frp`，不再通过后台调用 `frps.service`。
- 网站不再提供面向管理员的备份/恢复功能。
- Mineradio、MediaMTX、FRP 文件同步和 FRP 文件同步认证保持现有接口与运行方式。
- 不删除服务器上的 FRP、Kavita、Mineradio、MediaMTX 或备份数据；本次只移除网站侧的指定功能。

## 非目标与保护边界

- 不重构 Mineradio provider、音乐房间或其 `MUSIC_PROVIDER_BASE_URL` 集成。
- 不重构 MediaMTX、直播、HLS、RTMP 或直播 Nginx 配置。
- 不删除 `backend/routers/file_sync.py`，不修改 `PUBLIC_FRP_FILE_URL`、`PUBLIC_FRP_FILE_USERNAME`、`PUBLIC_FRP_FILE_PASSWORD` 或文件同步前端卡片。
- 不删除发布脚本、回滚脚本、部署前备份、迁移安全机制，以及文件同步上传过程中的原子替换回滚；这些是运维/事务安全，不是网站后台备份功能。
- 不执行生产数据库删表或删除服务器备份目录。
- 不覆盖工作树中已有的未提交修改。

## 设计

### 1. Books 与 Kavita

删除 `KAVITA_PUBLIC_BASE_URL` 读取和 `derive_reader_url` 生成链路。Books 继续提供书籍目录、公开元数据和管理编辑，但不再生成或展示 Kavita 阅读 URL，不再要求管理员填写 Kavita 相对路径。现有数据库中的 `reader_path` 历史列和旧迁移保留，以避免一次代码发布造成数据破坏；活跃模型序列化、Schema、前端和配置不再消费它。

### 2. FRP 网站管理

删除 FRP 管理 router、服务模块、FRP 专用 Schema/ORM 映射、前端管理页、管理路由、菜单入口、API 常量和相关测试/浏览器 smoke 断言。删除网站备份归档中对 `/home/frp/frps.toml` 的采集。

FRP 文件同步是独立保留项：`/api/admin/file-sync` 仍使用现有外部文件 URL 和认证，网站不获得 FRP 本机文件系统或 systemd 权限。

### 3. 网站后台备份

删除网站管理员侧的备份、恢复、备份列表、恢复任务展示和相应 API/菜单/统计。历史备份模型和数据库表不通过迁移删除，避免线上升级阶段发生不可逆数据操作；它们在本次发布后不再被网站业务代码访问。部署脚本继续负责发布包、回滚和迁移前安全备份。

### 4. 兼容策略

- 删除后的旧前端地址不新增替代页面；路由按现有未找到/重定向规则处理，不返回旧管理能力。
- 删除后的旧 API 不再注册，返回现有 404 行为。
- 公开 Books 响应移除仅用于 Kavita 的阅读字段；目录和其余书籍字段保持不变。
- 保留文件同步、Mineradio、MediaMTX 的配置、路由和运行依赖，确保这次拆分不会改变音乐、直播或文件中转行为。

## 文件范围

预期修改或删除：

- 后端：`backend/main.py`、`backend/book_service.py`、`backend/config.py`、`backend/schemas.py`、`backend/models.py`、FRP/备份 router 与服务模块及其活跃测试。
- 前端：Books 页面、管理员 Books 页面、FRP/备份页面、路由、管理员菜单、API 常量及对应测试。
- 配置/文档：环境样例、Docker/架构/数据格式/测试和发布清单中与已删除网站能力直接相关的描述。
- 保留：`backend/routers/file_sync.py`、Mineradio、MediaMTX、直播配置和 FRP 文件同步相关测试。

旧 Alembic migration 文件保持不变；如果需要让新数据库不再创建已删除的历史表，必须另行提出独立迁移设计，不在本次范围内。

## 验证

1. 静态检查确认活跃网站代码不再引用 `KAVITA_PUBLIC_BASE_URL`、FRP 管理 API、`/home/frp`、FRP systemd 控制或网站后台备份入口。
2. 后端测试确认 Books 目录不再生成 Kavita 阅读链接，删除的 API 不再注册，文件同步接口仍保留。
3. 前端测试确认 Books 目录和管理员 Books 编辑可用，FRP/备份入口不可达，Mineradio/MediaMTX/文件同步相关测试未回归。
4. 运行 `git diff --check`、相关后端/前端测试和项目 release gate；所有检查均使用隔离测试数据，不访问生产服务。
5. 检查工作树差异，确保只包含本次文件和原有用户改动，不重写或删除原有未提交文件。
