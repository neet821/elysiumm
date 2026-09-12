# Elysium

Elysium 是个人网站的唯一单仓。React 前端提供文章首页、账户、房间、直播、传输和管理功能；FastAPI 后端同时承载文章 API、音乐 provider、认证、媒体和实时协议。

## 项目组成

- `frontend/`：React 功能站点与房间/直播界面
- `backend/`：FastAPI 接口、登录、内容、文件、管理和实时功能
- `frontend/src/features/music/`：原生音乐房 UI、歌词、封面、粒子和播放适配器
- `backend/music/`：网易云、QQ、Audius provider
- `backend/articles/`：文章 Markdown、清洗、分类和媒体 API
- `deployment/`：Docker、systemd、MediaMTX 和 Nginx 发布模板
- `scripts/`：检查、发布、备份、回滚和浏览器验收脚本
- `docs/`：架构、迁移、部署和发布门禁说明

## 本地运行

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

另开终端准备后端环境并运行：

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
DATABASE_URL=sqlite:///./elysium-local.sqlite SECRET_KEY=local-only-secret \
  backend/.venv/bin/python -m uvicorn main:app --app-dir backend --port 8000 --workers 1
```

默认访问 `http://localhost:5173`。前端代理会把 `/api`、`/media`、上传、音乐、直播和 WebSocket 请求转发到唯一的 FastAPI 服务；Articles 不再有 `3100` 独立服务，音乐也不再有 `3000` 独立服务。

## 验证

```bash
npm --prefix frontend run check
npm --prefix frontend run test:unit
scripts/check-all.sh
```

后端测试使用临时测试数据，不连接生产数据库。完整发布前还要执行 `scripts/release-gate.sh`，并检查 `git diff --check`。

正式功能入口包括 `/`、`/article/*`、`/content/*`、`/login`、`/register`、`/rooms/music`、`/rooms/watch`、`/live`、`/account`、`/transfer/:token` 和 `/admin/*`。`/music` 与 `/tools/sync-room` 仅作为旧链接重定向保留；Articles 和音乐不再有独立 Node 服务、iframe 或 3000/3100 端口。

## 发布资料

- [架构说明](./docs/architecture.md)
- [安全说明](./docs/security.md)
- [数据格式](./docs/data-formats.md)
- [迁移说明](./docs/migrations.md)
- [部署说明](./docs/deployment.md)
- [Release/CI/CD 运维说明](./docs/operations/release-cicd.md)
- [测试说明](./docs/testing.md)
- [发布检查表](./docs/release-checklist.md)
- [Elysium 服务器布局](./docs/migration/elysiumm-server-layout.md)
- [阶段一交接记录](./docs/migration/2026-08-14-phase1-handoff.md)
- [Docker 说明](./DOCKER_GUIDE.md)
- [环境说明](./ENVIRONMENT_NOTES.md)
- [最终报告](./FINAL_REPORT.md)

生产发布前必须完成最终备份、校验、DNS/HTTPS、登录权限、媒体播放、实时能力和 Obsidian 同步验收；本仓库的代码清理不会自动修改生产服务或数据库。
