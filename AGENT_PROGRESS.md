# Elysium 执行进度

权威目标：`elysium_targets_full.md`

## 当前状态

- 当前阶段：单仓迁移完成，生产切换完成，等待 Obsidian 首次同步验收
- 总体状态：Elysium 已在新域名正式运行；旧运行服务已停用；Obsidian 加密连接尚未改动
- 发布版本：`c88c840`
- 私有仓库：[neet821/elysiumm](https://github.com/neet821/elysiumm)

## 已确认基线

- `npm test -- --run`：4 个文件，25 项通过
- `npm run build`：通过
- 当前问题：三块平窗、开放模型盒、椅子遮挡、右墙结构失真、蓝灰配色和旧机位偏差

## 阶段进度

- [x] Phase 0：读取参考图、旧会话、现有代码和测试，建立差异清单
- [x] Phase 1：房间壳体、八扇折角凸窗、连续窗景
- [x] Phase 2：无椅子的桌面区域
- [x] Phase 3：右墙低柜、搁板、照片网格和海报
- [x] Phase 4：暖色材质、灯光和界面
- [x] Phase 5：三个固定机位和聚焦姿态
- [x] Phase 6：交互、页面和完整回归
- [x] Phase 7：九张最终截图和最终验收
- [x] 追加改造：左右侧窗、顶框、横档和窗台改为标准直角

## 下一步

在主设备 Obsidian 的 LiveSync 设置中，将同步地址改为 `https://sync.elysiumm.top`，然后完成一次上传、下载、重启和恢复检查。连接配置已加密保存，不能直接编辑配置文件。

## 追加改造证据

- 左右侧窗旋转角度均为精确 90°；
- 两侧窗固定在正面窗左右端点，不再斜向外扩；
- 顶框、横档、竖框和窗台全部随侧窗直角收口；
- 两侧新增独立景色面，正面和侧面均无空白；
- 1920×1080 的 Overview、Desk、Right 三个画面已人工检查通过。

## 当前验证

- `npm test -- --run`：4 个文件，26 项通过
- `npm run build`：通过
- `npm run test:e2e`：6 组通过
- 九张截图：1920×1080、1920×1200、2560×1440 的三个机位全部生成并人工检查
- 像素检查：九张截图标准差为 0.194680 至 0.252996，均为有效非空画面
- 环境截图：黄昏和夜晚画面均可见且结构稳定
- 场景规模：181 个网格、174 组轮廓线、约 3416 个三角面、51 个投影物体
- 最终门禁：文档和参考资源收口后再次执行，全部通过

## 单仓迁移验证

- Blue Album 2.5D 首页已提交并推送：`7eec1317e473e6075456a50981743736d7736ff0`
- 服务器迁移快照已生成并通过 95/95 校验，未修改线上服务和域名
- Elysium 单仓已包含 `frontend/`、`backend/`、`mineradio/`、`deployment/`、`scripts/` 和迁移文档
- 前端检查：42 个测试文件、239 项通过，构建通过，37 条既有 lint 警告、0 个错误
- 浏览器验收：默认 3D、轻量模式记忆、镜头切换、显示器启动器共 3 项通过
- 房间引擎回归：4 个文件、26 项通过
- 后端完整回归：374 项通过，0 失败，0 错误
- GitHub 私有仓库：已创建并推送，仓库历史已清除私人文件
- DNS/HTTPS：`elysiumm.top`、`www.elysiumm.top`、`sync.elysiumm.top` 均已验证
- 服务器：`elysiumm-backend.service`、`elysiumm-mineradio.service`、`elysiumm-mediamtx.service` 均正常；旧三个 Blue Album 服务已停用
- 生产检查：主页、八个正式入口、API 健康检查、音乐入口和四个直播媒体端口通过
- 最终备份：`/home/blue-album/backups/releases/elysium-final-20260814T130313Z`，校验通过
- 尚未执行：Obsidian LiveSync 首次上传/下载/重启/恢复验收；旧域名 DNS 记录由用户自行管理，服务器已不再启用旧站服务
