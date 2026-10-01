# Elysium 音乐服务

## 运行边界

Python 后端的音乐适配层只访问内部地址 `http://127.0.0.1:8765`。本地预览先启动并检查 Node sidecar，再启动后端；生产中 `elysiumm-music-api.service` 与 `elysiumm-backend.service` 均由 systemd 管理，sidecar 仅监听 loopback。浏览器不直接请求音乐上游，也不接触平台 Cookie。

网易云搜索、歌曲 URL、歌词和公开歌单读取经由内部 NeteaseCloudMusicApiEnhanced 服务。适配层可使用管理员配置的平台凭据；内部服务不保存用户平台账号。一般解灰／跨来源自动解析保持关闭，歌曲解析失败必须由后端按原有可用性状态返回，不能静默换歌。

## 第三方组件与许可

| 组件 | 固定版本 | 用途 | 许可 |
| --- | --- | --- | --- |
| `@neteasecloudmusicapienhanced/api` | `4.40.1`（`backend/music_node/package-lock.json`） | 网易云 API 的内部 Node 服务 | MIT（以锁文件包元数据为准） |
| `@neteasecloudmusicapienhanced/unblockmusic-utils` | `0.4.4`（传递依赖） | 上游的跨来源匹配工具 | MIT（以锁文件包元数据为准） |
| `@unblockneteasemusic/server` | `0.28.0`（传递依赖） | 上述工具调用的音源实现 | LGPL-3.0-only（以锁文件包元数据为准） |

Elysium wrapper 位于 `backend/music_node/server.cjs`，不是上游源码副本。改版本时应同时审查上游版本、Node 运行时要求、API 行为和许可证，并更新 package manifest 与 lockfile。运行时需要 Node.js 22 或更新的兼容版本及 npm。

`unblockmusic-utils` 与 UNM server 当前随上游 API 锁定安装，但 Elysium 不调用其跨来源匹配接口；sidecar 强制设置 `ENABLE_GENERAL_UNBLOCK=false`，防止 `/song/url/v1` 静默替换音源。检查锁定版本的实现，匹配结果对调用方只返回候选 URL 和来源，未返回被匹配曲目的歌曲 ID、标题、艺人及实际时长；因此现阶段不足以按 Elysium 的身份／时长策略证明它仍是原曲。跨来源替代播放保持关闭。未来只有在匹配服务返回可核验的目标歌曲信息、Elysium 对标题/艺人/时长验证通过并记录实际来源后，才可新增显式接入；上游暂不可用也不得改变现有同源播放行为。

锁文件中 LGPL 组件是运行时传递依赖；升级、再分发或改变部署形态时必须重新检查对应许可证文本和履行要求。锁文件的许可证字段是依赖元数据，不替代法律审查。NeriPlayer 仅借鉴协议与测试场景，不复制其实现代码。

## 升级与回滚

Node 依赖在 backend release 构建阶段根据锁文件以 `npm ci --omit=dev` 安装。sidecar systemd unit 的工作目录指向 `backend-current/backend/music_node`；backend current 切换及显式 backend 回滚都会同步音乐服务。若回滚到尚未包含 sidecar 的旧 backend release，部署器会停止并禁用 sidecar，再重启旧后端。CI 固定使用 Node.js 22，并运行 wrapper 的 Node 测试。

生产主机需预先安装 Node.js 22+ 与 npm，并让 `node` 在 systemd 的固定 PATH 中可见。缺失或版本过低时发布在激活 release 前失败，不会把不可运行的音乐服务切到生产。
