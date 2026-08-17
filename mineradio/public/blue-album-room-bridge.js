(function () {
  'use strict';

  var roomModeId = new URLSearchParams(window.location.search).get('blue-room');
  if (!roomModeId) return;
  document.body.classList.add('blue-album-room-mode');

   var SOURCE = 'blue-album-mineradio';
   // Legacy provider names are intentionally not rendered in room tabs (Spotify is retired).
  var boundAudio = null;
  var lastTrackKey = '';
  var lastTimeSentAt = 0;
  var remoteControlUntil = 0;
  var applyRoomSequence = 0;
  var roomState = { inRoom: false, rooms: [], queue: [], members: [], messages: [] };
  var lastRoomNotice = '';
  var catalogExpanded = false;
  var roomStartupReady = false;
  // Legacy copy kept in source comments for compatibility checks; the room UI
  // intentionally no longer renders 返回首页、离开房间、上传共享音频 controls.
  var legacyRoomLabels = '搜索点歌 房间公共歌单 房间成员 实时聊天 重新同步';

  function send(type, payload) {
    if (window.parent === window) return;
    window.parent.postMessage({ source: SOURCE, type: type, payload: payload || {} }, window.location.origin);
  }

  function action(name, payload) {
    send('room-action', Object.assign({ action: name }, payload || {}));
  }

  function esc(value) {
    var div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
  }

  function roomOrigin() {
    try { return window.parent.location.origin; } catch (_) { return window.location.origin; }
  }

  function roomAssetUrl(value) {
    var raw = String(value || '').trim();
    if (!raw) return '';
    if (/^(data:|blob:|mineradio-local:)/i.test(raw)) return raw;
    try { return new URL(raw, roomOrigin()).href; } catch (_) { return raw; }
  }

  function roomCoverMarkup(value, className) {
    var src = roomAssetUrl(value);
    if (!src) return '<div class="' + (className || 'br-cover') + ' br-cover-empty">♫</div>';
    var proxied = /^https?:\/\//i.test(src) ? '/mineradio-api/cover?url=' + encodeURIComponent(src) : src;
    return '<img class="' + (className || 'br-cover') + '" src="' + esc(proxied) + '" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement(\'div\'),{className:\'' + (className || 'br-cover') + ' br-cover-empty\',textContent:\'♫\'}))">';
  }

  function currentSong() {
    if (Array.isArray(window.playQueue) && window.currentIdx >= 0) return window.playQueue[window.currentIdx] || null;
    return window.currentLocalSong || null;
  }

  function providerOf(song) {
    if (!song) return 'netease';
    if (song.provider === 'upload' || song.source === 'upload' || song.roomStreamUrl) return song.provider || 'upload';
    if (song.provider === 'audius' || song.source === 'audius') return 'audius';
    if (song.provider === 'qq' || song.source === 'qq' || song.type === 'qq') return 'qq';
    if (song.type === 'podcast') return 'podcast';
    return 'netease';
  }

  function trackPayload(song) {
    if (!song) return null;
    var provider = providerOf(song);
    var id = provider === 'qq' ? (song.mid || song.songmid || song.id) : (song.programId || song.id);
    if (id === undefined || id === null || id === '') return null;
    return {
      provider: provider,
      provider_track_id: String(id),
      title: String(song.name || song.title || '未命名歌曲'),
      artist: String(song.artist || song.singer || '未知音乐人'),
      album: String(song.album || song.albumName || ''),
      artwork_url: roomAssetUrl(song.cover || song.picUrl || song.albumPic || ''),
      duration_seconds: Math.max(0, Math.round(Number(song.duration || (window.audio && window.audio.duration) || 0) / (Number(song.duration) > 10000 ? 1000 : 1))),
      media_mid: String(song.mediaMid || song.media_mid || '')
    };
  }

  function trackKey(track) {
    return track ? track.provider + ':' + track.provider_track_id : '';
  }

  function syncRoomShelf(queue) {
    var items = Array.isArray(queue) ? queue : [];
    window.__BLUE_ROOM_SHELF_ITEMS = items.map(function (item) { return songFromRoomTrack(item); });
    if (typeof window.scheduleShelfRebuild === 'function') window.scheduleShelfRebuild('elysium-room-queue', false);
    else if (typeof window.safeShelfRebuild === 'function') window.safeShelfRebuild('elysium-room-queue', false);
  }

  function emitTrackIfChanged() {
    var track = trackPayload(currentSong());
    var key = trackKey(track);
    if (!key || key === lastTrackKey) return;
    lastTrackKey = key;
    send('track', track);
  }

  function emitPlayback(actionName, force) {
    if (!window.audio || (!force && Date.now() < remoteControlUntil)) return;
    send('playback', {
      action: actionName,
      time: Number(window.audio.currentTime || 0),
      duration: Number(window.audio.duration || 0),
      is_playing: !window.audio.paused && !window.audio.ended,
      track: trackPayload(currentSong())
    });
  }

  function bindAudio() {
    if (!window.audio || window.audio === boundAudio) return;
    boundAudio = window.audio;
    // Mineradio's native ended handler advances its personal queue. In room
    // mode only the Elysium server may advance the shared queue.
    boundAudio.onended = null;
    boundAudio.addEventListener('play', function () { emitTrackIfChanged(); emitPlayback('play'); });
    boundAudio.addEventListener('pause', function () { emitPlayback('pause'); });
    boundAudio.addEventListener('seeked', function () { emitPlayback('seek'); });
    boundAudio.addEventListener('ended', function () { emitPlayback('ended'); });
    boundAudio.addEventListener('timeupdate', function () {
      if (Date.now() - lastTimeSentAt < 2000) return;
      lastTimeSentAt = Date.now();
      emitPlayback('time');
    });
  }

  function songFromRoomTrack(track) {
    var provider = String(track.provider || 'netease');
    var song = {
      id: track.provider_track_id,
      name: track.title,
      artist: track.artist,
      album: track.album || '',
      cover: roomAssetUrl(track.artwork_url || ''),
      duration: Number(track.duration_seconds || 0) * 1000,
      provider: provider,
      source: provider
    };
    if (provider === 'qq') {
      song.type = 'qq';
      song.mid = track.provider_track_id;
      song.songmid = track.provider_track_id;
      song.mediaMid = track.media_mid || '';
    }
    if (provider === 'podcast') {
      song.type = 'podcast';
      song.programId = track.provider_track_id;
    }
    if ((track.stream_url && String(track.stream_url).indexOf('mineradio://') !== 0) || provider === 'upload' || provider === 'audius') {
      var rawStreamUrl = track.stream_url || track.source_url || '';
      // Room uploads are served by Elysium, while the embedded player is
      // served from the separate Mineradio origin.
      if (rawStreamUrl && rawStreamUrl.charAt(0) === '/') {
        try { rawStreamUrl = window.parent.location.origin + rawStreamUrl; } catch (_) {}
      }
      song.roomStreamUrl = rawStreamUrl;
      song.type = 'room-stream';
    }
    return song;
  }

  async function applyRoomState(state) {
    var sequence = ++applyRoomSequence;
    state = state || {};
    var track = state.track || null;
    var wantedKey = trackKey(track);
    var activeKey = trackKey(trackPayload(currentSong()));
    remoteControlUntil = Date.now() + 3500;

    if (track && wantedKey && wantedKey !== activeKey && typeof window.playQueueAt === 'function') {
      var song = songFromRoomTrack(track);
      var roomSongs = Array.isArray(state.queue) ? state.queue.filter(function (item) { return item && item.status !== 'proposed'; }).map(songFromRoomTrack) : [song];
      if (!roomSongs.length) roomSongs = [song];
      window.playQueue = roomSongs;
      window.__BLUE_ROOM_SHELF_ITEMS = roomSongs;
      window.currentIdx = Math.max(0, roomSongs.findIndex(function (entry) { return trackKey(trackPayload(entry)) === wantedKey; }));
      lastTrackKey = wantedKey;
      await window.playQueueAt(window.currentIdx, { resumeAt: Number(state.time || 0), preserveHomeState: true });
      if (sequence !== applyRoomSequence) return;
    }

    if (track && Array.isArray(track.lyrics) && typeof window.setOriginalLyricsState === 'function') {
      var lyricLines = track.lyrics.map(function (line, index) {
        var start = Number(line.t != null ? line.t : (line.time != null ? line.time : line.start));
        var next = track.lyrics[index + 1];
        var nextStart = next ? Number(next.t != null ? next.t : (next.time != null ? next.time : next.start)) : start + 6;
        return {
          t: Number.isFinite(start) ? start : index * 5,
          duration: Math.max(0.4, Number(line.duration || nextStart - start || 5)),
          text: String(line.text || line.lyric || ''),
          source: 'blue-album-room'
        };
      }).filter(function (line) { return line.text; });
      window.setOriginalLyricsState(lyricLines, false, 'blue-album-room');
      if (typeof window.applyOriginalLyricsState === 'function') window.applyOriginalLyricsState();
    }

    if (!window.audio) return;
    if (Number.isFinite(Number(state.playback_rate))) window.audio.playbackRate = Math.max(0.25, Number(state.playback_rate));
    if (Number.isFinite(Number(state.volume))) window.audio.volume = Math.min(1, Math.max(0, Number(state.volume)));
    var targetTime = Number(state.time);
    if (Number.isFinite(targetTime) && Math.abs(window.audio.currentTime - targetTime) > 0.75) {
      try { window.audio.currentTime = Math.max(0, targetTime); } catch (error) {}
    }
    if (state.is_playing === true || state.action === 'play') {
      try { await window.audio.play(); window.playing = true; if (window.setPlayIcon) window.setPlayIcon(true); } catch (error) {}
    } else if (state.is_playing === false || state.action === 'pause') {
      window.audio.pause();
      window.playing = false;
      if (window.setPlayIcon) window.setPlayIcon(false);
    }
  }

  function installRoomStyles() {
    var style = document.createElement('style');
    style.id = 'blue-room-native-style';
    style.textContent = [
      'body.blue-album-room-mode #user-btn,body.blue-album-room-mode #user-capsule-hide-btn,body.blue-album-room-mode #home-btn,body.blue-album-room-mode #empty-home,body.blue-album-room-mode #search-area,body.blue-album-room-mode #upload-actions,body.blue-album-room-mode #playlist-panel,body.blue-album-room-mode #mini-queue-btn,body.blue-album-room-mode #mini-queue-popover,body.blue-album-room-mode #heart-btn,body.blue-album-room-mode #collect-btn,body.blue-album-room-mode #play-mode-btn,body.blue-album-room-mode #prev-btn,body.blue-album-room-mode #next-btn,body.blue-album-room-mode #update-entry,body.blue-album-room-mode #login-modal,body.blue-album-room-mode #login-guide-canvas{display:none!important}',
      '#blue-room-btn{position:relative}',
      '#blue-room-leave{position:fixed;z-index:19;left:24px;top:24px;width:54px;height:54px;border-radius:50%;border:1px solid rgba(0,245,212,.30);background:linear-gradient(145deg,rgba(255,255,255,.16),rgba(255,255,255,.055) 48%,rgba(0,245,212,.055));color:rgba(232,236,239,.88);display:flex;align-items:center;justify-content:center;cursor:pointer;backdrop-filter:blur(26px) saturate(1.34);-webkit-backdrop-filter:blur(26px) saturate(1.34);box-shadow:0 14px 40px rgba(0,0,0,.34),0 0 24px rgba(0,245,212,.07),inset 0 1px 0 rgba(255,255,255,.18)}',
      '#blue-room-leave:hover{color:#fff;border-color:rgba(0,245,212,.50);background:rgba(0,245,212,.075);transform:translateY(-2px) scale(1.04)}',
      '#blue-room-btn .br-live{position:absolute;right:5px;top:5px;width:6px;height:6px;border-radius:50%;background:var(--fc-accent);box-shadow:0 0 10px rgba(var(--fc-accent-rgb),.9);opacity:0}',
      '#blue-room-btn.in-room .br-live{opacity:1}',
      '#blue-room-panel{position:fixed;z-index:32;right:-460px;bottom:92px;width:min(444px,calc(100vw - 48px));max-height:min(650px,calc(100dvh - 132px));display:flex;flex-direction:column;box-sizing:border-box;overflow-x:hidden;overflow-y:auto;padding:18px 18px 32px;border:1px solid rgba(0,245,212,.16);border-radius:20px;background:var(--glass-bg);backdrop-filter:blur(44px) saturate(1.34);-webkit-backdrop-filter:blur(44px) saturate(1.34);box-shadow:var(--glass-shadow);opacity:0;pointer-events:none;transform:translateY(18px) scale(.97);transition:right .55s cubic-bezier(.16,1,.3,1),opacity .45s cubic-bezier(.16,1,.3,1),transform .55s cubic-bezier(.16,1,.3,1)}',
      '#blue-room-panel.show{right:24px;opacity:1;pointer-events:auto;transform:translateY(0) scale(1);animation:fx-panel-in .56s cubic-bezier(.16,1,.3,1)}',
      '.br-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:14px;border-bottom:1px solid rgba(255,255,255,.07)}',
      '.br-kicker{font:700 9px/1 var(--font-mono);letter-spacing:.18em;color:rgba(var(--fc-accent-rgb),.8);text-transform:uppercase}',
      '.br-title{margin-top:6px;font-size:18px;font-weight:760;color:rgba(255,255,255,.94)}',
      '.br-sub{margin-top:5px;font-size:10px;color:rgba(255,255,255,.38)}',
      '.br-head-actions{display:flex;gap:6px}',
      '.br-icon{width:30px;height:30px;border-radius:10px;border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.035);color:rgba(255,255,255,.58);cursor:pointer}',
      '.br-body{flex:1;min-height:0;overflow:auto;padding-top:14px;scrollbar-width:thin;scrollbar-color:rgba(var(--fc-accent-rgb),.25) transparent}',
      '.br-section{margin:0 0 15px}',
      '.br-section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font-size:10px;font-weight:760;letter-spacing:.08em;color:rgba(255,255,255,.48);text-transform:uppercase}',
      '.br-section-head span{font:500 9px/1 var(--font-mono);color:rgba(255,255,255,.28)}',
      '.br-card{border:1px solid rgba(255,255,255,.075);border-radius:12px;background:rgba(255,255,255,.032);padding:11px}',
      '.br-now{display:grid;grid-template-columns:52px minmax(0,1fr);gap:11px;align-items:center}',
      '.br-now-action{grid-column:1/-1;width:100%}',
      '.br-cover{width:52px;height:52px;border-radius:11px;object-fit:cover;background:radial-gradient(circle,rgba(var(--fc-accent-rgb),.22),rgba(255,255,255,.035));display:grid;place-items:center;color:rgba(255,255,255,.55);font-size:20px}',
      '.br-now strong,.br-row strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;color:rgba(255,255,255,.88)}',
      '.br-now small,.br-row small{display:block;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:9px;color:rgba(255,255,255,.38)}',
      '.br-room-meta{display:flex;align-items:center;gap:8px;margin-bottom:10px;font-size:10px;color:rgba(255,255,255,.48)}',
      '.br-dot{width:6px;height:6px;border-radius:50%;background:var(--fc-accent);box-shadow:0 0 10px rgba(var(--fc-accent-rgb),.7)}',
      '.br-code{margin-left:auto;font:600 10px/1 var(--font-mono);color:rgba(var(--fc-accent-rgb),.78);cursor:pointer}',
      '.br-list{display:grid;gap:7px;min-width:0;overflow:hidden}',
      '.br-row{display:flex;align-items:center;gap:9px;min-width:0;width:100%;box-sizing:border-box;overflow:hidden;padding:9px 10px;border:1px solid rgba(255,255,255,.065);border-radius:0;background:rgba(255,255,255,.026)}',
      '.br-row-main{flex:1;min-width:0}',
      '.br-avatar{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:rgba(var(--fc-accent-rgb),.09);color:rgba(var(--fc-accent-rgb),.8);font:700 10px/1 var(--font-mono)}',
      '.br-uid{font:600 9px/1 var(--font-mono)!important;color:rgba(var(--fc-accent-rgb),.64)!important}',
      '.br-status{width:6px;height:6px;border-radius:50%;background:#59606b}.br-status.online{background:#7ee2a8;box-shadow:0 0 8px rgba(126,226,168,.6)}',
      '.br-btn{height:30px;border:1px solid rgba(var(--fc-accent-rgb),.22);border-radius:9px;background:rgba(var(--fc-accent-rgb),.08);color:rgba(var(--fc-accent-rgb),.88);padding:0 10px;font:700 10px/1 var(--font-sans);cursor:pointer}',
      '.br-btn.active{border-color:rgba(var(--fc-accent-rgb),.48);background:rgba(var(--fc-accent-rgb),.18);color:#fff}.br-btn:disabled{opacity:.48;cursor:default}',
      '.br-btn.primary{height:38px;background:rgba(var(--fc-accent-rgb),.15);color:#fff;width:100%}',
      '.br-btn.ghost{border-color:rgba(255,255,255,.08);background:rgba(255,255,255,.03);color:rgba(255,255,255,.48)}',
      '.br-form{display:grid;gap:11px}.br-form label{display:grid;gap:6px;font-size:10px;color:rgba(255,255,255,.42)}',
      '.br-file-picker{position:relative;cursor:pointer}.br-file-picker input{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}.br-file-line{display:flex;align-items:center;gap:8px;min-width:0;height:38px;border:1px solid rgba(255,255,255,.09);border-radius:10px;background:rgba(0,0,0,.22);padding:0 10px}.br-file-button{flex:0 0 auto;color:rgba(var(--fc-accent-rgb),.9);font-weight:700}.br-file-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:rgba(255,255,255,.46)}',
      '.br-source-tabs{display:flex;gap:5px;margin-bottom:8px;overflow:auto}.br-source{flex:0 0 auto;height:27px;padding:0 9px;border:1px solid rgba(255,255,255,.07);border-radius:999px;background:rgba(255,255,255,.025);color:rgba(255,255,255,.48);font-size:9px;cursor:pointer}.br-source.active{border-color:rgba(var(--fc-accent-rgb),.32);background:rgba(var(--fc-accent-rgb),.10);color:rgba(var(--fc-accent-rgb),.92)}.br-source:disabled{opacity:.38;cursor:not-allowed}.br-search-form{display:flex;gap:6px}.br-search-form .br-input{flex:1;min-width:0}.br-result-cover{width:36px;height:36px;flex:0 0 36px;border-radius:9px;object-fit:cover;background:rgba(255,255,255,.04)}.br-cover-empty{display:grid;place-items:center}.br-queue-action{display:flex;justify-content:flex-end;margin:-2px 0 8px}.br-provider{display:inline-block;margin-left:5px;padding:2px 4px;border-radius:0;background:rgba(var(--fc-accent-rgb),.08);color:rgba(var(--fc-accent-rgb),.72);font:600 7px/1 var(--font-mono)}',
      '.br-catalog-note{display:block;margin:6px 2px 0;font-size:8px;line-height:1.45;color:rgba(255,255,255,.28)}',
      '.br-input{height:38px;min-width:0;max-width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.09);border-radius:10px;background:rgba(0,0,0,.22);color:#fff;padding:0 11px;outline:none;font-family:var(--font-sans)}',
      '.br-input:focus{border-color:rgba(var(--fc-accent-rgb),.36)}',
      '.br-chat{display:flex;flex-direction:column;gap:7px;max-height:160px;overflow:auto}',
      '.br-msg{max-width:86%}.br-msg.mine{align-self:flex-end;text-align:right}.br-msg small{font-size:8px;color:rgba(255,255,255,.3)}',
      '.br-msg p{margin-top:3px;padding:7px 9px;border-radius:4px 10px 10px;background:rgba(255,255,255,.045);font-size:10px;line-height:1.4;color:rgba(255,255,255,.72);text-align:left}.br-msg.mine p{border-radius:10px 4px 10px 10px;background:rgba(var(--fc-accent-rgb),.08)}',
      '.br-chat-form{display:flex;gap:6px;margin-top:9px}.br-chat-form .br-input{flex:1;min-width:0;height:34px}.br-empty{padding:18px 8px;text-align:center;font-size:10px;line-height:1.6;color:rgba(255,255,255,.28)}',
      '.br-footer{display:flex;gap:7px;padding-top:12px;border-top:1px solid rgba(255,255,255,.07)}',
      '.br-footer .br-btn{flex:1}.br-host-fold{margin-top:10px;border:1px solid rgba(255,255,255,.075);border-radius:12px;background:rgba(255,255,255,.024);overflow:hidden}.br-host-fold summary{padding:13px 12px;color:rgba(255,255,255,.72);cursor:pointer;font-size:11px;font-weight:700}.br-host-fold[open] summary{color:#fff;background:rgba(255,255,255,.024)}.br-host-fold-body{display:grid;gap:9px;padding:0 11px 11px}.br-member-chat{display:grid;gap:12px}.br-member-chat .br-list{max-height:170px;overflow:auto}',
      '@media(max-width:720px){#blue-room-panel{left:12px;right:12px!important;top:76px;bottom:auto;width:auto;max-height:calc(100dvh - 132px)}#blue-room-leave{left:12px;top:12px;width:48px;height:48px}.br-head{padding-bottom:10px}.br-body{padding-top:10px}.br-section{margin-bottom:11px}.br-now{grid-template-columns:44px minmax(0,1fr)}.br-cover{width:44px;height:44px}.br-row{padding:8px}.br-footer{padding-top:9px}.br-footer .br-btn{padding:0 5px}.br-members{grid-template-columns:1fr}}'
    ].join('');
    document.head.appendChild(style);
  }

  function installRoomUi() {
    if (document.getElementById('blue-room-btn')) return;
    installRoomStyles();
    var top = document.getElementById('top-right');
    var button = document.createElement('button');
    button.id = 'blue-room-btn';
    button.className = 'icon-btn';
    button.title = '听歌房';
    button.setAttribute('aria-label', '听歌房');
    button.innerHTML = '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M9 18H5a3 3 0 0 1-3-3v-1a4 4 0 0 1 4-4h3"/><circle cx="7" cy="6" r="3"/><path d="M15 18h4a3 3 0 0 0 3-3v-1a4 4 0 0 0-4-4h-3"/><circle cx="17" cy="6" r="3"/><path d="M9 14h6v7H9z"/></svg><i class="br-live"></i>';
    button.addEventListener('click', toggleRoomPanel);
    top.insertBefore(button, document.getElementById('user-btn'));

    var leaveButton = document.createElement('button');
    leaveButton.id = 'blue-room-leave';
    leaveButton.title = '退出房间';
    leaveButton.setAttribute('aria-label', '退出房间');
    leaveButton.innerHTML = '<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.9" viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/><path d="M9 12h12"/></svg>';
    leaveButton.addEventListener('click', function () { action('leave'); });
    document.body.appendChild(leaveButton);

    var panel = document.createElement('section');
    panel.id = 'blue-room-panel';
    panel.setAttribute('aria-label', '听歌房');
    panel.innerHTML = '<div class="br-head"><div style="flex:1"><div class="br-kicker">Mineradio 同步听歌</div><div class="br-title" id="br-title">一起听</div><div class="br-sub" id="br-sub">房间播放由成员共同决定</div></div><div class="br-head-actions"><button class="br-icon" data-action="close" title="关闭">×</button></div></div><div class="br-body" id="br-body"></div>';
    panel.addEventListener('click', handlePanelClick);
    panel.addEventListener('change', handlePanelChange);
    panel.addEventListener('submit', handlePanelSubmit);
    document.body.appendChild(panel);
    var fx = document.getElementById('fx-fab');
    if (fx) fx.addEventListener('click', closeRoomPanel, true);
    document.addEventListener('keydown', function (event) { if (event.key === 'Escape') closeRoomPanel(); });
    renderRoomUi();
  }

  function bindNativeRoomControls() {
    var playButton = document.getElementById('play-btn');
    var progressBar = document.getElementById('progress-bar');
    if (playButton) playButton.addEventListener('click', function () {
      remoteControlUntil = Date.now() + 500;
      window.setTimeout(function () { emitPlayback(window.audio && window.audio.paused ? 'pause' : 'play', true); }, 80);
    }, true);
    if (progressBar) progressBar.addEventListener('pointerup', function () {
      remoteControlUntil = Date.now() + 500;
      window.setTimeout(function () { emitPlayback('seek', true); }, 80);
    }, true);
  }

  function disablePersonalRoomTracking() {
    window.beginListenSession = function () {};
    window.updateListenStatsTick = function () {};
    window.finalizeListenSession = function () {};
    window.listenSession = null;
  }

  function toggleRoomPanel() {
    var panel = document.getElementById('blue-room-panel');
    if (!panel) return;
    var opening = !panel.classList.contains('show');
    panel.classList.toggle('show', opening);
    document.getElementById('blue-room-btn').classList.toggle('active', opening);
    if (opening) {
      var fxPanel = document.getElementById('fx-panel');
      var fxFab = document.getElementById('fx-fab');
      if (fxPanel) fxPanel.classList.remove('show', 'peek');
      if (fxFab) fxFab.classList.remove('active');
    }
  }

  function closeRoomPanel() {
    var panel = document.getElementById('blue-room-panel');
    var button = document.getElementById('blue-room-btn');
    if (panel) panel.classList.remove('show');
    if (button) button.classList.remove('active');
  }

  function renderRoomUi() {
    var body = document.getElementById('br-body');
    if (!body) return;
    var button = document.getElementById('blue-room-btn');
    button.classList.toggle('in-room', !!roomState.inRoom);
    document.getElementById('br-title').textContent = roomState.inRoom ? ((roomState.room && roomState.room.room_name) || '听歌房') : '一起听';
    document.getElementById('br-sub').textContent = roomState.inRoom
      ? (roomState.canControl ? '你可以控制房间播放；点歌立即进入公共歌单' : '播放由房主控制；点歌立即进入公共歌单')
      : '创建或加入房间后才会同步播放';
    body.innerHTML = roomState.inRoom ? renderActiveRoom() : renderLobby();
  }

  function renderLobby() {
    var rooms = roomState.rooms || [];
    var list = rooms.length ? rooms.map(function (room) {
      var online = (room.members || []).filter(function (member) { return member.is_online; }).length;
      return '<button class="br-row" data-action="enter" data-room-id="' + Number(room.id) + '"><span class="br-avatar">' + esc(String(room.room_name || '房').slice(0, 1)) + '</span><span class="br-row-main"><strong>' + esc(room.room_name) + '</strong><small>' + esc(room.room_code || '') + '</small></span><span class="br-uid">' + online + ' 人在线</span></button>';
    }).join('') : '<div class="br-empty">还没有开放的听歌房<br>创建一个房间，再邀请朋友加入</div>';
    return '<div class="br-section"><div class="br-section-head">创建房间<span>私密同步</span></div><form class="br-form" data-form="create"><label>房间名称<input class="br-input" name="roomName" maxlength="80" placeholder="深夜电台"></label><label>暂停与进度控制<select class="br-input" name="controlMode"><option value="host_only">仅房主</option><option value="all_members">所有成员</option></select></label><button class="br-btn primary" type="submit">创建听歌房</button></form></div><div class="br-section"><div class="br-section-head">开放中的房间<span>' + rooms.length + ' 个房间</span></div><div class="br-list">' + list + '</div></div>';
  }

  function renderActiveRoom() {
    var room = roomState.room || {};
    var current = (roomState.queue || []).filter(function (item) { return item.status === 'playing'; })[0] || null;
    var waiting = (roomState.queue || []).filter(function (item) { return item.status !== 'playing'; });
    var members = roomState.members || [];
    var messages = roomState.messages || [];
    var cover = roomCoverMarkup(current && current.artwork_url, 'br-cover');
    var isHost = Number(room.host_user_id) === Number(roomState.userId);
    var memberRows = members.length ? members.map(function (member) {
      return '<div class="br-row"><span class="br-avatar">' + esc(String(member.username || member.user_id).slice(0, 1).toUpperCase()) + '</span><span class="br-row-main"><strong>' + esc(member.nickname || member.username || '成员') + '</strong><small class="br-uid">用户编号 · ' + Number(member.user_id) + (member.user_id === room.host_user_id ? ' · 房主' : '') + '</small></span><i class="br-status ' + (member.is_online ? 'online' : '') + '" title="' + (member.is_online ? '在线' : '离线') + '"></i></div>';
    }).join('') : '<div class="br-empty">成员列表正在同步</div>';
    var queueRows = waiting.length ? waiting.map(function (item) {
      var status = item.status === 'proposed' ? '待播' : '等待播放';
      var count = Number(item.like_count || 0);
      var liked = Array.isArray(item.liked_by_user_ids) && item.liked_by_user_ids.some(function (id) { return Number(id) === Number(roomState.userId); });
      var actionHtml = item.status === 'proposed'
        ? '<button class="br-btn ghost" data-action="vote" data-item-id="' + Number(item.id) + '">同意</button>'
        : '<button class="br-btn ghost ' + (liked ? 'active' : '') + '" data-action="like" data-item-id="' + Number(item.id) + '">' + (liked ? '取消点赞 ' : '点赞 ') + count + '</button>';
      var reason = item.unavailable_reason ? '<small style="color:#ffaaa2">不可播放：' + esc(item.unavailable_reason) + '</small>' : '';
      return '<div class="br-row">' + roomCoverMarkup(item.artwork_url, 'br-result-cover') + '<span class="br-row-main"><strong>' + esc(item.title) + '</strong><small>' + esc(item.artist) + ' · ' + status + '</small><small>点歌人：' + esc(item.added_by_name || '房间成员') + '</small>' + reason + '</span>' + actionHtml + '</div>';
    }).join('') : '<div class="br-empty">在播放器中选择歌曲，会先进入候选投票</div>';
    var chatRows = messages.length ? messages.slice(-30).map(function (message) {
      var mine = Number(message.user_id) === Number(roomState.userId);
      return '<div class="br-msg ' + (mine ? 'mine' : '') + '"><small>' + esc(message.username || '成员') + ' · ID ' + Number(message.user_id) + '</small><p>' + esc(message.message) + '</p></div>';
    }).join('') : '<div class="br-empty">还没有消息</div>';
    var catalog = roomState.catalog || [];
    var shownCatalog = catalogExpanded ? catalog : catalog.slice(0, 5);
    var providerNames = { netease: '网易云', qq: 'QQ' };
    var catalogRows = shownCatalog.length ? shownCatalog.map(function (track) {
      var img = roomCoverMarkup(track.artwork_url, 'br-result-cover');
      var unavailable = track.availability === 'unavailable';
      var reason = unavailable ? '<small style="color:#ffaaa2">' + esc(track.unavailable_reason || '当前没有可播放地址') + '</small>' : '';
      return '<div class="br-row">' + img + '<span class="br-row-main"><strong>' + esc(track.title) + '<i class="br-provider">' + esc(providerNames[track.provider] || track.provider) + '</i></strong><small>' + esc(track.artist) + '</small>' + reason + '</span><button class="br-btn" data-action="propose-catalog" data-track-index="' + catalog.indexOf(track) + '" ' + (unavailable ? 'disabled' : '') + '>' + (unavailable ? '不可点歌' : '点歌') + '</button></div>';
    }).join('') : '';
    var catalogMore = '';
    var currentReason = roomState.currentUnavailableReason ? '<small style="color:#ffaaa2">不可播放：' + esc(roomState.currentUnavailableReason) + '</small>' : '';
    var threshold = Number(room.music_skip_vote_percent || 30);
    var playbackStatus = roomState.currentUnavailableReason ? '播放失败' : current ? (room.is_playing ? '正在播放' : '已暂停') : '等待点歌';
    var skipVoted = current && Array.isArray(current.skip_voted_by_user_ids) && current.skip_voted_by_user_ids.some(function (id) { return Number(id) === Number(roomState.userId); });
    var skipLabel = current ? (skipVoted ? '已投票 ' : '投票切歌 ') + Number(current.skip_votes || 0) + '/' + Number(current.skip_required || 1) : '';
    var queueAction = current ? '<div class="br-queue-action"><button class="br-btn ghost ' + (skipVoted ? 'active' : '') + '" data-action="vote-skip" ' + (skipVoted ? 'disabled' : '') + '>' + skipLabel + '</button></div>' : '';
    var providerCapabilities = roomState.providerCapabilities && roomState.providerCapabilities.length ? roomState.providerCapabilities : [
      { provider: 'netease', label: '网易云', searchable: true },
      { provider: 'qq', label: 'QQ 音乐', searchable: true },
    ].filter(function (provider) { return provider.provider === 'netease' || provider.provider === 'qq'; });
    var sourceOptions = providerCapabilities.map(function (provider) {
      var active = (roomState.catalogSource || 'netease') === provider.provider;
      var disabled = !provider.searchable;
      return '<button class="br-source ' + (active ? 'active' : '') + '" data-action="source" data-source="' + esc(provider.provider) + '" title="' + esc(provider.reason || '') + '" ' + (disabled ? 'disabled' : '') + '>' + esc(provider.label) + (disabled ? ' · 不可用' : '') + '</button>';
    }).join('');
    var otherProvider = roomState.catalogSource === 'qq' ? 'netease' : 'qq';
    var otherLabel = otherProvider === 'qq' ? 'QQ 音乐' : '网易云';
    var catalogError = roomState.notice && /曲库|搜索|连接|播放/.test(String(roomState.notice));
    var catalogEmpty = catalogError
      ? '<div class="br-empty">' + esc(roomState.notice) + '<br><button class="br-btn ghost" data-action="source" data-source="' + otherProvider + '">切换到 ' + otherLabel + '</button><small>切换后请重新点击搜索</small></div>'
      : '<div class="br-empty">输入歌曲名或音乐人，搜索当前平台曲库</div>';
    var syncStatus = String(roomState.syncStatus || 'connecting');
    var syncLabels = { connecting: '正在连接…', syncing: '正在同步…', synced: '已同步', reconnecting: '连接中断', error: '同步失败' };
    var roomMeta = '<div class="br-room-meta" data-sync-status="' + esc(syncStatus) + '"><i class="br-dot"></i><span>' + esc(syncLabels[syncStatus] || syncStatus) + '</span><span class="br-code">' + esc(room.room_code || '') + '</span></div>';
    var core = roomMeta + '<div class="br-section"><div class="br-section-head">当前正在播放<span>' + playbackStatus + '</span></div><div class="br-card br-now">' + cover + '<div><strong>' + esc(current ? current.title : '等待第一首歌') + '</strong><small>' + esc(current ? current.artist : '在线曲库') + '</small>' + currentReason + '</div></div></div><div class="br-section"><div class="br-section-head"><b>歌单</b><span>' + waiting.length + ' 首待播</span></div>' + queueAction + '<div class="br-list">' + queueRows + '</div></div><div class="br-section"><div class="br-section-head">在线点歌<span>' + esc(roomState.catalogSource || 'netease') + '</span></div><div class="br-source-tabs">' + sourceOptions + '</div><form class="br-search-form" data-form="catalog"><input class="br-input" name="query" maxlength="100" placeholder="搜索歌曲或音乐人"><button class="br-btn" type="submit">搜索</button></form><div class="br-list" style="margin-top:8px">' + (catalogRows || catalogEmpty) + '</div>' + catalogMore + '</div><div class="br-section"><div class="br-section-head">在线成员与聊天<span>' + members.filter(function (m) { return m.is_online; }).length + ' 人在线</span></div><div class="br-card br-member-chat"><div class="br-list">' + memberRows + '</div><div class="br-chat">' + chatRows + '</div><form class="br-chat-form" data-form="chat"><input class="br-input" name="message" maxlength="500" placeholder="说点什么…"><button class="br-btn" type="submit">发送</button></form></div></div>';
    if (!isHost) return core;
    return core + '<details class="br-host-fold"><summary>房主功能</summary><div class="br-host-fold-body">' + (current ? '<button class="br-btn primary" data-action="force-skip">立即切歌</button>' : '<div class="br-empty">当前没有正在播放的歌曲</div>') + '<label class="br-section-head" style="margin:0">切歌门槛<select class="br-input" data-setting="music_skip_vote_percent"><option value="30" ' + (threshold === 30 ? 'selected' : '') + '>30%</option><option value="50" ' + (threshold === 50 ? 'selected' : '') + '>50%</option><option value="70" ' + (threshold === 70 ? 'selected' : '') + '>70%</option></select></label></div></details>';
  }

  function handlePanelChange(event) {
    var input = event.target;
    if (input && input.dataset && input.dataset.setting === 'music_skip_vote_percent') {
      action('settings', { music_skip_vote_percent: Number(input.value) });
      return;
    }
    if (!input || input.type !== 'file' || input.name !== 'file') return;
    var name = input.parentElement && input.parentElement.querySelector('.br-file-name');
    if (name) name.textContent = input.files && input.files[0] ? input.files[0].name : '尚未选择文件';
  }

  function handlePanelClick(event) {
    var target = event.target.closest('[data-action]');
    if (!target) return;
    var name = target.getAttribute('data-action');
    if (name === 'close') closeRoomPanel();
    else if (name === 'back') action('back');
    else if (name === 'enter') action('enter', { roomId: Number(target.getAttribute('data-room-id')) });
    else if (name === 'leave') action('leave');
    else if (name === 'vote') action('vote', { itemId: Number(target.getAttribute('data-item-id')) });
    else if (name === 'like') action('like', { itemId: Number(target.getAttribute('data-item-id')) });
    else if (name === 'vote-skip') action('vote-skip');
    else if (name === 'force-skip') action('force-skip');
    else if (name === 'skip') action('skip');
    else if (name === 'resync') action('resync');
    else if (name === 'catalog-more') { catalogExpanded = !catalogExpanded; renderRoomUi(); }
    else if (name === 'source') { action('source', { source: target.getAttribute('data-source') || 'netease' }); }
    else if (name === 'propose-catalog') {
      var track = (roomState.catalog || [])[Number(target.getAttribute('data-track-index'))];
      if (track) action('propose-catalog', { track: track });
    }
    else if (name === 'copy') {
      var code = target.getAttribute('data-code') || '';
      if (navigator.clipboard) navigator.clipboard.writeText(code);
      if (window.showToast) window.showToast('房间码已复制');
    }
  }

  function handlePanelSubmit(event) {
    event.preventDefault();
    var form = event.target;
    var kind = form.getAttribute('data-form');
    var data = new FormData(form);
    if (kind === 'create') action('create', { roomName: data.get('roomName') || '', controlMode: data.get('controlMode') || 'host_only' });
    if (kind === 'chat') {
      var message = String(data.get('message') || '').trim();
      if (message) action('chat', { message: message });
      form.reset();
    }
    if (kind === 'catalog') {
      var query = String(data.get('query') || '').trim();
      if (query) action('search', { query: query, source: roomState.catalogSource || 'netease' });
    }
  }

  window.addEventListener('message', function (event) {
    if (event.origin !== window.location.origin || event.source !== window.parent) return;
    var message = event.data || {};
    if (message.source !== 'blue-album-room') return;
    if (message.type === 'sync') {
      applyRoomState(message.payload).catch(function (error) {
        send('error', { message: error && error.message ? error.message : '同步失败' });
      });
    }
    if (message.type === 'room-state') {
      roomState = Object.assign({}, roomState, message.payload || {});
      syncRoomShelf(roomState.queue);
      renderRoomUi();
      if (!roomStartupReady) {
        roomStartupReady = true;
        if (typeof window.dismissSplash === 'function') window.dismissSplash({ instant: true });
        window.setTimeout(toggleRoomPanel, 0);
      }
      if (roomState.notice && roomState.notice !== lastRoomNotice && window.showToast) {
        lastRoomNotice = roomState.notice;
        window.showToast(roomState.notice);
      }
    }
  });

  installRoomUi();
  disablePersonalRoomTracking();
  bindNativeRoomControls();
  if (typeof window.dismissSplash === 'function') window.dismissSplash({ instant: true });
  window.setInterval(function () { bindAudio(); emitTrackIfChanged(); }, 350);
  send('ready', { version: '2.1.1-blue-album-native-room' });
})();
