# Elysium 数据格式与公开契约

## HTTP 与 JSON

结构化请求/响应使用 UTF-8 JSON，上传使用 `multipart/form-data` 或管理员专用 tus 流程。没有统一 response envelope；每条路由由 Pydantic 明确响应形状。未知字段、非法标识、危险 URL 和超出边界的值应拒绝，不能静默截断。

状态码边界：

| 状态码 | 含义 |
| --- | --- |
| `200/201/204` | 成功 |
| `400` | 合法身份下的无效领域操作 |
| `401/403` | 缺少/无效凭据；或已认证但无权限 |
| `404` | 不存在，或在当前用户范围内隐藏 |
| `409` | Version conflict，客户端必须先重新取状态 |
| `413/415/422` | 大小、媒体类型或 schema 校验失败 |
| `429` | 限流；应返回 `Retry-After` |
| `503` | 维护中或必需依赖暂不可用 |

## 分页、排序与版本

列表使用有上限的 `skip/limit`、`page` 或路由明确的分页参数；数据库/显示顺序必须稳定，存在 position/display 字段时客户端不能假设插入顺序。history、event 等接口按各自路由限制最大范围。

可变房间、播放状态、Books 和列表使用 integer revision/version。客户端发送最后观察到的版本，服务端在同一事务中只递增一次；旧版本返回 `409` 和可安全恢复的最新状态（若该路由支持）。不能直接重放旧动作。

## Room Core Snapshot

媒体 Snapshot 至少包含媒体身份、播放/暂停、位置、速率、服务端时间锚点和 playback version。音乐保留兼容的 `track_id`；视频使用播放列表项身份。客户端根据服务端时间估算位置，发生重连、页面恢复或冲突时重新取 Snapshot。

Snapshot 不得包含 provider Cookie、受管存储路径或其他用户私有数据；buffering、音量和全屏属于客户端临时状态，不写入权威播放快照。Socket.IO 的 `client_instance_id`、`operation_seq`、`clock_probe` 是可选扩展，旧客户端仍按兼容行为处理。

实例与操作序号必须成对提供；服务端按用户、房间、UUID 实例判定重复和乱序。进程内 guard 最多保留 20,000 条、24 小时；不代替持久版本检查，重启后仍由 version/media_id 阻断过时曲目控制。旧客户端两字段都缺失时保留原兼容路径。控制操作必须匹配当前媒体身份。

成员成功加入后及每 30 秒发送 `clock_probe`，断线清空待回应采样；服务端只回应已认证的房间成员。客户端取最近 8 次有效样本的最低 RTT 估算时钟偏移；重连先取权威 Snapshot，再恢复控制，不上传旧队列快照覆盖新状态。

## Public Sync

管理员创建/轮换设备时，完整 opaque credential 只显示一次；请求通过 `X-Sync-Token`，数据库只保存 digest 和 hint。路径必须是设备根目录下的 normalized relative path。

整文件上传携带 path、声明大小和 SHA-256；分块上传另外绑定 upload id、总大小、总摘要、chunk index/count。重复的相同 chunk 和相同 completed identity 可幂等处理；元数据或内容冲突必须失败。服务端在临时存储中组装，校验大小/摘要/配额后原子替换，再记录事件。

## 导入、导出与 Books

Collection 支持 JSON 和 Netscape bookmark HTML。JSON 保留文件夹树、bookmark metadata、tags 和允许的展示字段；导入有 dry-run、有界输入、重复处理以及 cycle/missing-parent 校验。真实导入先创建安全备份，再以一个事务写入，失败回滚。

HTML import 将标题和 URL 当作不可信文本，保留有效嵌套文件夹，不导入 script URL。两种格式都不能携带登录 token、存储路径或服务器配置。

Books JSON 只包含已发布元数据、安全封面引用和列表；内部 draft/revision 只出现在管理员响应。网站不输出 Kavita reader URL 或服务器凭据。Books 表和迁移仍受保护，不因旧 Books 页面退役而删除。

## 管理员上传

管理员 tus 上传由 `/api/admin/tus/` 管权限、配额、摘要和最终入库；tusd 只做 loopback 分片暂存。未完成内容位于 release 外的 shared 路径，最终文件沿用现有文件表、私有下载地址和 Range 处理。公开 transfer token 只允许读取/下载。

## 备份产物与恢复边界

MariaDB/MySQL 备份使用 `.sql`，隔离 SQLite 演练使用 `.sqlite3`。release/rollback 包可包含 `frontend.tar.gz`、旧配置、service 配置、`candidate-revision.txt`、`previous-revision.txt` 和 `SHA256SUMS`；配置包可能含 secret，必须受限权限且不能由 HTTP 提供。

恢复不能把数据库文件直接当作任意 source，不能读取受管 backup root 外的路径，也不能接受绝对路径、穿越或 link 条目。恢复/回滚命令和证据要求见 [部署指南](./deployment.md)、[迁移指南](./migrations.md) 与 [安全模型](./security.md)。
