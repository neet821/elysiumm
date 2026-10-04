# Elysium

Elysium 是个人网站的单仓库：React 前端、FastAPI 后端、文章与媒体、音乐房、观影房、直播、公共同步、传输和管理功能共同维护。生产发布仍是独立的、需要人工批准的运维动作；本地检查不会连接生产数据库、Nginx、systemd、FRP 或 FlClash。

## 目录边界

- `frontend/`：React 页面、路由、房间、直播和管理员界面。
- `backend/`：FastAPI 路由、认证、服务、文章、媒体、音乐和实时协议。
- `backend/music_node/`：锁定版本的内部音乐 Node 侧车，只供后端 loopback 调用。
- `public_sync/`：带 `X-Sync-Token` 的公共目录同步客户端，不是特权文件桥。
- `deployment/`：Compose、Nginx、systemd 和 MediaMTX 模板；`deployment/live/` 是直播独立安装资产。
- `scripts/`：本地检查、发布、回滚、备份恢复演练和浏览器验收脚本。

Articles 和面向浏览器的音乐功能不再启动独立的 `3100`/`3000` 服务、iframe 或旧 provider HTTP 桥。旧 `/music`、`/tools/sync-room` 只保留兼容重定向；当前 `MineradioPage` 是网站音乐房，不是独立 Mineradio 服务。

## 本地运行

```bash
# 首次准备 Python 3.12、Node.js 22 和锁定依赖
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
npm --prefix frontend ci

# 一条命令启动前后端、音乐侧车和上传侧车；退出用 Ctrl+C
bash scripts/local-preview.sh --saved
```

默认访问 `http://127.0.0.1:5173`。`--saved` 在项目根目录保存 `elysium-local.sqlite` 并先执行迁移；数据库及本地上传暂存不进入 Git。`ELYSIUM_SAVED_PREVIEW_ROOT` 可指定另一目录；省略 `--saved` 使用退出即清理的临时数据库。端口被占用时先检查现有预览，不重复启动。侧车使用锁定版本；网络或 tusd 不可用必须查看启动提示，不能视为上传验收成功。

前端通过代理访问后端；公开音频可能由允许的平台媒体地址播放，但平台 Cookie 始终只在后端。只改样式通常无需改后端，功能样式位于 `frontend/src/features/`，共享变量位于 `frontend/src/index.css`。

## 快速验证

```bash
# 前端静态检查与单元测试
npm --prefix frontend run check
npm --prefix frontend run test:unit

# 后端、迁移漂移、配置和前端综合检查；只使用隔离临时数据
scripts/check-all.sh
```

发布候选还需要按 [测试与证据](./docs/testing.md) 执行 `scripts/release-gate.sh`，并按 [发布检查表](./docs/release-checklist.md) 记录实际命令、版本、摘要和浏览器结果。没有执行的检查必须保持未确认，不能写成通过。

## 中文指南

- [架构与运行边界](./docs/architecture.md)
- [安全模型](./docs/security.md)
- [数据格式与公开契约](./docs/data-formats.md)
- [迁移与数据路径](./docs/migrations.md)
- [部署、基线与回滚](./docs/deployment.md)
- [测试与发布证据](./docs/testing.md)
- [发布检查表](./docs/release-checklist.md)
- [CI/CD 运维](./docs/operations/release-cicd.md)

## 当前生产边界

裸机生产根目录是 `/srv/services/elysium`，前后端分别通过不可变 release 和 `frontend-current`/`backend-current` 激活，共享数据位于 `shared/`，发布事务位于 `releases/deployment-history/`。MariaDB、Nginx、systemd、MediaMTX、Obsidian LiveSync 和公共同步各有边界；后端实时状态保持单 worker。任何真实发布、迁移、回滚、DNS/HTTPS、设备同步或媒体验收都必须保留可回滚证据，并由 [部署指南](./docs/deployment.md) 和 [CI/CD 运维](./docs/operations/release-cicd.md) 规定的人工门禁控制。
