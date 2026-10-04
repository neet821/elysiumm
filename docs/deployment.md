# Elysium 部署、基线与回滚

## 安全边界

测试只使用临时根目录和数据库，不连接生产环境。生产根目录是 `/srv/services/elysium`；部署工具不读取生产环境文件，除非显式收到 backend systemd 的 EnvironmentFile。FlClash 和 FlClashCore 永远不由 Elysium 重启、检查、baseline 或回滚。

## 裸机布局

| 内容 | 位置 |
| --- | --- |
| 裸 Git 仓库 | `/srv/services/elysium/repository.git` |
| 后端/前端 release | `releases/backend-releases/<id>`、`releases/frontend-releases/<id>` |
| 激活点 | `backend-current`、`frontend-current` |
| 发布事务 | `releases/deployment-history/<deployment-id>.json` |
| 共享上传/私有/同步/传输/备份 | `/srv/services/elysium/shared/` |
| 不可变 baseline | `/srv/backups/elysium/baseline/<baseline-id>/` |
| 生产环境 | `/etc/elysium/backend.env`、`/etc/elysium/mediamtx.*` |

release 是不可变快照并带组件级 `RELEASE.json`；只有 current 链接是激活点。旧 `data -> shared` 兼容链接不再由安装器创建。Articles 镜像、上传和其他 shared 数据是 baseline manifest 中声明的外部依赖，不自动复制进普通 release。

## 初始化与 baseline

基线包含 `BASELINE.json` 和 `SHA256SUMS`，必须先校验可恢复性，不能只确认目录存在。

```bash
# 只创建缺失的 release/shared/裸仓库目录，不切换 current、不停服务
sudo scripts/install-release-layout.sh \
  --root /srv/services/elysium \
  --origin https://github.com/<org>/<repo>.git

# 查看基线工具的全部参数；不能复制半份参数表执行生产快照
python3 scripts/create-baseline.py --help

# 只读校验 manifest、摘要、权限、路径和恢复依赖
sudo python3 scripts/verify-baseline.py \
  --baseline /srv/backups/elysium/baseline/<baseline-id>
```

基线工具沿用历史四组件合同：`--component` 必须恰好给出 backend、frontend、mineradio、articles 的实际 runtime 路径；名称不代表要重新启动旧独立服务。必需项还包括 `--env-file`、相同文件的 `--config env/backend.env=...`、完整 backend `.venv`（外置时用 `--dependency backend/.venv=...`）、uploads 与 Articles 的 `--shared-path`、backend `.venv/bin/python -m uvicorn` 的 `--service-command`，以及配置的 `--restore-target`、服务与路径重写声明。环境文件必须权限 600 或更严，数据库 revision 必须与快照后端一致。逐项核对后才能创建；已有验证基线不因一次前端发布而重建。

真实 baseline 必须包含数据库备份、恢复配置、必要的 systemd/Nginx/MediaMTX 目标和共享依赖。创建后先做隔离端口/数据库恢复演练，再考虑迁移旧目录；baseline 永久保留。

## 现役模板与独立服务

- Compose 模板是本地/自托管路径；NCM 和 tusd 侧车只在私有网络可达，不发布宿主机端口，shared volumes 必须保留。
- `deployment/nginx/`、`deployment/mediamtx/` 和 `deployment/systemd/` 由 release impact map、CD payload 和静态测试消费；不要根据某个文件缺少直接引用就删除。
- `deployment/live/{mediamtx.yml,elysiumm-mediamtx.service,nginx-live.conf}` 由 `scripts/provision-live-streaming.sh` 和 `scripts/check-release-config.py` 消费，负责 RTMP/HLS、鉴权、录制和 Nginx `/live-media/`。它和普通 `deployment/mediamtx/` 不是同一模板。
- 直播录像位于 `/srv/services/elysium/shared/uploads/live-recordings`，不自动删除；公网只需开放 RTMP 1935，其余 MediaMTX 管理/播放端口保持本机访问并经过 Nginx 授权。
- Obsidian LiveSync 的 CouchDB 保持 loopback，只暴露已鉴权的 Nginx 路径；`LIVE_PATH`、凭据、mirror settings 和 `.env` 不进入 release 或日志。设备端必须用现有加密连接创建无害笔记验证。

## CI/CD 与发布事务

### 直播安装与使用

直播安装器固定 MediaMTX `v1.18.2`。`scripts/provision-live-streaming.sh --check` 只校验资产；`sudo scripts/provision-live-streaming.sh --install` 会安装并启动服务，只能在获批的初始配置/维护窗口执行。然后在站点包含 `/etc/nginx/snippets/elysium-live.conf`，补全环境中的 `LIVE_*`，执行 `sudo nginx -t` 成功后才 reload。公网 TCP 1935 同时需安全组/防火墙放行；8000、8888、9996、9997 保持本机访问。

OBS 使用管理员页显示的服务器地址和一次性推流密钥；H.264 视频、AAC 音频、2 秒关键帧，建议从 1080p/30fps、4–6Mbps 开始。当前服务不转码。权限分为公开、指定登录用户、有效期邀请；撤销邀请后后续媒体请求也会失败。网页无画面时依次查后端健康、`systemctl status elysiumm-mediamtx`、本机 HLS 和 Nginx 授权路径。`sudo systemctl restart elysiumm-mediamtx` 会短暂中断直播，需单独授权窗口，不是普通前端发布步骤。

### 内部侧车

音乐服务监听 loopback 8765，健康路径 `/healthz`；unit 指向 `backend-current/backend/music_node/server.cjs`，固定系统 PATH 中需有 Node 22+。发布脚本在新 release 执行 `npm ci --omit=dev`，切换/回滚后端时协调该侧车；测试入口是 `npm test --prefix backend/music_node`，不在当前运行目录安装或覆盖依赖。

本地 tusd 可通过 `TUSD_BINARY=<已验证的二进制>` 指定。不可用时预览其他功能仍启动，但上传返回 503、按钮禁用；必须真实恢复侧车并完成断线续传验收，不能把降级提示当作上传通过。

版本化的 `release-impact.yml` 决定 frontend/backend/infra 和验证 profiles；未知路径或 impact map 变化走 full validation。质量工作流构建锁定依赖、测试、前端产物、摘要和非 secret metadata；生产部署只允许成功的 main push、人工批准的 `production` environment 和 `PRODUCTION_DEPLOY_ENABLED=true`。

远端部署使用精确 commit 和 pinned SSH host keys，先把 commit fetch 到裸仓库，再由 release CLI 物化不可变 release。frontend-only 不读取生产数据库或 backend `.venv`；backend-only 不切换前端；infra 只应用显式映射的 Nginx/systemd/MediaMTX 目标。普通应用发布不重启不受影响的 MediaMTX，也不控制 FlClash。

## 部署、迁移与回滚命令

```bash
# 先检查配置、baseline、数据库连通性、健康端点和 shared 空间
sudo bash scripts/release-preflight.sh \
  --root /srv/services/elysium \
  --baseline-root /srv/backups/elysium/baseline \
  --env-file /etc/elysium/backend.env \
  --web-root /srv/services/elysium/frontend-current/dist \
  --health-url http://127.0.0.1:8000/api/health

# 只回滚指定组件；确认串必须与事务和组件完全一致
sudo python3 scripts/rollback-production.py \
  --root /srv/services/elysium \
  --deployment-id <deployment-id> \
  --component frontend \
  --confirm 'ROLLBACK:<deployment-id>:frontend'
```

backend release 会读取 systemd 使用的数据库环境，比较当前 revision 与目标 heads：无 pending 不备份/不迁移；pending 先备份并校验摘要，再 `alembic upgrade heads`；ahead、divergent、unknown 或环境失败都在切换 `backend-current` 前终止。回滚不猜测 downgrade；迁移后的数据恢复必须使用获批 backup/baseline。

标准发布通过成功 CI 的 CD payload 执行，不使用手工简化的 `deploy-production.py` 调用。完整合约在 `.github/workflows/cd.yml` 的 `deploy_command`：staged 脚本、impact map、精确 commit/run-id、main ref、锁/API 摘要、Node 22、受信 Python、按需 tusd 二进制/摘要、前端 dist/预算及逐项 changed path。缺少其中依赖或元数据应失败，不能临时删参数绕过。

## 生产验收

发布后必须分别记录 backend health、公开首页、Articles/content、媒体、Socket.IO 重连、音乐播放、管理员文件/tus、共享路径、Nginx/systemd 状态、直播授权/录制、Obsidian 设备同步和 deployment transaction。单个 HTTP 200、SSH 成功、配置文件存在或静态构建成功都不是用户可见的生产验收。

详见 [架构](./architecture.md)、[迁移](./migrations.md)、[测试与证据](./testing.md)、[发布检查表](./release-checklist.md) 和 [CI/CD 运维](./operations/release-cicd.md)。本页只描述命令和边界，不表示当前主机已执行这些操作。
