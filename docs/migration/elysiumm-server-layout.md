# Elysium 服务器布局

这份文件描述规范化后的目标布局。安装脚本只创建缺失目录；首次接管
已有服务前必须完成 baseline 创建、恢复演练和人工切换审批。

| 内容 | 位置 |
| --- | --- |
| 裸 Git 仓库 | `/srv/services/elysium/repository.git` |
| 不可变基线 | `/srv/backups/elysium/baseline/<baseline-id>/` |
| 后端 release/current | `/srv/services/elysium/backend-releases/<release>`、`backend-current` |
| 前端 release/current | `/srv/services/elysium/frontend-releases/<release>`、`frontend-current` |
| 发布事务 | `/srv/services/elysium/deployment-history/<deployment-id>.json` |
| 共享上传、私有、同步、传输、备份 | `/srv/services/elysium/shared/{uploads,private-storage,sync-storage,transfers,backups}` |
| 兼容链接 | `/srv/services/elysium/data -> shared`，完成清单前不删除 |
| 生产配置 | `/etc/elysium/backend.env`、`/etc/elysium/mediamtx.*` |
| 后端服务 | `elysiumm-backend.service`，单 worker |
| 直播服务 | `elysiumm-mediamtx.service` |
| Nginx 静态根 | `/srv/services/elysium/frontend-current/dist` |

baseline 不属于服务运行目录。服务根目录只保留 release、current、shared、裸
仓库和发布历史；需要执行发布前检查时，显式传入：

```bash
sudo bash scripts/release-preflight.sh \
  --root /srv/services/elysium \
  --baseline-root /srv/backups/elysium/baseline
```

Articles Markdown/媒体镜像和上传内容属于 `shared` 外部依赖；它们不重复
冻结进普通 release，baseline 只在 `BASELINE.json` 中记录依赖。Mineradio
播放器、provider 和 Articles API 在前端/FastAPI 内，不再启动独立 3000/3100
服务。

## 安装顺序

1. 以当前真实运行状态创建并校验永久 baseline，不切换 current。
2. 运行 `scripts/install-release-layout.sh` 创建目录、裸仓库和 `data -> shared`。
3. 将审查过的 commit fetch 到 `repository.git`，由 release CLI 生成前后端独立快照。
4. 只在目标 Alembic head 存在 pending migration 时备份并升级数据库。
5. 依次验证后端、前端、Nginx、Socket.IO、音乐、Articles、直播和共享数据。

## 回滚原则

组件回滚只切换对应 immutable current，并记录新的 rollback transaction；后端
回滚会重启单 worker。已执行 migration 不自动猜测 downgrade，必须由数据库负责人
按事务中记录的校验和备份或 baseline 恢复。MediaMTX、FlClash/FlClashCore 和
未受影响的服务不随普通应用发布重启。
