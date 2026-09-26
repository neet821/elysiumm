# Elysium 音乐服务

## 运行边界

Python 后端的音乐适配层只访问内部地址 `http://127.0.0.1:8765`。本地预览先启动并检查 Node sidecar，再启动后端；生产中 `elysiumm-music-api.service` 与 `elysiumm-backend.service` 均由 systemd 管理，sidecar 仅监听 loopback。浏览器不直接请求音乐上游，也不接触平台 Cookie。

网易云搜索、歌曲 URL、歌词和公开歌单读取经由内部 NeteaseCloudMusicApiEnhanced 服务。适配层可使用管理员配置的平台凭据；内部服务不保存用户平台账号。一般解灰／跨来源自动解析保持关闭，歌曲解析失败必须由后端按原有可用性状态返回，不能静默换歌。

## 第三方组件与许可

| 组件 | 固定版本 | 用途 | 许可 |
| --- | --- | --- | --- |
| `@neteasecloudmusicapienhanced/api` | `4.40.1`（`backend/music_node/package-lock.json`） | 网易云 API 的内部 Node 服务 | MIT（以锁文件包元数据为准） |

Elysium wrapper 位于 `backend/music_node/server.cjs`，不是上游源码副本。改版本时应同时审查上游版本、Node 运行时要求、API 行为和许可证，并更新 package manifest 与 lockfile。运行时需要 Node.js 22 或更新的兼容版本及 npm。

UnblockNeteaseMusic (UNM) 当前没有接入生产路径；跨来源匹配必须先能提供足够的歌曲身份／时长证据，才能单独评估启用。NeriPlayer 仅借鉴协议与测试场景，不复制其实现代码。

## 升级与回滚

Node 依赖在 backend release 构建阶段根据锁文件以 `npm ci --omit=dev` 安装。sidecar systemd unit 的工作目录指向 `backend-current/backend/music_node`；backend current 切换及显式 backend 回滚都会同步音乐服务。若回滚到尚未包含 sidecar 的旧 backend release，部署器会停止并禁用 sidecar，再重启旧后端。CI 固定使用 Node.js 22，并运行 wrapper 的 Node 测试。

生产主机需预先安装 Node.js 22+ 与 npm，并让 `node` 在 systemd 的固定 PATH 中可见。缺失或版本过低时发布在激活 release 前失败，不会把不可运行的音乐服务切到生产。
