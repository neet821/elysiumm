# Elysium 测试与发布证据

本文说明如何在隔离环境验证现有实现。测试结果必须带有命令、commit、时间、环境和摘要；没有执行的检查写 UNRUN，依赖外部条件的检查写 BLOCKED，不能用静态检查或单个 HTTP 200 宣称用户验收通过。

## 工具链和边界

发布等价线使用 Python 3.12、Node.js 22，以及锁定的 backend/requirements-dev.txt、frontend/package-lock.json 和 backend/music_node/package-lock.json。测试只能使用临时 SQLite、临时 backup/admin roots 和临时端口，不得使用生产数据库、生产凭据、真实 Nginx/systemd/FRP 控制面或生产存储。

本地安装和基础检查：

~~~bash
# 创建隔离后端环境并安装锁定依赖
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt

# 按前端锁文件安装依赖
npm --prefix frontend ci

# 检查本次补丁空白格式
git diff --check

# 运行后端、前端、迁移漂移和构建检查
scripts/check-all.sh

# 单独检查版本化发布模板和 live 资产
python3 scripts/check-release-config.py

# 运行 fail-fast 发布门禁；只使用临时本地状态，不部署或回滚
scripts/release-gate.sh
~~~

失败步骤必须保留原始错误、范围和重现命令；后续步骤未执行时不能记为 PASS。发布门禁不启动生产 Docker、不调用特权主机动作，也不改变 FlClash。

## 聚焦测试

后端使用 unittest；迁移测试必须验证空库/旧库升级、降级兼容和模型与 Alembic head 一致。目前数据库 head 是 0027_tus_upload_reservations：

~~~bash
# 发布脚本和配置的快速回归
backend/.venv/bin/python -m unittest -v backend.tests.test_release_scripts_unittest

# 后端全量 unittest（只使用隔离测试资源）
backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_*_unittest.py' -v

# 临时 SQLite 上执行备份、恢复、完整性和清理演练
backend/.venv/bin/python scripts/rehearse-backup-restore.py --json
~~~

前端检查包括 source-contract、Vitest、lint 和生产构建：

~~~bash
# 运行组件测试
npm --prefix frontend run test:unit

# 运行源代码合同检查
npm --prefix frontend run test:source

# 检查 lint 和生产构建
npm --prefix frontend run lint
npm --prefix frontend run build
~~~

## 浏览器和现役功能验收

浏览器脚本应在临时端口、临时数据库/存储和独立浏览器 profile 中运行，并检查控制台错误、失败请求、非预期第三方流量、凭据/路径泄露和横向溢出。组件测试不能替代导航、布局、媒体、重连或多客户端权限验收。

~~~bash
# 音乐房多客户端、视频房多客户端和 Books/admin 流程
node scripts/phase7-multiclient-smoke.mjs
node scripts/phase8-video-multiclient-smoke.mjs
node scripts/phase10-books-admin-browser-smoke.mjs

# 可访问性、兼容性和直播流程
node scripts/phase11-accessibility-compat-smoke.mjs
node scripts/live-stream-smoke.mjs
~~~

验收范围至少覆盖：登录与 admin-only 路由、文章/首页、音乐 provider 和音乐房 Socket.IO、视频 Range、直播权限与 MediaMTX、管理员 Files/tus 上传、Public Sync、Obsidian 加密 LiveSync 连接以及旧路径兼容重定向。直播验收须验证 OBS/RTMP、访客隐私、录制共享路径和当前 cookie 配置；LiveSync 验收须使用现有设备和无害测试笔记，不把凭据或 .env 写入仓库。

## CI/CD 对应关系

.github/workflows/ci.yml 固定 Python 3.12 和 Node.js 22，使用锁文件并在 main 的质量检查后运行 release gate。.github/workflows/cd.yml 是独立的生产交付流程，只有同仓库 main 的成功 CI、PRODUCTION_DEPLOY_ENABLED=true 和受保护 production 环境人工审批同时满足时才可部署；本地测试不等价于该审批。

## 结果语义

- PASS：指定命令在新建隔离状态下以零退出码完成，并记录了实际证据。
- FAIL：断言、构建、迁移、预算或浏览器检查失败，必须保留失败范围。
- BLOCKED：确实缺少外部服务、凭据、设备、人工审批或其他操作权限。
- UNRUN：尚未执行，不能被汇总为 PASS。

更具体的迁移、部署、发布检查和 CI/CD 顺序见 [migrations.md](migrations.md)、[deployment.md](deployment.md)、[release-checklist.md](release-checklist.md) 和 [operations/release-cicd.md](operations/release-cicd.md)。
