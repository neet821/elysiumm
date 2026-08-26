# 房间分享与听歌体验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成房间分享链接、听歌房体验修复、播放历史、搜索输入和按钮视觉改动并部署。

**Architecture:** 保留现有房间 REST/WebSocket 同步协议；分享链接由前端当前路由生成；历史继续使用后端 `MusicRoomEvent` 脱敏接口；播放器只在房间边界和权威曲目变化时重置/同步。

**Tech Stack:** React, Vitest, FastAPI, SQLAlchemy, pytest/unittest, Vite, systemd/Nginx。

**Spec:** `docs/superpowers/specs/2026-08-26-room-share-music-history-design.md`

## Global Constraints

- 保留工作区已有未提交修改，不覆盖无关文件。
- 用户可见房间分享内容使用完整 URL，不显示房间号或用户编号。
- 搜索输入允许词间空格，提交时只清理首尾空白。

### Task 1: 房间列表与分享链接

**Files:**
- Modify: `frontend/src/pages/SyncRoomList.jsx`
- Modify: `frontend/src/pages/RoomsPage.jsx`
- Modify: `frontend/src/pages/roomsHub.css`
- Test: `frontend/tests/syncRoomList.test.jsx`

- [ ] 写失败测试：房间卡片不显示房间号、显示复制分享按钮；入口顺序为观影房后听歌房。
- [ ] 运行目标测试确认失败。
- [ ] 实现完整当前 URL 复制、成功提示和回退复制。
- [ ] 运行目标测试确认通过。

### Task 2: 听歌房播放器与搜索

**Files:**
- Modify: `frontend/src/pages/MineradioPage.jsx`
- Modify: `frontend/src/features/player/MineradioRoomEmbed.jsx`
- Modify: `mineradio/public/blue-album-room-bridge.js`
- Modify: `mineradio/public/js/modules/05-playback/07-search.js`
- Test: `frontend/tests/mineradioRoomEmbed.test.jsx`, `frontend/tests/musicLobby.test.jsx`

- [ ] 写失败测试：新房间清空旧曲目，搜索词间空格保留，切歌命令不等待旧播放结束。
- [ ] 运行目标测试确认失败。
- [ ] 实现房间边界 reset、切歌顺序修复和搜索输入处理。
- [ ] 运行目标测试确认通过。

### Task 3: 历史记录与文案/视觉收口

**Files:**
- Modify: `frontend/src/pages/MineradioPage.jsx`
- Modify: `frontend/src/pages/SyncRoomList.jsx`
- Modify: `frontend/src/features/player/mineradioRoomStage.css`
- Test: `frontend/tests/roomPlayerPage.test.jsx`, `backend/tests/test_music_room_history_unittest.py`

- [ ] 写失败测试：历史播放记录展示、Mineradio 同步听歌和用户编号不出现、按钮具有高对比样式。
- [ ] 运行目标测试确认失败。
- [ ] 实现历史面板和文案/样式收口；不改动已有脱敏规则。
- [ ] 运行前后端目标测试确认通过。

### Task 4: 全量验证、提交与部署

**Files:**
- No new source files.

- [ ] 运行前端全量测试、后端房间/音乐测试、构建和 `git diff --check`。
- [ ] 检查生产部署脚本和当前服务，执行项目规定的部署流程。
- [ ] 部署后检查健康接口、页面文案和房间分享按钮。
- [ ] 提交所有本次及工作区已有相关改动，报告提交和部署结果。
