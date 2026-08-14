# Elysium 接管第一阶段交接记录

日期：2026-08-14

## Blue Album 保护结果

- 分支：`dev`
- 提交：`7eec1317e473e6075456a50981743736d7736ff0`
- 远程：`origin/dev` 与本地提交一致
- 检查：`npm run check` 通过；包含 238 项单元测试和正式构建
- 说明：检查中保留了已有 lint 警告，但没有错误；本次没有修改这些无关警告

## 服务器恢复快照

- 完整快照：`/home/blue-album/backups/elysium-migration-20260814T080135Z`
- 规模：约 4.7GB
- 校验清单 SHA-256：`7ff0f37089cdf8760727c406503db6d600c9c2130a5729ff8e69ed4dd259f251`
- 校验复核：95/95 项通过
- 脱敏归档：`/home/blue-album/backups/elysium-migration-20260814T080135Z/elysium-archive-manifest.tar.gz`
- 脱敏归档 SHA-256：`21987317e7ac6c4c7bbf68abf255fe8631efa49d1a4ddac303da6fd2c33cfe5e`

完整快照包含网站、代码、上传文件、录像、MariaDB 逻辑备份、CouchDB 数据、服务定义、Nginx 配置和证书恢复材料。完整快照只留在服务器受控备份目录，不进入 Git。

脱敏归档只包含版本、服务名称、路径和校验信息，已扫描确认不含环境文件、数据库、上传内容、录像、令牌、Cookie、私有同步数据或证书私钥，可作为旧私有仓库的归档附件。

## 线上状态

以下服务在快照前后均保持运行，本阶段没有停止或重启服务：

- `blue-backend.service`
- `blue-mineradio.service`
- `blue-album-mediamtx.service`
- `nginx.service`
- `mariadb.service`
- `frps.service`

本阶段未修改 DNS、HTTPS、Nginx、数据库、CouchDB、Obsidian 配置或线上程序目录。
