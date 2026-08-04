# Elysium 3D Room

一个纯前端实现的 3D 个人数字房间：Three.js 基础几何体 + 线稿轮廓，三个固定机位，窗外景观、时间环境、音乐、台灯与导航交互。视觉方法参考 pure-line-room，但房间布局、机位、交互与代码均为独立实现。

## 运行

```bash
npm install
npm run dev
```

打开 http://localhost:5173 即可。生产构建与预览：

```bash
npm run build
npm run preview
```

## 测试

```bash
npm test            # 单元测试
npm run test:e2e    # 浏览器端到端验收（使用本机 Chrome）
```

## 代码结构

- `src/main.js` — 应用装配：场景、房间、相机、环境、交互、界面与路由
- `src/scene/` — Three.js 运行时、线稿材质系统、窗外纹理加载
- `src/room/` — 房间壳体、凸窗、书桌区、唱片区、墙面装饰
- `src/camera/` — 三个固定机位、平滑过渡与受限鼠标视差
- `src/environment/` — 时间状态、调色板、环境控制器（灯光/窗景/台灯/唱片）
- `src/audio/RoomAudio.js` — Web Audio 合成的安静黑胶氛围音
- `src/interactions/` — 射线拾取、悬停反馈与交互行为
- `src/routes/` — Projects / Gallery / Reading / Movies 占位页配置
- `src/ui/` — 界面 HUD 与路由覆盖层
- `tests/` — 单元测试与 Playwright 端到端测试

## 三个相机在哪里定义

全部集中在 `src/camera/cameraPresets.js`：

- `overview` — 斜向总览（默认首页）
- `desk` — 正面电脑桌视角
- `right` — 右墙唱片区直视视角

每个机位包含位置、视线目标、FOV 和过渡时长。切换与推近动画由 `src/camera/CameraRig.js` 执行。

## 如何替换窗外图片

1. 把图片放到 `public/scenery/`，替换 `nature.svg` / `city.svg` / `cloudy.svg` / `night.svg`，或按 `src/scene/textureLoader.js` 中的 `SCENERY_URLS` 新增/改名。
2. 图片建议使用与窗洞比例接近的横图；代码会自动回退到内置纹理，不会黑屏。

## 如何修改主题 / 后期上色

所有颜色集中在 `src/environment/palette.js` 的四个调色板（清晨 / 白天 / 黄昏 / 夜晚）。每个调色板包含天空、地平线、环境、强调、文字与轮廓颜色。

材质如何取色定义在 `src/scene/primitives.js` 的 `DEFAULT_DEFINITIONS`：例如 `wood` 使用环境色填充，`dark` 使用轮廓色填充。想换一种木材颜色，只需调整调色板或材质定义，不用改动任何房间模型代码。

## 明确属于 Phase 2 的功能

- 真实天气 API 与动态天空
- 完整的内容页（当前是导航占位流程）
- PBR / 高精度材质与高模家具
- 移动端优先的构图与触控
- 生产级音乐流与外部音频资源
- 房间布局在线自定义
