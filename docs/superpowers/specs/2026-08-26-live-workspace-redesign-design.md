# Live Workspace Redesign

## Goal

Make the live watch page a compact video surface and turn the administrator live page into one focused workspace with an embedded preview, compact settings, expandable audience details, and one reusable invite link.

## Scope

- The public watch view keeps only the stream title, video surface, and useful playback controls.
- Playback controls are play/pause, refresh stream, volume, and fullscreen. Volume starts muted at value `0`; there is no separate sound prompt.
- Waiting or ended broadcasts show only `未开播` centered in the video surface.
- The administrator page removes the old live-management copy, standalone refresh action, public-watch link, recording controls, and unnecessary stream-setting fields.
- OBS connection information is shown inside the opening settings section.
- The administrator page embeds the same compact player between the status bar and settings.
- Audience count in the status bar is interactive and opens the existing detailed audience table.
- The invite section is rendered only for `access_mode === 'invite'`, shows at most one active invite, permits repeated use by multiple viewers, and supports manual revocation.
- Historical invites are not shown in the administrator UI.
- Historical live sessions remain available but are collapsed by default.

## Data and compatibility

The existing live session, heartbeat, media authorization, settings, audience, invite, and recording APIs remain compatible. The invite-list and invite-create behavior gains an active-link constraint; no schema change is required because revoked and expired rows remain historical data while only one non-expired, non-revoked row may be active.

## Acceptance criteria

1. `/live?watch=1` renders the compact player for an administrator as well as for a regular viewer.
2. The refresh control reconnects the current stream without showing a separate sound button.
3. Initial volume is `0` and moving the volume slider controls the video directly.
4. Waiting/ended state has no hero card, backdrop, overlay, description, or large extra text; the centered state is `未开播`.
5. The administrator page contains no `直播管理`, `单直播间`, `设置 OBS、观看权限、访客记录和自动录像。`, `打开观看页`, `自动录像`, `自动录制直播`, `封面地址`, `目标码率（kbps）`, or standalone refresh action.
6. The administrator page embeds the video preview before opening settings and shows the audience table only after the viewer-count control is activated.
7. An invite link can be used by more than one viewer, only invite mode exposes its controls, and the UI never lists historical links.

