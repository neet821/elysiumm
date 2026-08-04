# Task 4：固定相机系统报告

## 结果

- 完成 `overview`、`desk`、`right` 三个固定机位。
- 完成位置、视线目标和视角大小的同步缓动；终点会精确写回目标值，不留下累计误差。
- 完成临时聚焦与恢复；恢复目标是聚焦前的固定机位。
- 完成受限鼠标视差：输入先夹在 `[-1, 1]`，再平滑响应；相机位置偏移量为 `0.055`，视线目标偏移量为 `0.14`，极端输入造成的方向变化不超过测试限定的 `2.5°`。
- 未使用 OrbitControls，也未接入界面按钮、鼠标事件或后续交互系统。

## RED / GREEN

### RED

1. 相机测试先于正式模块加入，首次运行因 `CameraRig.js` 尚不存在而失败：`1 failed suite`。
2. 工作区随后并发出现同任务范围内的更严格测试契约，要求额外支持 `CAMERA_PRESET_NAMES`、`cubicEaseInOut`、任意 `initialPose`、非法聚焦姿态拒绝、FOV 插值。保留该测试后，首次对照运行结果为 `7 tests / 6 failed / 1 passed`，失败点与这些新增要求一致。

### GREEN

- 相机专项测试：`tests/camera.test.js`，`7/7` 通过。
- 覆盖三个机位的有限值和安全时长、聚焦姿态有限值拒绝、缓动精确端点、位置/目标/FOV 同步插值、`0.8–2s` 时长夹紧、精确终点、恢复、鼠标视差夹紧。
- 并发契约与原任务没有冲突，最终已全部兼容，没有覆盖或删除其测试。

## 最终机位

| 机位 | 位置 | 视线目标 | FOV | 时长 |
| --- | --- | --- | ---: | ---: |
| overview | `[-9.8, 6.6, 11.5]` | `[0.4, 2.55, -0.65]` | 38 | 1.35s |
| desk | `[-1.2, 2.9, 4.2]` | `[-1.2, 2.75, -2.7]` | 42 | 1.10s |
| right | `[0.5, 2.85, 0.05]` | `[5.78, 2.85, 0.05]` | 52 | 1.20s |

## 真实 Chromium 检查

使用本机 Google Chrome Stable 以真实 WebGL 页面渲染，检查了 `1920×1080` 和 `1920×1200` 两种比例下的全部三个机位。

- overview：桌子、整幅飘窗和右墙区域同时进入画面，房间边界完整。
- desk：接近坐在桌前的视角，显示器为中心，窗景仍清楚可见。
- right：正对右墙；唱片机、唱片架、书架、海报、照片墙全部清楚。首轮左下角有桌子近景遮挡，最终将机位移到桌子之后并重新拍摄，遮挡已消除。
- 16:9 与 16:10 下主体均未被关键裁切；16:10 只裁到顶层装饰植物的少量顶部，不影响要求主体。

最终截图保存在：

- `.superpowers/sdd/2026-08-04-elysium-room/task-4-screenshots/overview-1920x1080.png`
- `.superpowers/sdd/2026-08-04-elysium-room/task-4-screenshots/desk-1920x1080.png`
- `.superpowers/sdd/2026-08-04-elysium-room/task-4-screenshots/right-1920x1080.png`
- `.superpowers/sdd/2026-08-04-elysium-room/task-4-screenshots/overview-1920x1200.png`
- `.superpowers/sdd/2026-08-04-elysium-room/task-4-screenshots/desk-1920x1200.png`
- `.superpowers/sdd/2026-08-04-elysium-room/task-4-screenshots/right-1920x1200.png`
- 汇总图：`.superpowers/sdd/2026-08-04-elysium-room/task-4-screenshots/contact-sheet-final.png`

### 浏览器中的动画端点

- overview → desk：`0s` 保持 overview；`0.55s` 到达中点 `[-5.5, 4.75, 7.85]`、FOV `40`；`1.10s` 精确到达 desk，`isTransitioning=false`。
- desk → right：`0s` 保持 desk；`0.60s` 到达中点 `[-0.35, 2.875, 2.125]`、FOV `47`；`1.20s` 精确到达 right，`isTransitioning=false`。
- 两段切换起点方向保持原姿态，位置、视线和 FOV 连续变化；没有发现方向跳变。

## 全量验证

- `npm test -- --run`：4 个测试文件、22 个测试全部通过。
- `npm run build`：成功，Vite 产物正常生成。
- `git diff --check`：通过，无空白格式问题。
- 正式源码中没有临时预览入口，也没有 OrbitControls 引用。

## 自检

- 三个固定机位均为有限数值，默认切换时长都位于 `0.8–2s`。
- 任意聚焦姿态中的位置、目标、FOV 或时长出现非有限值时会立即拒绝。
- 视差从基础姿态重新计算，不会逐帧累积漂移。
- 变焦投影矩阵在 FOV 变化时同步更新。
- 没有接入 Task 7 的界面或交互职责。
- 未发现遗留问题。

## 提交

- 实现提交：`7141552`（`feat: add fixed camera rig`）
