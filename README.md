# Elysium

Elysium 是个人网站的唯一单仓。首页默认进入 Three.js 真 3D 房间，功能页继续使用原有地址、登录状态、接口、数据库和实时协议。

## 项目组成

- `frontend/`：React 功能站点、3D 房间和轻量 2.5D 模式
- `backend/`：FastAPI 接口、登录、内容、文件、管理和实时功能
- `mineradio/`：音乐服务
- `deployment/`：Docker、systemd、MediaMTX 和 Nginx 发布模板
- `scripts/`：检查、发布、备份、回滚和浏览器验收脚本
- `docs/`：架构、迁移、部署和发布门禁说明

## 本地运行

```bash
npm install
npm --prefix frontend install
npm run dev
```

默认访问 `http://localhost:5173`。前端代理会把 `/api`、上传、音乐、直播和 WebSocket 请求转发到本机服务。

## 验证

```bash
npm run check:frontend
npm run test:e2e:frontend
npm run test:room
npm run test:backend
```

后端测试使用临时测试数据，不连接生产数据库。完整发布前还要执行 `scripts/release-gate.sh`，并检查 `git diff --check`。

## 首页模式

首页固定提供 `3d` 和 `lite` 两种手动模式，默认值是 `3d`，选择保存在浏览器本地。3D 初始化失败时会明确提示切换，不会自动改变用户选择。

正式功能入口保持不变：

`/archive` · `/live` · `/music` · `/tools` · `/collection` · `/books` · `/games` · `/account`

## 发布资料

- [架构说明](./docs/architecture.md)
- [安全说明](./docs/security.md)
- [数据格式](./docs/data-formats.md)
- [迁移说明](./docs/migrations.md)
- [部署说明](./docs/deployment.md)
- [测试说明](./docs/testing.md)
- [发布检查表](./docs/release-checklist.md)
- [Elysium 服务器布局](./docs/migration/elysiumm-server-layout.md)
- [阶段一交接记录](./docs/migration/2026-08-14-phase1-handoff.md)
- [Docker 说明](./DOCKER_GUIDE.md)
- [环境说明](./ENVIRONMENT_NOTES.md)
- [最终报告](./FINAL_REPORT.md)

服务器切换前必须完成最终备份、校验、DNS/HTTPS、登录权限、媒体播放、实时能力和 Obsidian 同步验收。旧域名和旧仓库不会在此之前停用。
