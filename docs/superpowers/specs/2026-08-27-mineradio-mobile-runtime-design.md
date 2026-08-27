# Mineradio 独立移动端运行时设计

## 目标

让 iPhone、Android 和 iPad 在 Mineradio 同一入口下进入独立的轻量移动端运行时：移动端不加载桌面 Three.js 播放器、桌面模块或桌面节奏分析链路，顶栏和控制栏继续复用现有 DOM/按钮语义，歌词由移动端 DOM 渲染器独立显示。

## 边界

- 移动设备由 User-Agent、iPad 桌面 UA 的触控点和平台信息判断；不能用 viewport 宽度决定模式。
- 桌面端继续使用现有 `index-loader.js` 和 Three.js 播放器，行为不变。
- 移动端复用搜索框、返回按钮、房间按钮、底部控制栏的 DOM 和图标，但使用移动端自己的事件绑定与状态管理。
- 歌词设置按钮离开顶栏，放在歌词区域下方的独立固定槽位。
- 移动端不请求 Three.js、music-tempo、GSAP、桌面模块和任何离线节奏分析资源。

## 启动分流

`mineradio/public/index.html` 只保留基础 HTML、共享样式和一个极小的启动分流器。移动设备加载 `mobile-runtime.css` 与 `mobile-runtime.js`；桌面设备加载现有桌面 vendor 脚本和 `index-loader.js`。分流器必须在桌面 vendor 标签之前执行，避免移动端先产生下载请求。

## 移动端运行时

新运行时负责：搜索结果展示、音频 URL 获取、HTMLAudioElement 播放、歌词请求和解析、房间入口、进度更新、暂停/继续/上一首/下一首/音量/沉浸操作。它只维护一个音频对象和一个歌词 DOM 窗口（上一句、当前句、下一句），歌词更新以 `timeupdate` 为主，必要时使用受限的 rAF；长句使用 CSS 自然换行，不创建 Canvas、纹理或 Three.js Mesh。

## 顶栏与控制栏

顶栏采用固定三槽：左侧返回，中间搜索，右侧房间。账户/状态类按钮不得参与顶栏自动 flex 堆叠；歌词设置按钮固定在歌词区域下方，和顶栏脱离。底部控制栏继续使用既有按钮 ID、图标和可访问名称，由移动运行时重新绑定。中心 transport 集群继续隐藏。

## 故障与回退

- 搜索、音源、歌词或房间请求失败时显示轻量 DOM 状态，不回退加载桌面播放器。
- 移动端不会调用 `analyzeAudioBeats`、`analyzePodcastDjBeats`、Cuefield AutoMix 或本地节奏分析弹窗。
- 桌面端启动失败仍保留现有错误处理。

## 验收

- 静态测试确认移动入口不包含桌面 vendor/index-loader 请求，iPad 桌面 UA 仍选移动入口。
- JS syntax check、移动端专项测试和生产构建通过。
- 使用真实移动 UA 访问公网 Mineradio，确认网络请求没有 Three.js/music-tempo/GSAP/桌面模块，并验证搜索、播放、暂停、切歌、歌词异步切换、房间和顶栏按钮无重叠。
