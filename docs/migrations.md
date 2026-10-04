# Elysium 迁移与数据路径

## 唯一 schema 来源

`backend/alembic/versions/` 是生产 schema 的唯一历史；应用 import 不得隐式修改生产库。`backend/run_migrations.py` 会识别空库和已知 legacy baseline，只 stamp 已知基线，再升级到当前 head 并检查 drift；未知或半迁移状态必须 fail closed。

当前是线性 `0001`–`0027`：

- `0001`–`0010`：legacy baseline、安全、首页、Collection、曲库、音乐房、视频房、游戏、Books/Files/Admin 及 legacy repair。
- `0011`–`0017`：视频指纹、房间时钟、直播、音乐房切换和媒体首页。
- `0018`–`0025`：Archive 类型兼容、临时视频、传输、直播访客、房间锁、游戏移除、公开 token 和管理员备注。
- `0026_user_playlists`：用户播放列表；`0027_tus_upload_reservations`：断点上传预约/最终化记录。当前 head 是 `0027_tus_upload_reservations`，不能退回写成 `0025`。

Books ORM 以及 `books`、`book_lists`、`book_list_items` 表仍被首页/媒体/管理员服务和测试消费；退役旧页面不代表可以删表或添加 Alembic ignore。

## 日常与发布迁移

```bash
# 在隔离数据库或明确授权的运维环境中运行当前迁移入口
backend/.venv/bin/python backend/run_migrations.py

# 仅对已验证的非生产临时数据库使用显式 Alembic 命令
cd backend
DATABASE_URL='<validated URL>' .venv/bin/alembic upgrade head
```

普通 backend systemd 启动不调用迁移。发布事务加载 backend systemd 使用的同一环境文件，读取生产 `alembic_version` 和目标 release 的 Alembic heads：

1. 无 pending revision：不创建迁移前数据库备份，也不执行 upgrade。
2. 有 pending descendants：先创建并校验带摘要的 backup，再执行 `alembic upgrade heads`，升级后必须精确到目标 heads。
3. ahead、divergent、unknown、缺少环境或无法确定：在切换 `backend-current` 前终止。

组件回滚不猜测数据库 downgrade。若迁移已执行，数据库恢复必须由数据库负责人批准，使用记录中的 checksum-bearing backup 或经过演练的 baseline restore；代码链接回滚和数据恢复是两个动作。

## 迁移前证据与恢复演练

生产升级前必须有 reviewed commit、成功的 `scripts/release-preflight.sh`、数据库可达性、足够磁盘、时间戳备份/配置/前端包、`SHA256SUMS`、上一版本标识和明确的 abort owner。恢复包必须在受管根目录中，不能依赖旧 release 或兼容链接。

```bash
# 只在操作系统临时目录创建 SQLite 演练库；不连 MariaDB、不读生产 env
backend/.venv/bin/python scripts/rehearse-backup-restore.py --json
```

演练应迁移到当前 head、写入 marker、备份、修改、恢复、检查 marker 和 integrity，再确认临时工作区已删除。非零退出、摘要不一致、剩余工作区、意外 revision、计数差异或凭据泄露都不是通过证据。

开发/兼容性诊断可以在 disposable database 使用 `alembic downgrade -1` 后再升级；绝不能对生产 URL 使用。新增迁移必须在当前 head 后追加，不编辑已经部署的 revision，并覆盖空库、legacy、约束、保留数据和可逆性测试。

## `/data` 到 `shared` 与 baseline

新代码统一使用 `/srv/services/elysium/shared/`；旧 `data -> shared` 只作为迁移期兼容边界，不为新 release 创建。每次发布扫描仓库、systemd、Nginx、维护脚本和进程中的旧路径，保留 deployment ID 和结果；至少两个成功 release 且 baseline restore 不再依赖旧链接后，才可另行审批删除。

```bash
# 开发检查：仅仓库/显式配置扫描，不将本机进程当成生产消费者
python3 scripts/check-legacy-paths.py --root . --no-processes

# 获批的生产只读检查：包含 systemd、Nginx、/proc，不能带 --no-processes
sudo python3 scripts/check-legacy-paths.py \
  --root /srv/services/elysium \
  --git-dir /srv/services/elysium/repository.git --revision <候选commit> \
  --systemd-root /etc/systemd/system --nginx-root /etc/nginx --proc-root /proc
```

扫描非零退出应记录具体消费者，不通过增加 runtime 排除项掩盖。默认排除仅覆盖审计器自身、专属测试和写有历史路径的运维指南。生产扫描结果保留到至少两次成功发布；旧目录、基线和恢复依赖未经复核不得删除。

生产 baseline 永久放在服务根目录之外的 `/srv/backups/elysium/baseline/<baseline-id>/`，包含自洽 runtime、完整 backend `.venv`、数据库备份、`BASELINE.json`、`SHA256SUMS` 和只指向 baseline 内部的恢复配置。baseline 外置、迁移和恢复失败时保留旧目录和失败状态，不擅自删除。

`scripts/relocate-baseline.py` 只接受同文件系统内的真实 baseline 子目录，拒绝 symlink 和已有目标；先校验摘要，再原子 rename、重写内部路径、重新校验，并写入 relocation 事务。失败时尝试原子退回原路径，保存失败/回退状态；它不是复制后随意删除源目录的工具。

```bash
# 仅在获批外置窗口、验证源/目标与恢复计划后执行；不是日常发布步骤
sudo python3 scripts/relocate-baseline.py \
  --source <已核对的旧baseline目录> \
  --destination-root /srv/backups/elysium/baseline \
  --history-root /srv/services/elysium/releases/deployment-history \
  --commit <批准的commit>
```

相关操作见 [部署指南](./deployment.md)、[测试与证据](./testing.md) 和 [发布检查表](./release-checklist.md)。本页不宣称当前生产迁移已经执行或通过。
