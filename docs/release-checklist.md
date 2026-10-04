# Elysium 发布检查表

本表是发布前填写的证据模板，不是预先通过声明。每项都记录命令、commit、时间、环境、摘要和实际结果；未执行写 UNRUN，外部条件未满足写 BLOCKED。静态检查、单个 HTTP 200、SSH 成功或已写入部署事务都不能替代用户可见验收。

## 1. 代码范围和工具链

- [ ] 记录目标 commit、变更摘要、影响范围和回滚目标；保留依赖锁、许可证与历史迁移。文档清理须先合并现役说明、检查消费者并保存历史。
- [ ] git diff --check 无错误；没有混入用户未提交修改、示例数据库、截图、日志或过程资料。
- [ ] CI 使用 Python 3.12、Node.js 22、锁定的依赖和 release-impact；前端构建产物与 commit/hash 对应。
- [ ] 版本化模板、systemd/Nginx/live 资产和许可文件仍可从仓库追溯；不以文件名推断未使用。

## 2. 数据、迁移和恢复

- [ ] 数据库迁移从当前状态可达 0027_tus_upload_reservations，且 head、模型和迁移无漂移；不把 0025 当当前 head。
- [ ] 发布前完成与目标环境匹配的备份、摘要校验和恢复目标记录；生产恢复须有批准窗口。
- [ ] 外置基线位于 /srv/backups/elysium/baseline/<baseline-id>/，是自包含、可校验且不回指旧 checkout 的副本。
- [ ] 临时 SQLite 恢复演练覆盖迁移、marker、备份、修改、恢复、完整性和清理；生产/预发布演练另外记录隔离、健康、认证和 Socket.IO 结果。
- [ ] /data -> shared 迁移仅在扫描进程、systemd、Nginx、同步客户端后推进；保留兼容期间不得删除旧路径。
- [ ] secrets、数据库凭据、LiveSync 配置和用户数据未进入 Git、artifact、命令参数或日志。

## 3. 安全和现役功能

- [ ] 登录、管理员授权、CORS、Socket.IO 房间权限、速率限制、审计字段和 SSRF/path 校验均有实际证据。
- [ ] tus 上传、tusd sidecar、管理员 Files 和写入路径保持 admin-only；验证大小/类型/路径/冲突响应和恢复行为。
- [ ] 首页、文章、认证、音乐 provider/音乐房、视频 Range、直播/MediaMTX、Public Sync、Books 和后台入口按影响范围验收。
- [ ] Obsidian 使用原有加密 LiveSync 连接和无害测试笔记；不把 endpoint、凭据或 .env 写入仓库。
- [ ] 真实浏览器检查控制台错误、失败请求、第三方流量、隐私泄露、移动溢出、重连和多客户端权威状态。

## 4. 兼容性、退役和许可证

- [ ] 旧公开路径、重定向、MineradioPage、当前 direct adapters、历史表和 Alembic 迁移按证据保留；旧 Mineradio bridge 不作为当前入口。
- [ ] Archive 的 2026-08-28 至 2026-08-30 48 小时零请求记录只作为历史证据；没有新的消费者扫描就不扩大退役范围。
- [ ] Books 因内部服务、首页供给链、测试、ORM 和表/迁移仍保留；resource-request 的外部使用未知时继续保留。
- [ ] FRP/Public Sync、MediaMTX、LiveSync、Nginx/systemd、生产路径和公开兼容性均有明确消费者结论；未知消费者一律阻断删除。
- [ ] 音乐依赖保留 @neteasecloudmusicapienhanced/api 4.40.1 MIT、unblockmusic-utils 0.4.4 MIT、@unblockneteasemusic/server 0.28.0 LGPL-3.0-only，并保持 general unblock=false。
- [ ] 上传依赖保留 @uppy/core 6.0.0 MIT、@uppy/tus 6.0.0 MIT、tusd v2.10.0 Linux x86_64 MIT，以及 backend/third_party_licenses/tusd/LICENSE.txt 和发布摘要。

## 5. 发布、审批和回滚

- [ ] 只接受同仓库 main 的成功 CI；production 环境人工审批和 PRODUCTION_DEPLOY_ENABLED=true 均有记录，未使用 GitHub 网页手工绕过流程。
- [ ] 生产布局仍为 /srv/services/elysium，backend-current、frontend-current、shared 和 releases/deployment-history 的切换是独立、原子且可追溯的。
- [ ] 前端变更不重建未变化的后端。当前后端组装器创建独立虚拟环境；尚未实现带完整性校验的安全复用，不能改写或复制运行中的环境来加速发布。
- [ ] 单 worker 约束仍满足 Socket.IO/rooms/limits；backend/frontend 可独立发布，不把前后端 current 链接混切。
- [ ] 发布前后记录健康、路由、Socket.IO、Nginx/systemd、共享目录、迁移和实际设备/浏览器证据；没有真实证据的项目保持 UNRUN 或 BLOCKED。
- [ ] 组件回滚使用对应 deployment-id 和确认串；涉及迁移或 shared 基础设施时不猜测 downgrade，改走批准的基线恢复。
- [ ] 未修改 FlClash、生产代理、权限、真实部署设置或未授权服务；未把本地门禁结果写成生产验收。

## 6. 最小复核命令

~~~bash
# 检查工作树差异，不执行部署
git diff --check

# 检查发布配置和版本化模板
python3 scripts/check-release-config.py

# 隔离环境恢复演练；不触碰生产数据库
backend/.venv/bin/python scripts/rehearse-backup-restore.py --json

# 发布候选的 fail-fast 本地门禁；失败必须保留证据
scripts/release-gate.sh
~~~

发现未记录的消费者、迁移漂移、摘要不一致、权限回归、同步失败、secret 泄露或生产文件变化时立即停止，保存失败状态和证据，先更新 [security.md](security.md)、[migrations.md](migrations.md)、[deployment.md](deployment.md) 或 [operations/release-cicd.md](operations/release-cicd.md) 中的事实，再重新评估。

相关顺序见 [architecture.md](architecture.md)、[data-formats.md](data-formats.md)、[testing.md](testing.md)、[deployment.md](deployment.md) 和 [operations/release-cicd.md](operations/release-cicd.md)。
