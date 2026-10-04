# Elysium CI/CD 运维

本文只描述仓库内 CI/CD 与生产发布脚本的真实边界。quality 负责锁定依赖、影响范围、测试和构建；deployment 只负责经过审批的生产交付。操作员使用仓库脚本和受保护环境，不依赖 GitHub 网页手工发布。

## 触发和审批

质量流程来自 .github/workflows/ci.yml，生产流程来自 .github/workflows/cd.yml。CI 使用 Python 3.12、Node.js 22、锁定的 backend/requirements-dev.txt、frontend/package-lock.json 和 backend/music_node/package-lock.json；发布配置检查必须确认 Node 版本为 22。

生产 deployment 只能由同一仓库 main 的成功 CI 触发，并同时满足：

- PRODUCTION_DEPLOY_ENABLED 恰好为 true；
- protected production environment 的人工审批已通过；
- artifact、commit、影响范围和摘要校验匹配。

变量未设置或为 false 是安全默认值。本流程不修改 FlClash 或 FlClashCore，也不绕过 Nginx/systemd/数据库审批。

## 受保护变量和密钥

| 类型 | 名称 | 用途和边界 |
| --- | --- | --- |
| Secret | PRODUCTION_SSH_PRIVATE_KEY | 专用部署密钥；临时文件 mode 600，不打印。 |
| Secret | PRODUCTION_SSH_KNOWN_HOSTS | 固定 SSH host key；严格校验，不调用 ssh-keyscan。 |
| Variable | PRODUCTION_SSH_HOST | 生产 SSH 地址。 |
| Variable | PRODUCTION_SSH_USER | 具备审计过的 sudo -n 权限的部署账号。 |
| Variable | PRODUCTION_ROOT | 发布根目录，默认 /srv/services/elysium。 |
| Variable | PRODUCTION_BASELINE_ROOT | 基线根目录，默认 /srv/backups/elysium/baseline/。 |
| Variable | PRODUCTION_BASELINE_ID | PRODUCTION_BASELINE_ROOT 下已校验的目录名。 |
| Variable | PRODUCTION_GIT_ORIGIN | install-release-layout.sh 记录的仓库 origin。 |
| Variable | PRODUCTION_DEPLOY_ENABLED | 发布开关；默认关闭，审批后才可设为 true。 |

数据库凭据、应用 secret、生产 env 内容和用户数据不得进入变量、artifact、命令参数、部署事务元数据或日志。production environment 应配置 required reviewers；环境审批不能由仓库变量替代。

## 质量检查和 artifact

影响范围由版本化 release-impact.yml 决定。需要复核某个范围时：

~~~bash
# 根据 base/head 解析后端、前端、基础设施和 live 影响
python3 scripts/resolve-release-impact.py --base <base> --head <head>

# 检查 CI/CD 模板、Node 22、依赖锁文件和活动部署资产
python3 scripts/check-release-config.py
~~~

CI 为 commit 生成 `elysium-release-metadata-<commit>`、按需的 `elysium-frontend-<commit>` 和 `elysium-tusd-<commit>` artifact。包含影响图、非 secret 元数据、前端预算/产物及 tusd 许可证/摘要，不包含 .venv 或生产 env。CD 必须从触发它的 CI run 下载，并复核 commit 与摘要。

## 从修改到发布的命令行流程

以下命令在本地开发仓库执行，不在服务器运行目录 `git pull`。占位值必须先替换；提交、推送和合并只包含已经审查的文件。

~~~bash
# 获取最新主线；工作区有未提交修改时先保存，不强行覆盖
git fetch origin
git switch main
git pull --ff-only
git switch -c codex/<本次任务>

# 修改并预览；数据库保留在本地，不重复运行已存在的预览
bash scripts/local-preview.sh --saved
# 手动查看页面，完成后 Ctrl+C；自动测试由 CI 运行

# 审查实际差异，只暂存本次文件，中文提交
git diff --check
git diff -- <本次文件>
git add -- <本次文件>
git commit -m "本次修改的中文说明"
git push -u origin HEAD

# 创建 PR、等待 CI；禁用分页器，不再出现 (END) 等待 q
GH_PAGER=cat gh pr create --base main --title "中文标题" --body "修改、验证及兼容说明"
GH_PAGER=cat gh pr checks <PR号> --watch
# 若失败，先读对应 run 的失败日志，修复后重新提交，不跳过检查
GH_PAGER=cat gh run view <run-id> --log-failed

# 人工审查最终差异，CI 通过后压缩合并、删除临时分支
GH_PAGER=cat gh pr diff <PR号>
gh pr merge <PR号> --squash --delete-branch
git switch main
git pull --ff-only
git fetch --prune origin

# 合并后 main CI 完成，CD 才进入 production 等待批准
GH_PAGER=cat gh run list --workflow ci.yml --branch main --limit 3
GH_PAGER=cat gh run list --workflow cd.yml --limit 3
~~~

**必须由人操作**：页面体验检查、平台扫码/登录，以及生产部署批准。批准人先确认目标 commit、影响范围、备份和回滚入口，再执行以下命令；代理不代替批准人执行。环境 ID 和 CD run ID 必须来自这次等待中的运行，不能复制历史值。

~~~bash
# 只读列出本次 CD 的待批准环境
gh api repos/neet821/elysiumm/actions/runs/<CD-run-id>/pending_deployments

# 由配置的批准人批准本次 production 环境，不改变审核规则
gh api --method POST repos/neet821/elysiumm/actions/runs/<CD-run-id>/pending_deployments \
  -F 'environment_ids[]=<production环境ID>' \
  -f state=approved -f comment='已核对版本、备份和回滚目标，同意本次发布'

# 批准后等待结果；失败先查看日志，按原发布事务处理
GH_PAGER=cat gh run watch <CD-run-id> --exit-status
GH_PAGER=cat gh run view <CD-run-id> --log-failed
~~~

## 基线和 preflight

自动部署不是创建基线的机制。启用 PRODUCTION_DEPLOY_ENABLED=true 前，必须在外部路径建立自包含、可恢复、无旧 checkout 回指的基线，并核对 runtime、数据库副本、manifest 和 SHA256SUMS：

~~~bash
# 校验指定生产基线；命令本身不修改基线
sudo python3 scripts/verify-baseline.py \
  --baseline /srv/backups/elysium/baseline/<baseline-id>

# 发布前检查 current、shared、数据库、env、Nginx/systemd 和健康端点
sudo bash scripts/release-preflight.sh \
  --root /srv/services/elysium \
  --baseline-root /srv/backups/elysium/baseline \
  --env-file /etc/elysium/backend.env \
  --health-url http://127.0.0.1:8000/api/health
~~~

预发布/隔离环境必须先完成发布和 rollback 演练。首次 data -> shared 切换还要记录 data_pre_copy、livesync_pre_copy、baseline、maintenance_mode、final_sync、legacy_data_retention、release_layout 和 release_transaction；未完成的事务不能伪装成普通发布成功。

## 生产布局和部署事务

生产根目录是 /srv/services/elysium，固定布局包括 repository.git、releases、backend-current、frontend-current、shared 和 releases/deployment-history。backend-current 与 frontend-current 可独立切换；Socket.IO 房间和进程内限流要求后端保持单 worker。shared 上传、文章内容、LiveSync 和恢复边界不能随 release 删除。

标准序列是初始化布局、获取精确 commit、校验基线、安装影响图、执行 preflight，再调用 scripts/deploy-production.py。CI 会同时传递 deployment-id、GitHub run ID、frontend dist、预算/摘要以及每个 changed path；生产端应将事务写入 deployment-history。

不提供删减参数的手工部署示例。完整调用只由 `.github/workflows/cd.yml` 的 `deploy_command` 组装：使用 stage 内脚本和 impact map、main ref、commit/run-id、lock/API 摘要与 Node 22；后端附受信 Python 和 tusd 来源/摘要，前端附 dist/预算，最后逐项附 changed path。人工审批后原样执行该合同，不能在运行目录 `git pull` 或改写 `.venv`。

发布脚本按 impact map 选择 frontend/backend/infra/live 范围；不应把前后端 current 链接混切。deployment 模板、Nginx、systemd、MediaMTX、tusd 和 live 资产必须按实际消费者更新，不能因名称相似而合并或判定未使用。

## Rollback

每个事务保存前一版本 component link、commit、deployment-id 和实际健康证据。组件 rollback 只能使用对应事务和精确确认串：

~~~bash
# 只回滚指定 immutable frontend current link，并创建新的 rollback 事务
sudo python3 scripts/rollback-production.py \
  --root /srv/services/elysium \
  --deployment-id <deployment-id> \
  --component frontend \
  --confirm 'ROLLBACK:<deployment-id>:frontend'
~~~

backend 组件使用 --component backend。rollback 不猜测数据库 downgrade；若涉及迁移、shared 或基础设施，保留失败状态和新安全备份，按批准的基线恢复流程处理。恢复后复核 checksum、健康端点、公开路由、Socket.IO、Nginx/systemd 和实际数据/存储路径。

## 真实验收

部署命令成功、SSH 成功、单个 HTTP 200 或存在事务记录都不是用户验收。必须按影响范围记录登录/admin、首页/文章、音乐 provider/音乐房、视频 Range、tus/admin-only、直播/MediaMTX、Obsidian LiveSync、Public Sync、Nginx/systemd、current/shared 和实际浏览器/设备结果。未执行的设备或生产检查保持 UNRUN/BLOCKED。测试和发布证据见 [../testing.md](../testing.md) 与 [../release-checklist.md](../release-checklist.md)。
