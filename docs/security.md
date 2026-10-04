# Elysium 安全模型

## 威胁与信任边界

浏览器、上传文件名和内容、房间 payload、同步设备客户端及第三方服务都按不可信或可能不可用处理。主机管理员、root-owned 生产环境文件和数据库负责人是运维信任边界。目标是避免越权、路径穿越、身份伪造、旧版本写入、凭据泄露和恢复包被篡改。

## 身份认证与授权

- 密码使用 bcrypt 12 rounds，并先执行字节长度限制；HTTP 使用区分类型的 access/refresh JWT。
- 每个受保护请求重新解析活动用户；未知、停用、缺失或非法用户都拒绝。Socket.IO 只信任握手解析出的用户，不信任事件 payload 中的 user id。
- `SECRET_KEY` 必须存在、足够长且不能是占位值；生产放在仓库外的 mode-600 环境文件中，轮换视为协调登出事件。数据库密码、同步设备凭据和 provider Cookie 不能提交或打印。
- 权限在 router 和 service 两层执行。普通用户只能访问自己的私有 Collection 和已加入房间；管理员接口要求活动管理员身份；停用账号应阻断新的 HTTP/Socket.IO 活动。
- 管理员文件用认证后的数字下载路由和私有 UUID 存储名；视频/字幕流需要成员权限或短期媒体 token；公开 `/uploads` 不是私有文件根目录。

## 浏览器、实时与限流

CORS 使用显式 allowlist，生产拒绝 `*`；生产 API/WebSocket 应由 Nginx 同源转发。外部链接只做普通导航，不能把 secret 拼到 URL。

实时部署保持单 worker。播放控制带 bounded payload 和 expected version；旧版本请求返回冲突而不是覆盖当前状态，重连回到权威 Snapshot。登录、管理员变更、上传、provider 搜索和实时变更使用进程内限流；多 worker 需要另行设计共享 limiter/Socket.IO manager。

Audit 记录 actor、action、resource、结果和有限安全详情，不记录 token、私信、凭据、绝对路径或异常原文。

## 文件、上传与外部 URL（SSRF）

上传先写受控临时文件，校验类型、大小、摘要和危险内容后原子发布；文件名只是显示元数据。读取、删除、备份、恢复都必须把数据库路径重新解析到配置根目录下，拒绝绝对路径、穿越、跨根和篡改路径，并清理失败的部分状态。

管理员断点上传只经过同源 `/api/admin/tus/`，tusd loopback-only；公开传输链接只读/下载。后端不得把 tusd 地址、服务器路径或 provider Cookie 交给浏览器。

服务端音频解析只接受选定 provider allowlist 中的无凭据 HTTP(S) 地址。Kavita 是独立服务，网站不派生或抓取其链接。外部视频由 `external_media.py` 探测和代理：每一跳都校验 HTTP(S)、凭据、端口和公共 DNS/IP，最多 5 次重定向，探测读取有界前缀并核对真实媒体格式；HLS 和 Range 继续经过成员授权。DNS 校验不等于系统级出站隔离，部署仍需合理的网络访问限制。

## 备份、恢复与隐私

发布/回滚包属于敏感配置，必须 root-owned、受限权限并在受控根目录内校验 `SHA256SUMS`。恢复拒绝根目录外路径、绝对/穿越/link 条目、摘要不匹配、缺失产物或缺失上一版本；回滚需要 root、精确确认字符串，并在变更前再留一份安全包。数据库恢复不能靠猜测 Alembic downgrade。

公开序列化不返回 ownership-only 描述、凭据 digest、存储路径、provider Cookie 和内部异常。Books 只返回发布元数据，不集成 Kavita reader 链接；Public Sync 的设备 secret 只在创建/轮换时返回，房间历史按查看者过滤。

直播观看先服务端授权，再使用短期 HttpOnly cookie；邀请撤销后后续 HLS 请求也必须失败。stream key 和 invite token 只返回一次并只存 digest；访客信息限管理员可见并默认保留 90 天，IP 地区解析使用本地数据，不发给第三方。HTTPS 部署使用 `LIVE_COOKIE_SECURE=1`；只有明确受控的 HTTP 测试环境才使用 `0`，不能从历史部署记录推定当前配置。

## 已知限制与人工责任

JWT 没有逐会话 denylist；短 access lifetime、停用账号和 key rotation 是现有控制。Release 包是 root-owned checksum，不是外部签名。TLS、主机防火墙、数据库 grants、异地备份、告警和系统补丁仍由运维负责。FlClash/FlClashCore 不属于 Elysium 安全或部署控制面。

安全检查只能报告实际执行的证据；单个 HTTP 200、静态配置存在或测试构建成功都不等于生产安全验收。相关发布条件见 [部署指南](./deployment.md)、[数据格式](./data-formats.md) 和 [发布检查表](./release-checklist.md)。
