# 多环境启动与隔离

同一仓库支持 WSL/Linux、Codespaces、Docker Compose 和 Debian 裸机。代码共享，环境文件、数据库、受管文件、日志和凭据按环境隔离。

## 配置文件

后端参考 `backend/.env.example`，前端参考 `frontend/.env.example`。本地实际文件是 `backend/.env` 与 `frontend/.env`；裸机生产的唯一输入文件是服务器本地 `backend/prod.env`。这些文件均被忽略，不得提交。

生产必填项包括：

- `DATABASE_URL` 与 `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME`
- `SECRET_KEY`、`ALGORITHM`、令牌有效期
- `HOST`、`PORT`、无通配符的 `CORS_ORIGINS`
- `VITE_API_BASE_URL`、`VITE_WS_BASE_URL`、`DOMAIN`（可选 `DOMAIN_WWW`）
- 绝对路径 `PUBLIC_SYNC_STORAGE`、`PRIVATE_STORAGE_DIR`、`ADMIN_FILES_STORAGE_DIR`、`BACKUP_OUTPUT_DIR`
- 可选、无凭据的 `KAVITA_PUBLIC_BASE_URL`
- 用于校验外部视频真实公网地址的 `EXTERNAL_MEDIA_DOH_URL`；默认使用 Cloudflare 公共 DNS，可替换为兼容 DNS JSON 的可信服务

示例中的 `CHANGE_ME` 是故意无效的。用外部安全方法生成密钥，环境文件权限设为 `600`。数据库 URL 中的特殊字符按 URL 规则编码。

## WSL / Linux 开发

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
./start-wsl.sh
```

填写本机数据库和 localhost 来源。后端监听 `127.0.0.1:8000`，Vite 默认监听 `0.0.0.0:5173`。脚本在服务前运行正式迁移，但开发数据仍应自行备份。

## GitHub Codespaces

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
./start-codespace.sh
```

按 Codespaces 实际转发域名填写 API、WebSocket 和 CORS；不要把任意 `*` 当成生产配置。端口可见性和数据库安装由 Codespace 操作者管理。

## Docker Compose

```bash
./start-docker.sh
```

若根目录 `.env` 不存在，脚本只复制 `.env.docker` 并退出。替换所有占位值后再次运行。Docker 后端使用 Python 3.12，前端用 Node 20 锁文件构建；数据库健康、后端健康后才开放前端。详情见 [Docker 指南](./DOCKER_GUIDE.md)。

## Debian 裸机生产

生产拓扑是 Nginx 静态前端、MariaDB/MySQL、Mineradio 和一个 Uvicorn 后端进程。必须保持**单进程**，因为 Socket.IO 房间、在线状态和部分限速状态尚未共享到外部存储。

生产脚本不选择或下载代码。操作者先签出已审查提交并保持工作树干净，准备数据库、证书、目录和 `backend/prod.env`，再运行：

```bash
sudo scripts/release-preflight.sh \
  --env-file backend/prod.env \
  --health-url http://127.0.0.1:8000/api/health
sudo PROD_ENV_FILE="$PWD/backend/prod.env" ./start-prod.sh
```

发布先执行不写入的工具、配置、仓库、空间、数据库和健康检查；随后创建带校验清单的**迁移前发布包**，才允许安装依赖、执行迁移、更新服务和切换前端。失败停止并保留包。第一次接管已有服务需显式提供 `PREVIOUS_RELEASE_REVISION`；真正空白主机才可使用 `ALLOW_COLD_START=1`。

回滚不是自动数据库降级。先 `--verify-only` 验证指定发布包，再以精确确认字符串执行**显式回滚**，同时恢复数据库、上一代码提交、配置、服务和前端。完整命令与停止条件见 [部署与回滚](./docs/deployment.md)。

## 隔离与日志

- `.env`、`backend/prod.env`、上传、私密存储、同步存储、备份、虚拟环境、`node_modules` 和构建产物不入 Git。
- 裸机服务日志用 `journalctl -u blue-backend.service` 与 `journalctl -u blue-mineradio.service`；Nginx 使用系统日志。
- Docker 日志用 `docker compose logs`；业务持久数据在命名卷，不在容器可写层。
- 自动测试创建 temporary SQLite/文件/浏览器状态，不读取生产配置。

## 发布流转

功能分支完成后先通过本地门禁与 CI，再合并到发布分支。服务器由操作者显式获取并签出已审查提交；发布脚本只部署当前提交。不要在生产脚本运行期间同时改代码、环境文件或数据库结构。
